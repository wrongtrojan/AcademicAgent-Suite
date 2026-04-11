# GPU worker images

Build **`context: .`** from the **repository root**. CPU Dockerfiles stay under `services/<name>/`; GPU variants override via [`deploy/docker-compose.gpu.yml`](../docker-compose.gpu.yml) (+ optional [`deploy/docker-compose.gpu-bge.yml`](../docker-compose.gpu-bge.yml)).

| Path | Service |
|------|---------|
| `pdf_recognition/Dockerfile.gpu` | MinerU |
| `video_recognition/Dockerfile.gpu` | faster-whisper |
| `visual_inference/Dockerfile.gpu` | Qwen2-VL |
| `data_embedding/Dockerfile.gpu` | BGE on CUDA |

**Run:** `make demo-gpu` or `make demo-gpu-bge`. Details: [`docs/MODELS_AND_GPU.md`](../../docs/MODELS_AND_GPU.md). Optional host pip extras: [`requirements-ml-gpu.txt`](../../requirements-ml-gpu.txt).

```bash
docker build -f deploy/images/pdf_recognition/Dockerfile.gpu -t contextmap-pdf:gpu .
# …other images similarly
```
