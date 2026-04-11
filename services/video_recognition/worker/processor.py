from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import asyncpg

from shared.http_utils import fetch_url_bytes
from shared.messaging.redis_streams import JobBroker, StreamsConfig
from shared.messaging.reliability import record_job_pending
from shared.paths import storage_root
from shared.protocol.envelope import OutputSpec, ServiceName, TaskEnvelope, TaskResult, TaskStatus

logger = logging.getLogger(__name__)


def _try_faster_whisper(video_path: Path) -> str | None:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None
    model_name = os.environ.get("WHISPER_MODEL", "base")
    device = os.environ.get("WHISPER_DEVICE", "cuda")
    compute_type = os.environ.get("WHISPER_COMPUTE_TYPE", "float16")
    cache = (os.environ.get("WHISPER_CACHE") or os.environ.get("HF_HOME") or "").strip()
    kwargs: dict = {}
    if cache:
        kwargs["download_root"] = cache
    try:
        wm = WhisperModel(model_name, device=device, compute_type=compute_type, **kwargs)
        segments, _info = wm.transcribe(str(video_path))
        parts = [s.text for s in segments]
        text = " ".join(parts).strip()
        return text[:32000] if text else None
    except Exception as exc:
        logger.warning("faster-whisper failed: %s", exc)
        return None


def _try_openai_whisper(video_path: Path) -> str | None:
    whisper = shutil.which("whisper")
    if not whisper:
        try:
            import whisper as whisper_mod  # type: ignore

            model = whisper_mod.load_model(os.environ.get("WHISPER_MODEL", "base"))
            result = model.transcribe(str(video_path))
            return result.get("text") or None
        except Exception as exc:
            logger.warning("openai-whisper not available: %s", exc)
            return None
    out = tempfile.mkdtemp(prefix="whisper_")
    try:
        subprocess.run(
            [whisper, str(video_path), "--output_format", "txt", "--output_dir", out],
            check=True,
            timeout=int(os.environ.get("WHISPER_TIMEOUT", "600")),
        )
        txts = list(Path(out).glob("*.txt"))
        if txts:
            return txts[0].read_text(encoding="utf-8", errors="ignore")[:32000]
    except Exception as exc:
        logger.warning("whisper CLI failed: %s", exc)
    finally:
        shutil.rmtree(out, ignore_errors=True)
    return None


def _try_whisper_transcribe(video_path: Path) -> str | None:
    if os.environ.get("VIDEO_WHISPER", "0") != "1":
        return None
    backend = os.environ.get("WHISPER_BACKEND", "auto").lower().strip()
    if backend == "openai":
        return _try_openai_whisper(video_path)
    if backend == "faster":
        return _try_faster_whisper(video_path)
    # auto: prefer faster-whisper (GPU images), then OpenAI whisper / CLI
    text = _try_faster_whisper(video_path)
    if text:
        return text
    return _try_openai_whisper(video_path)


def _public_url(rel: Path) -> str:
    base = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
    return f"{base}/static/storage/{rel.as_posix()}"


async def process_video(env: TaskEnvelope) -> TaskResult:
    if not env.asset_id:
        raise ValueError("video_recognition requires asset_id")
    asset_id = env.asset_id
    payload = env.payload or {}
    process_rel = Path(payload.get("process_dir_rel", f"processed/video/{asset_id}"))
    process_dir = storage_root() / process_rel
    process_dir.mkdir(parents=True, exist_ok=True)

    raw_url = env.input_refs[0]
    data = await fetch_url_bytes(raw_url)
    vid_path = process_dir / "source.video"
    vid_path.write_bytes(data)

    transcript = _try_whisper_transcribe(vid_path)
    if transcript:
        body = transcript
    else:
        body = f"[video stub transcript] asset={asset_id} bytes={len(data)} (set VIDEO_WHISPER=1 for Whisper)"

    chunks = [
        {
            "content": body,
            "type": "text",
            "coordination": {"timestamp_start": 0.0, "timestamp_end": 1.0},
            "visual_description": "keyframe:0",
        }
    ]
    manifest = {"asset_id": asset_id, "chunks": chunks}
    manifest_path = process_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    manifest_url = _public_url(process_rel / "manifest.json")

    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql://contextmap:contextmap@localhost:5432/contextmap",
    )
    conn = await asyncpg.connect(db_url)
    try:
        await conn.execute(
            "UPDATE assets SET status = $2, process_path = COALESCE(process_path, $3) WHERE id = $1::uuid",
            asset_id,
            "Structuring",
            manifest_url,
        )
    finally:
        await conn.close()

    broker = JobBroker(
        StreamsConfig(
            redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            consumer_name="video-chain",
        )
    )
    await broker.connect()
    try:
        next_env = TaskEnvelope(
            service=ServiceName.data_embedding,
            status=TaskStatus.pending,
            input_refs=[manifest_url],
            output=OutputSpec(),
            asset_id=asset_id,
            idempotency_key=f"{asset_id}:data_embedding",
            payload={"process_dir_rel": process_rel.as_posix(), "stage": "embed"},
        )
        await record_job_pending(next_env)
        await broker.publish_ingress(next_env)
    finally:
        await broker.close()

    return TaskResult(
        job_id=env.job_id,
        service=env.service,
        status=TaskStatus.completed,
        asset_id=asset_id,
        output_refs=[manifest_url],
    )
