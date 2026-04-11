# Models, GPU, and concurrency

This document describes how **heavy workers** (PDF, video, visual) use NVIDIA GPUs, where **model weights** are stored, and how that relates to **`service_manager`** concurrency limits.

## Compose overlays

**Heavy inference (PDF / video / visual):** main stack plus [`deploy/docker-compose.gpu.yml`](../deploy/docker-compose.gpu.yml):

```bash
make demo-gpu
# or: docker compose -f docker-compose.yml -f deploy/docker-compose.gpu.yml --env-file .env up -d
```

**BGE embeddings on GPU:** add the optional third file [`deploy/docker-compose.gpu-bge.yml`](../deploy/docker-compose.gpu-bge.yml) (after the GPU overlay so named volumes and service images stay aligned):

```bash
make demo-gpu-bge
# or: docker compose -f docker-compose.yml -f deploy/docker-compose.gpu.yml -f deploy/docker-compose.gpu-bge.yml --env-file .env up -d
```

That rebuilds `data_embedding` with [`deploy/images/data_embedding/Dockerfile.gpu`](../deploy/images/data_embedding/Dockerfile.gpu), sets `EMBEDDING_BACKEND=bge`, `EMBEDDING_DEVICE=cuda`, and mounts the same HF/torch cache volumes. The overlay also sets `CONTEXTMAP_LIMIT_DATA_EMBEDDING` default to **1** on `service_manager` to reduce parallel BGE pressure on a single GPU.

**Retrieval:** for [`mixture_searching`](../services/mixture_searching/worker/processor.py) semantic search quality, run **`mixture_searching`** with **BGE-backed embeddings** in the same stack. If `data_embedding` still uses `EMBEDDING_BACKEND=hash` while the rest of the pipeline runs on GPU, search can look weak or inconsistent versus true dense vectors.

Named volumes (survive image rebuilds):

| Volume | Mount (typical) | Used for |
|--------|-----------------|----------|
| `hf_model_cache` | `/models/hf` | `HF_HOME`, Hugging Face hub cache |
| `torch_model_cache` | `/models/torch` | `TORCH_HOME` |
| `whisper_cache` | `/models/whisper` | faster-whisper CTranslate2 models (`WHISPER_CACHE`) |

Environment variables are set in `deploy/docker-compose.gpu.yml`; copy hints from the repository root `.env.example`.

## Per-service behavior

### PDF (`pdf_recognition`)

- **Image:** `deploy/images/pdf_recognition/Dockerfile.gpu` (see `deploy/images/README.md`).
- **Runtime:** [`mineru_runner.py`](../services/pdf_recognition/worker/mineru_runner.py) runs `python -m mineru` when `MINERU_MODE` allows it (`auto` is typical).
- **VRAM:** depends on document complexity and MinerU pipeline; treat **one concurrent PDF job per GPU** as the safe default until you profile your hardware.

### Video (`video_recognition`)

- **Image:** `deploy/images/video_recognition/Dockerfile.gpu` — includes **faster-whisper**.
- **Env:** `VIDEO_WHISPER=1`, `WHISPER_BACKEND=auto|faster|openai`, `WHISPER_MODEL` (e.g. `base`, `small`, `large-v3`), `WHISPER_DEVICE` (`cuda` / `cpu`), `WHISPER_COMPUTE_TYPE` (e.g. `float16`, `int8_float16`).
- **CPU stack:** without the GPU image, `WHISPER_BACKEND=openai` or the `whisper` CLI can still be used if installed.

### Visual (`visual_inference`)

- **Image:** `deploy/images/visual_inference/Dockerfile.gpu`.
- **Local VLM:** `VISUAL_BACKEND=local` and `QWEN_VL_MODEL_ID` (default in GPU compose: `Qwen/Qwen2-VL-2B-Instruct`).
- **Optional:** `QWEN_VL_TORCH_DTYPE` (`bfloat16` / `float16`), `VISUAL_MAX_PIXELS`, `VISUAL_MAX_NEW_TOKENS`.
- **API path:** `VISUAL_BACKEND=api` with `OPENAI_API_KEY` (or legacy `VISUAL_USE_VLM=1` when `VISUAL_BACKEND` is unset).

### Embeddings (`data_embedding`)

- **Default** [`deploy/docker-compose.gpu.yml`](../deploy/docker-compose.gpu.yml) does **not** switch `data_embedding` to CUDA (keeps the slim CPU image unless you add another override).
- **BGE + GPU:** use [`deploy/docker-compose.gpu-bge.yml`](../deploy/docker-compose.gpu-bge.yml) as above, or set `EMBEDDING_BACKEND=bge` and `EMBEDDING_DEVICE` yourself when running a custom stack.
- **Env:** [`shared/embedding.py`](../shared/embedding.py) reads **`EMBEDDING_DEVICE`** (`cuda`, `cpu`, `cuda:0`, …); unset means sentence-transformers chooses the device (legacy auto).

## Two layers of resource control

1. **Docker Compose** — which containers see a GPU (`count: 1` vs `all`), how many **replicas** you run, and **startup order** (`depends_on` + health checks in the root `docker-compose.yml`).
2. **`ServiceResourceGate`** in [`core/service_manager.py`](../core/service_manager.py) — **per-process** semaphores that cap how many jobs are routed to each work stream at once.

If Compose allows two `pdf_recognition` replicas on one GPU while the gate allows 2 parallel PDF jobs, you can still **OOM**. Align these deliberately.

### Environment overrides for gates

Set on the **`service_manager`** service (the GPU compose file sets conservative defaults):

| Variable | Default (GPU compose) | Maps to |
|----------|----------------------|---------|
| `CONTEXTMAP_LIMIT_PDF_RECOGNITION` | `1` | `pdf_recognition` |
| `CONTEXTMAP_LIMIT_VIDEO_RECOGNITION` | `1` | `video_recognition` |
| `CONTEXTMAP_LIMIT_DATA_EMBEDDING` | `2` in base GPU overlay; **`1` default** when using [`docker-compose.gpu-bge.yml`](../deploy/docker-compose.gpu-bge.yml) | `data_embedding` |
| `CONTEXTMAP_LIMIT_VISUAL_INFERENCE` | `1` | `visual_inference` |

Other services use defaults from [`ServiceLimits.default()`](../shared/resource/semaphore.py) unless overridden with `CONTEXTMAP_LIMIT_<ENUM_NAME>` (enum name is uppercase with underscores, e.g. `CONTEXTMAP_LIMIT_LLM_CALLING`).

### Reference: defaults vs GPU-oriented suggestion

| Service | Code default | Typical GPU note |
|---------|----------------|------------------|
| `pdf_recognition` | 2 | **1** if one job fills VRAM |
| `video_recognition` | 1 | 1 |
| `data_embedding` | 4 | Lower if BGE on GPU |
| `visual_inference` | 2 | **1** for large VLMs |

## Version matrix (sanity check)

Images are based on **`pytorch/pytorch:2.4.1-cuda12.1-cudnn9-runtime`**. Use PyTorch / CUDA wheels that match that runtime when adding dependencies. Re-pin in Dockerfiles if you change the base image.

## First-time model download

Weights are **not** baked into images by default. After `up`, first inference may download several GB into the named volumes. Optional preload:

```bash
./scripts/warm_models.sh 'Qwen/Qwen2-VL-2B-Instruct'
```

Run inside a worker container with the same volume mounts and `HF_HOME` as in compose, or from the host with `HF_HOME` pointing at a cache directory.

## Troubleshooting

- **`nvidia-smi` empty in container:** check `nvidia-container-toolkit` and that the GPU compose file is applied.
- **OOM during PDF or VLM:** reduce `CONTEXTMAP_LIMIT_*`, set **replicas to 1** for that service, or use a smaller model / `VISUAL_MAX_PIXELS`.
- **Whisper slow on CPU:** use the GPU video image and `WHISPER_DEVICE=cuda`, or a smaller `WHISPER_MODEL`.
