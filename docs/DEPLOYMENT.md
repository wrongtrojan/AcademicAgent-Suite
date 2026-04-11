# Deployment notes

## Docker Compose

**Recommended:** copy [`.env.example`](../.env.example) to `.env` at the repository root (single source of truth), then:

```bash
make demo
```

### Postgres 浏览（Pgweb）与命令行

- **Pgweb（推荐）**：Compose 服务 `pgweb` 映射 **`http://localhost:8088`**。浏览器内选表、执行 `SELECT`，按需刷新页面即可查看最新数据（开发/内网使用）。
- **psql**：`make db-psql`（需栈已启动），或  
  `docker compose --env-file .env exec -it postgres psql -U contextmap -d contextmap`

常用 SQL：

```sql
SELECT id, title, type, status, created_at FROM assets ORDER BY created_at DESC LIMIT 50;
SELECT id, title, status FROM sessions ORDER BY created_at DESC LIMIT 20;
```

### 落盘日志（调试）

- 各 Python 服务在设置环境变量 **`LOG_DIR=/var/log/contextmap`** 时，将同格式日志写入**轮转文件**；Compose 已把仓库 **`./logs`** 挂载到该路径。
- 主机上：`tail -f logs/gateway.log`、`tail -f logs/pdf_recognition.log` 等；与响应头 **`X-Request-ID`** 对照网关行中的 `request_id=`。
- 变量 **`LOG_FILE_MAX_BYTES`** / **`LOG_FILE_BACKUP_COUNT`** 可选，见 `.env.example`。

**Raw Compose** (same as `make demo`): from the repo root, Compose auto-loads [`docker-compose.yml`](../docker-compose.yml):

```bash
docker compose --env-file .env up -d
```

GPU/BGE fragments and extra Dockerfiles live under [`deploy/`](deploy/).

### GPU stack (NVIDIA)

For **MinerU**, **faster-whisper**, and **local Qwen2-VL**, add the GPU overlay so workers use CUDA images and named model cache volumes:

```bash
make demo-gpu
# or: docker compose -f docker-compose.yml -f deploy/docker-compose.gpu.yml --env-file .env up -d
```

Requires the NVIDIA driver and [nvidia-container-toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html). See [`docs/MODELS_AND_GPU.md`](MODELS_AND_GPU.md) for model locations, VRAM notes, and **`CONTEXTMAP_LIMIT_*`** tuning on `service_manager`.

**BGE on GPU (optional third overlay):** for dense embeddings in `data_embedding` and better [`mixture_searching`](services/mixture_searching/worker/processor.py) behavior, merge [`deploy/docker-compose.gpu-bge.yml`](deploy/docker-compose.gpu-bge.yml) after the GPU file:

```bash
make demo-gpu-bge
# or: docker compose -f docker-compose.yml -f deploy/docker-compose.gpu.yml -f deploy/docker-compose.gpu-bge.yml --env-file .env up -d
```

Adjust secrets and URLs in `.env`. `PUBLIC_BASE_URL` must be reachable by worker containers that build asset URLs; inside Compose, workers typically use `http://gateway:8000` while browsers use `http://localhost:8000`.

**Environment:** one template [`.env.example`](../.env.example). Optional keys (e.g. `WORKER_CONSUMER`) are commented there; defaults also live in each `services/*/worker/main.py`.

## Existing Postgres volumes: `content_tsv` migration

`deploy/postgres/init.sql` creates `asset_chunks` with the `content_tsv` generated column for full-text search. **New** databases created from that init script already include it.

If you are reusing an **older** data volume created before that column existed, apply the migration manually:

```bash
psql "$DATABASE_URL" -f shared/database/migrations/002_fulltext_embedding.sql
```

Or from the host with Compose:

```bash
docker compose exec -T postgres \
  psql -U contextmap -d contextmap -f - < shared/database/migrations/002_fulltext_embedding.sql
```

(Adjust user/database if your `.env` differs.)

## Stack verification

Script: `scripts/verify_stack.sh` (see header comments for env vars).

| Goal | Command |
|------|---------|
| Only Postgres + Redis | `./scripts/verify_stack.sh` |
| + Gateway HTTP health | `VERIFY_GATEWAY=1 ./scripts/verify_stack.sh` |
| + Upload fixture PDF + sync | `VERIFY_GATEWAY=1 VERIFY_UPLOAD=1 ./scripts/verify_stack.sh` |
| + Start `service_manager`, `pdf_recognition`, `data_embedding`, `data_ingesting` | add `VERIFY_WORKERS=1` |
| + Poll until asset `Ready` or `Failed` | add `VERIFY_STATUS=1` (set `VERIFY_STATUS_TIMEOUT_SEC` / `VERIFY_STATUS_INTERVAL_SEC` if needed) |
| GPU worker images + volumes | set `VERIFY_GPU=1` (merges `deploy/docker-compose.gpu.yml` into root `docker-compose.yml`) |
| + BGE GPU `data_embedding` | set `VERIFY_BGE_GPU=1` (adds `deploy/docker-compose.gpu-bge.yml`; implies GPU stack) |
| Host `nvidia-smi` | `VERIFY_NVIDIA=1` |
| Container GPU check | `VERIFY_GPU_CONTAINER=1` (with `VERIFY_GPU` or `VERIFY_BGE_GPU`) |
| Import `mineru` in PDF worker | `VERIFY_MINERU_IMPORT=1` (with GPU overlays) |

Makefile shortcuts: `make demo` / `make demo-gpu*` to start stacks; `make verify`, `make verify-http`, `make verify-e2e` (CPU compose); `make verify-e2e-gpu` and `make verify-e2e-gpu-bge` for merged compose overlays (see [`scripts/verify_stack.sh`](scripts/verify_stack.sh) header).

**Note:** Reaching `Ready` requires the pipeline workers; without MinerU, PDF recognition falls back to synthetic chunks (`MINERU_MODE` in `.env` — see `.env.example`). First build of worker images can take several minutes.

The script sets `COMPOSE_PROJECT_NAME=contextmap` by default so it does not collide with unrelated containers on the host. Override if you need a fixed project name.

**Workers and `localhost` URLs:** The gateway registers uploads with `PUBLIC_BASE_URL` (often `http://localhost:8000` for browsers). Pipeline workers set `GATEWAY_INTERNAL_ORIGIN=http://gateway:8000` so HTTP fetches rewrite to the gateway container (see `shared/http_utils.rewrite_localhost_gateway_url`).

## Cleaning up stale containers on the host

Containers from **other** Compose projects or old experiments (e.g. `redis-cache` with a broken bind mount to `storage/db_data/redis`, or Milvus-related names) are **not** used by this repo’s default stack (`COMPOSE_PROJECT_NAME=contextmap`). You may remove them if you no longer need them.

- **Remove one container by name:** `docker rm -f redis-cache` (repeat for `milvus-standalone`, `milvus-etcd`, etc. as needed).
- **Remove all stopped containers:** `docker container prune` (review the list when prompted; this affects every stopped container on the machine, not only this project).
- **When bringing up this project’s compose file**, you can drop orphans that belong to the same compose file’s previous runs:  
  `docker compose -p contextmap up -d --remove-orphans`

Deleting a container does **not** delete named volumes (e.g. Postgres data) unless you pass `-v` to `docker rm` or use `docker volume rm`. Only remove volumes if you intend to wipe that data.

## Chunk coordination (PDF / video)

`asset_chunks.coordination` is JSON used for:

- **Structured outline** anchors (`page` or `timestamp_start` / `timestamp`), filled during ingest.
- **Evidence UI** metadata via hybrid search (`shared/evidence_format.py`): PDF `page_label` + optional `bbox` (JSON string); video `timestamp` (seconds).

MinerU / parsers can add **`bbox`** (e.g. normalized or PDF coords) into `coordination` when available; the frontend `PdfViewer` expects a JSON array string in evidence metadata when present.

## Compose services for chat retrieval

For **grounded answers with evidence**, run **`mixture_searching`** (used by `gateway/chat_graph.py` → `hybrid_search`) alongside Gateway and Postgres. Example:

```bash
docker compose up -d mixture_searching
```
