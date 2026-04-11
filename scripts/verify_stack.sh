#!/usr/bin/env bash
# Stack verification: Postgres + Redis (+ optional Gateway, workers, upload/sync, status poll).
#
# Usage:
#   ./scripts/verify_stack.sh
#       postgres + redis only
#   VERIFY_GATEWAY=1 ./scripts/verify_stack.sh
#       + gateway build/up + GET /api/v1/health
#   VERIFY_GATEWAY=1 VERIFY_UPLOAD=1 ./scripts/verify_stack.sh
#       + POST minimal PDF + sync (asset may stay "recognizing" without workers)
#   VERIFY_GATEWAY=1 VERIFY_UPLOAD=1 VERIFY_WORKERS=1 ./scripts/verify_stack.sh
#       + service_manager + pdf_recognition + data_embedding + data_ingesting
#   VERIFY_STATUS=1 …
#       after upload/sync, poll GET …/status/single_asset until Ready or Failed (needs workers for Ready)
#
# GPU compose overlays (merge order: base → gpu.yml → optional gpu-bge.yml):
#   VERIFY_GPU=1
#       add -f deploy/docker-compose.gpu.yml (MinerU / faster-whisper / Qwen-VL images + NVIDIA)
#   VERIFY_BGE_GPU=1   (alias: VERIFY_EMBED_GPU=1)
#       add deploy/docker-compose.gpu.yml + deploy/docker-compose.gpu-bge.yml (BGE on GPU for data_embedding)
#       implies the same heavy-worker images/volumes as VERIFY_GPU for consistency.
#
# Optional GPU host/container checks (after workers if VERIFY_WORKERS=1):
#   VERIFY_NVIDIA=1           run nvidia-smi on the host (fails soft if missing)
#   VERIFY_GPU_CONTAINER=1   docker exec pdf_recognition nvidia-smi
#   VERIFY_MINERU_IMPORT=1   docker exec pdf_recognition python -c "import mineru"
#
# Tunables: VERIFY_STATUS_TIMEOUT_SEC (default 300), VERIFY_STATUS_INTERVAL_SEC (default 5)
# Compose project: COMPOSE_PROJECT_NAME (default contextmap).
# Base compose: repo root docker-compose.yml (override with COMPOSE_FILE).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT/docker-compose.yml}"
export COMPOSE_FILE
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-contextmap}"

COMPOSE_ARGS=(-f "$COMPOSE_FILE")
if [ "${VERIFY_BGE_GPU:-0}" = "1" ] || [ "${VERIFY_EMBED_GPU:-0}" = "1" ]; then
  COMPOSE_ARGS+=(-f "$ROOT/deploy/docker-compose.gpu.yml" -f "$ROOT/deploy/docker-compose.gpu-bge.yml")
elif [ "${VERIFY_GPU:-0}" = "1" ]; then
  COMPOSE_ARGS+=(-f "$ROOT/deploy/docker-compose.gpu.yml")
fi

cd "$ROOT"

echo "[verify_stack] compose files: ${COMPOSE_ARGS[*]} (project: $COMPOSE_PROJECT_NAME)"

if [ "${VERIFY_NVIDIA:-0}" = "1" ]; then
  if command -v nvidia-smi >/dev/null 2>&1; then
    echo "[verify_stack] VERIFY_NVIDIA=1 — host nvidia-smi:"
    nvidia-smi || true
  else
    echo "[verify_stack] VERIFY_NVIDIA=1 but nvidia-smi not on PATH — skip." >&2
  fi
fi

docker compose "${COMPOSE_ARGS[@]}" up -d postgres redis

echo "[verify_stack] Waiting for postgres and redis to accept connections..."
for i in $(seq 1 60); do
  if docker compose "${COMPOSE_ARGS[@]}" exec -T postgres pg_isready -U contextmap -d contextmap >/dev/null 2>&1 \
    && docker compose "${COMPOSE_ARGS[@]}" exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; then
    echo "[verify_stack] Postgres and Redis are up."
    break
  fi
  if [ "$i" -eq 60 ]; then
    echo "[verify_stack] Timeout waiting for postgres/redis." >&2
    docker compose "${COMPOSE_ARGS[@]}" ps
    exit 1
  fi
  sleep 2
done

if [ "${VERIFY_GATEWAY:-0}" != "1" ]; then
  echo "[verify_stack] VERIFY_GATEWAY!=1 — skipping gateway. Set VERIFY_GATEWAY=1 to test HTTP."
  exit 0
fi

echo "[verify_stack] Building and starting gateway (depends on postgres + redis)..."
docker compose "${COMPOSE_ARGS[@]}" up -d --build gateway

echo "[verify_stack] Waiting for gateway health..."
GATEWAY_URL="${GATEWAY_URL:-http://127.0.0.1:8000}"
for i in $(seq 1 60); do
  if curl -fsS "$GATEWAY_URL/api/v1/health" | grep -q '"status"'; then
    echo "[verify_stack] Gateway health OK: $GATEWAY_URL/api/v1/health"
    break
  fi
  if [ "$i" -eq 60 ]; then
    echo "[verify_stack] Gateway health check failed." >&2
    docker compose "${COMPOSE_ARGS[@]}" logs gateway --tail 80 || true
    exit 1
  fi
  sleep 2
done

if [ "${VERIFY_WORKERS:-0}" = "1" ]; then
  echo "[verify_stack] Starting pipeline workers (service_manager, pdf_recognition, data_embedding, data_ingesting)..."
  docker compose "${COMPOSE_ARGS[@]}" up -d --build \
    service_manager \
    pdf_recognition \
    data_embedding \
    data_ingesting
  sleep 3
  docker compose "${COMPOSE_ARGS[@]}" ps service_manager pdf_recognition data_embedding data_ingesting || true

  if [ "${VERIFY_GPU_CONTAINER:-0}" = "1" ]; then
    if [ "${VERIFY_GPU:-0}" = "1" ] || [ "${VERIFY_BGE_GPU:-0}" = "1" ] || [ "${VERIFY_EMBED_GPU:-0}" = "1" ]; then
    echo "[verify_stack] VERIFY_GPU_CONTAINER=1 — pdf_recognition nvidia-smi:"
    docker compose "${COMPOSE_ARGS[@]}" exec -T pdf_recognition nvidia-smi || echo "[verify_stack] nvidia-smi in container failed (no GPU?)." >&2
    fi
  fi
  if [ "${VERIFY_MINERU_IMPORT:-0}" = "1" ]; then
    if [ "${VERIFY_GPU:-0}" = "1" ] || [ "${VERIFY_BGE_GPU:-0}" = "1" ] || [ "${VERIFY_EMBED_GPU:-0}" = "1" ]; then
    echo "[verify_stack] VERIFY_MINERU_IMPORT=1 — import mineru in pdf_recognition:"
    docker compose "${COMPOSE_ARGS[@]}" exec -T pdf_recognition python -c "import mineru" \
      || echo "[verify_stack] import mineru failed (image/deps?)." >&2
    fi
  fi
fi

if [ "${VERIFY_UPLOAD:-0}" != "1" ]; then
  echo "[verify_stack] VERIFY_UPLOAD!=1 — skipping upload smoke."
  exit 0
fi

FIXTURE="$ROOT/scripts/fixtures/minimal.pdf"
if [ ! -f "$FIXTURE" ]; then
  echo "[verify_stack] Missing fixture $FIXTURE — skipping upload." >&2
  exit 0
fi

echo "[verify_stack] POST upload smoke (minimal PDF)..."
RESP="$(curl -fsS -X POST "$GATEWAY_URL/api/v1/upload/file" -F "file=@$FIXTURE;type=application/pdf")"
echo "$RESP" | head -c 400
echo
if ! echo "$RESP" | grep -q 'asset_id'; then
  echo "[verify_stack] Unexpected upload response." >&2
  exit 1
fi

ASSET_ID="$(printf '%s' "$RESP" | python3 -c "import json,sys; print(json.load(sys.stdin)['asset_id'])")"
echo "[verify_stack] POST /api/v1/assets/sync?asset_id=$ASSET_ID ..."
SYNC="$(curl -fsS -X POST "$GATEWAY_URL/api/v1/assets/sync?asset_id=${ASSET_ID}")"
echo "$SYNC" | head -c 400
echo
if ! echo "$SYNC" | grep -qE 'success|job_id|queued'; then
  echo "[verify_stack] Unexpected sync response." >&2
  exit 1
fi

if [ "${VERIFY_STATUS:-0}" != "1" ]; then
  echo "[verify_stack] VERIFY_STATUS!=1 — not polling asset status. Set VERIFY_STATUS=1 to wait for Ready/Failed."
  echo "[verify_stack] Done."
  exit 0
fi

if [ "${VERIFY_WORKERS:-0}" != "1" ]; then
  echo "[verify_stack] Warning: VERIFY_STATUS=1 but VERIFY_WORKERS!=1 — pipeline workers may not be running; status may not reach Ready." >&2
fi

TIMEOUT="${VERIFY_STATUS_TIMEOUT_SEC:-300}"
INTERVAL="${VERIFY_STATUS_INTERVAL_SEC:-5}"
echo "[verify_stack] Polling asset status (timeout ${TIMEOUT}s, interval ${INTERVAL}s)..."
deadline=$(( $(date +%s) + TIMEOUT ))
while true; do
  NOW="$(date +%s)"
  if [ "$NOW" -ge "$deadline" ]; then
    echo "[verify_stack] Timeout waiting for terminal asset status." >&2
    curl -fsS "$GATEWAY_URL/api/v1/status/single_asset?asset_id=${ASSET_ID}" >&2 || true
    exit 1
  fi
  ST_JSON="$(curl -fsS "$GATEWAY_URL/api/v1/status/single_asset?asset_id=${ASSET_ID}")"
  STATUS="$(printf '%s' "$ST_JSON" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('data',{}).get('status',''))")"
  echo "[verify_stack] asset status: ${STATUS:-unknown}"
  if [ "$STATUS" = "Ready" ]; then
    echo "[verify_stack] Asset reached Ready."
    break
  fi
  if [ "$STATUS" = "Failed" ]; then
    echo "[verify_stack] Asset status Failed — see worker logs." >&2
    docker compose "${COMPOSE_ARGS[@]}" logs pdf_recognition --tail 40 >&2 || true
    docker compose "${COMPOSE_ARGS[@]}" logs data_embedding --tail 40 >&2 || true
    docker compose "${COMPOSE_ARGS[@]}" logs data_ingesting --tail 40 >&2 || true
    exit 1
  fi
  sleep "$INTERVAL"
done

echo "[verify_stack] Done."
