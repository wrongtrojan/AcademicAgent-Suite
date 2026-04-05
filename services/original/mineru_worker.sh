#!/bin/bash

# 1. 参数校验
if [ "$#" -ne 2 ]; then
    echo "[Usage] $0 <asset_id> <pdf_path>"
    exit 1
fi

ASSET_ID=$1
PDF_PATH=$2

SCRIPT_PATH=$(readlink -f "$0")
SCRIPT_DIR=$(dirname "$SCRIPT_PATH")
# 定位项目根目录
PROJECT_ROOT=$(cd "$SCRIPT_DIR/../../" && pwd)

PROJECT_CONFIG="$PROJECT_ROOT/configs/magic-pdf.json"
HOME_CONFIG="$HOME/magic-pdf.json"
CONFIG_YAML="$PROJECT_ROOT/configs/model_config.yaml"

echo "--- Expert: DocParser (MinerU) Single Worker Mode ---"

# 2. 配置文件部署与自动清理逻辑 (参照备份脚本使用 trap)
if [ ! -f "$PROJECT_CONFIG" ]; then
    echo "[Error] Cannot find $PROJECT_CONFIG"
    exit 1
fi

cp "$PROJECT_CONFIG" "$HOME_CONFIG"
echo "[Status] Config deployed to $HOME_CONFIG"

# 确保脚本退出时清理环境，无论成功或失败
trap 'rm -f "$HOME_CONFIG"; echo "[Status] Cleanup: Removed $HOME_CONFIG from home.";' EXIT

# 3. 环境与路径解析 (参照备份脚本的 Key 值)
CONDA_ENV_PY=$(yq e '.environments.doc_recognize' "$CONFIG_YAML")
MAGIC_PDF_BIN=$(dirname "$CONDA_ENV_PY")/magic-pdf

# 检查二进制文件是否存在
if [ ! -f "$MAGIC_PDF_BIN" ]; then
    echo "[Error] magic-pdf binary not found at $MAGIC_PDF_BIN"
    echo "[Debug] Please check .environments.doc_recognize in model_config.yaml"
    exit 1
fi

echo "[Task] Processing Asset: $ASSET_ID"
echo "[Path] Source: $PDF_PATH"

# 4. 执行转换 (参照备份脚本调用逻辑，不手动指定 --output_dir)
# MinerU 会根据 magic-pdf.json 中的配置自动决定输出位置
"$MAGIC_PDF_BIN" pdf --pdf "$PDF_PATH" --method ocr

EXIT_CODE=$?

# 5. 结果返回
if [ $EXIT_CODE -eq 0 ]; then
    echo "[Success] Asset $ASSET_ID processed."
    exit 0
else
    echo "[Error] MinerU failed with exit code $EXIT_CODE"
    exit 1
fi