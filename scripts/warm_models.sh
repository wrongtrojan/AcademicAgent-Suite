#!/usr/bin/env bash
# Optional: preload Hugging Face weights into the cache (same HF_HOME as in compose).
# Usage:
#   ./scripts/warm_models.sh [MODEL_ID] [MODEL_ID...]
# Example:
#   HF_HOME=/models/hf ./scripts/warm_models.sh Qwen/Qwen2-VL-2B-Instruct
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <huggingface_model_id> [more_ids...]" >&2
  exit 1
fi

for mid in "$@"; do
  echo "Downloading: ${mid}"
  HF_WARM_MODEL_ID="${mid}" python3 -c '
import os
import sys
try:
    from huggingface_hub import snapshot_download
except ImportError:
    print("Install huggingface_hub: pip install huggingface_hub", file=sys.stderr)
    sys.exit(1)
snapshot_download(os.environ["HF_WARM_MODEL_ID"])
'
done
