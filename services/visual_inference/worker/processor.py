from __future__ import annotations

import asyncio
import io
import logging
import os
import threading
from typing import Any

import httpx

from shared.http_utils import fetch_url_bytes
from shared.protocol.envelope import TaskResult, TaskStatus

logger = logging.getLogger(__name__)

_qwen_lock = threading.Lock()
_qwen_processor: Any = None
_qwen_model: Any = None


def _visual_backend() -> str:
    return os.environ.get("VISUAL_BACKEND", "").strip().lower()


def _should_try_openai_api() -> bool:
    b = _visual_backend()
    if b == "api":
        return True
    if not b and os.environ.get("VISUAL_USE_VLM", "0") == "1":
        return True
    return False


def _should_try_local_qwen() -> bool:
    b = _visual_backend()
    if b == "local":
        return True
    if b in ("auto", "") and os.environ.get("QWEN_VL_MODEL_ID", "").strip():
        return True
    return False


def _ensure_qwen() -> tuple[Any, Any]:
    global _qwen_processor, _qwen_model
    with _qwen_lock:
        if _qwen_model is not None:
            return _qwen_processor, _qwen_model
        import torch
        from transformers import AutoProcessor, Qwen2VLForConditionalGeneration

        model_id = os.environ.get("QWEN_VL_MODEL_ID", "Qwen/Qwen2-VL-2B-Instruct").strip()
        dtype_name = os.environ.get("QWEN_VL_TORCH_DTYPE", "bfloat16").strip().lower()
        torch_dtype = getattr(torch, dtype_name, torch.bfloat16)
        _qwen_processor = AutoProcessor.from_pretrained(model_id)
        _qwen_model = Qwen2VLForConditionalGeneration.from_pretrained(
            model_id,
            torch_dtype=torch_dtype,
            device_map="auto",
        )
        return _qwen_processor, _qwen_model


def _local_qwen_caption(image_bytes: bytes, caption: str) -> str:
    import torch
    from PIL import Image
    from qwen_vl_utils import process_vision_info

    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": caption},
            ],
        }
    ]
    processor, model = _ensure_qwen()
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    max_pixels = int(os.environ.get("VISUAL_MAX_PIXELS", "802816"))
    image_inputs, video_inputs = process_vision_info(messages)
    proc_kw: dict[str, Any] = {
        "text": [text],
        "images": image_inputs,
        "videos": video_inputs,
        "padding": True,
        "return_tensors": "pt",
    }
    try:
        inputs = processor(**proc_kw, max_pixels=max_pixels)
    except TypeError:
        inputs = processor(**proc_kw)
    device = next(model.parameters()).device
    inputs = inputs.to(device)
    max_new = int(os.environ.get("VISUAL_MAX_NEW_TOKENS", "256"))
    with torch.inference_mode():
        generated = model.generate(**inputs, max_new_tokens=max_new)
    in_len = inputs["input_ids"].shape[1]
    trimmed = generated[:, in_len:]
    decoded = processor.batch_decode(
        trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
    )
    return (decoded[0] if decoded else "").strip()


async def _openai_compatible_vlm(image_url: str, caption: str) -> str:
    data = await fetch_url_bytes(image_url)
    b64 = __import__("base64").b64encode(data).decode("ascii")
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(
            f"{os.environ.get('OPENAI_API_BASE', 'https://api.openai.com/v1').rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {os.environ.get('OPENAI_API_KEY', '')}"},
            json={
                "model": os.environ.get("VISUAL_MODEL", "gpt-4o-mini"),
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": caption},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                            },
                        ],
                    }
                ],
                "max_tokens": 500,
            },
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


async def process_visual(env) -> TaskResult:
    payload = env.payload or {}
    caption = payload.get("caption") or "Describe the image."
    image_url = payload.get("image_url") or (env.input_refs[0] if env.input_refs else None)
    summary = f"visual_inference:{caption}"

    if image_url and _should_try_openai_api() and os.environ.get("OPENAI_API_KEY"):
        try:
            summary = await _openai_compatible_vlm(image_url, caption)
        except Exception as exc:
            logger.warning("VLM API call failed: %s", exc)
            summary = f"{summary} (vlm_error: {exc})"

    elif image_url and _should_try_local_qwen():
        try:
            data = await fetch_url_bytes(image_url)
            summary = await asyncio.to_thread(_local_qwen_caption, data, caption)
        except Exception as exc:
            logger.warning("local Qwen-VL failed: %s", exc)
            summary = f"{summary} (local_vlm_error: {exc})"

    return TaskResult(
        job_id=env.job_id,
        service=env.service,
        status=TaskStatus.completed,
        asset_id=env.asset_id,
        data={"summary": summary, "confidence": 0.5},
    )
