#!/bin/bash

# Define colors for log levels
INFO='\033[0;34m'
SUCCESS='\033[0;32m'
WARN='\033[1;33m'
ERROR='\033[0;31m'
NC='\033[0m'

echo -e "${INFO}[1/4] Upgrading ModelScope Library...${NC}"
pip install --upgrade modelscope

# Navigate to your pre-existing models directory
# Adjust this path if the script is not run from the parent folder
cd models || { echo -e "${ERROR}Error: 'models' directory not found.${NC}"; exit 1; }

echo -e "${INFO}[2/4] Downloading Model Weights...${NC}"

# Helper function for ModelScope downloads
fetch_ms() {
    local repo=$1
    local target=$2
    echo -e "${INFO}Downloading ${repo} into ./${target}...${NC}"
    python3 -c "from modelscope import snapshot_download; snapshot_download('$repo', local_dir='./$target')"
}

# Execution
fetch_ms 'AI-ModelScope/clip-vit-large-patch14' 'clip'
fetch_ms 'Systran/faster-whisper-large-v3' 'whisper_v3'
fetch_ms 'qwen/Qwen2-VL-7B-Instruct' 'qwen2_vl'
fetch_ms 'opendatalab/PDF-Extract-Kit-1.0' 'miner_u'

echo -e "${INFO}[3/4] Reorganizing MinerU Structure...${NC}"
# Specifically targeting the sub-path you mentioned
if [ -d "miner_u/models" ]; then
    pushd miner_u/models > /dev/null

    # Layout adjustment
    if [ -d "Layout/LayoutLMv3" ]; then
        echo -e "${INFO}Relocating LayoutLMv3 files...${NC}"
        mv Layout/LayoutLMv3/config.json Layout/ 2>/dev/null
        mv Layout/LayoutLMv3/model_final.pth Layout/ 2>/dev/null
        rm -rf Layout/LayoutLMv3/
    fi

    # MFD adjustment
    if [ -d "MFD/YOLO" ]; then
        echo -e "${INFO}Relocating MFD weights...${NC}"
        mv MFD/YOLO/yolo_v8_ft.pt MFD/weights.pt 2>/dev/null
        rm -rf MFD/YOLO/
    fi

    popd > /dev/null
else
    echo -e "${WARN}Warning: miner_u/models not found. Check download status.${NC}"
fi

echo -e "${INFO}[4/4] Handling DINOv2 Weights...${NC}"
cd dinov2
if [ ! -f "dinov2_vitl14_pretrain.pth" ]; then
    echo -e "${INFO}Fetching DINOv2 via curl...${NC}"
    curl -L -C - -O https://dl.fbaipublicfiles.com/dinov2/dinov2_vitl14/dinov2_vitl14_pretrain.pth
else
    echo -e "${SUCCESS}DINOv2 weights already exist. Skipping.${NC}"
fi

echo -e "${SUCCESS}--------------------------------------------------${NC}"
echo -e "${SUCCESS}All models are downloaded and organized!${NC}"
echo -e "${SUCCESS}--------------------------------------------------${NC}"