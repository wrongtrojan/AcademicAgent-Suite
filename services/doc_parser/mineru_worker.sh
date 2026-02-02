#!/bin/bash

# 1. 严格获取项目根目录绝对路径
SCRIPT_PATH=$(readlink -f "$0")
SCRIPT_DIR=$(dirname "$SCRIPT_PATH")
PROJECT_ROOT=$(cd "$SCRIPT_DIR/../../" && pwd)

# 2. 修正路径：使用中划线 magic-pdf.json
PROJECT_CONFIG="$PROJECT_ROOT/configs/magic-pdf.json"
HOME_CONFIG="$HOME/magic-pdf.json"

echo "--- Expert: DocParser (MinerU) Smart & Clean ---"
echo "[Debug] Project Root: $PROJECT_ROOT"

# 3. 物理复制逻辑
if [ ! -f "$PROJECT_CONFIG" ]; then
    echo "[Error] Cannot find $PROJECT_CONFIG"
    echo "Please verify the file exists in AcademicAgent-Suite/configs/"
    exit 1
fi

# 复制到家目录，确保 MinerU 能够读取
cp "$PROJECT_CONFIG" "$HOME_CONFIG"
echo "[Status] Config deployed to $HOME_CONFIG"

# 【核心功能】设置退出清理陷阱：脚本结束、报错或被中断时，自动删除家目录文件
trap 'rm -f "$HOME_CONFIG"; echo "[Status] Cleanup: Removed $HOME_CONFIG from home.";' EXIT

# 4. 从 model_config.yaml 读取路径 [cite: 79]
CONFIG_YAML="$PROJECT_ROOT/configs/model_config.yaml"
RAW_DIR=$(yq e '.paths.raw_storage' "$CONFIG_YAML")/PDF
PROCESSED_DIR=$(yq e '.paths.processed_storage' "$CONFIG_YAML")
CONDA_ENV_PY=$(yq e '.environments.doc_parser' "$CONFIG_YAML")
MAGIC_PDF_BIN=$(dirname "$CONDA_ENV_PY")/magic-pdf

# 5. 增量扫描逻辑 [cite: 112, 113]
shopt -s nullglob
pdf_files=("$RAW_DIR"/*.pdf)

if [ ${#pdf_files[@]} -eq 0 ]; then
    echo "[Exit] No PDF files found in $RAW_DIR"
    exit 0
fi

for pdf in "${pdf_files[@]}"; do
    filename_no_ext=$(basename "$pdf" .pdf)
    
    # 判定去重路径：匹配 /storage/processed/magic-pdf/文件名/ocr 
    CHECK_PATH="$PROCESSED_DIR/magic-pdf/$filename_no_ext/ocr"
    
    if [ -d "$CHECK_PATH" ]; then
        echo "[Skip] $filename_no_ext already processed. Skipping..."
        continue
    fi

    echo "------------------------------------------------"
    echo "[Task] Processing: $filename_no_ext"

    # 执行 OCR 解析 [cite: 15]
    "$MAGIC_PDF_BIN" pdf --pdf "$pdf" --method ocr
    
    if [ $? -eq 0 ]; then
        echo "[Success] Finished: $filename_no_ext"
    else
        echo "[Error] Failed to process $filename_no_ext"
    fi
done

echo "------------------------------------------------"
echo "--- DocParser Task Completed ---"