import sys
import json
import subprocess
import os
from datetime import datetime
from pathlib import Path

def run_pdf_expert(params):
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = Path(SCRIPT_DIR).resolve().parent.parent
    LOG_DIR = PROJECT_ROOT / "logs"
    LOG_DIR.mkdir(exist_ok=True)
    
    log_file_path = LOG_DIR / "doc_parser.log"
    shell_script = os.path.join(SCRIPT_DIR, "mineru_worker.sh")

    if not os.path.exists(shell_script):
        return {
            "status": "error", 
            "message": f"mineru_worker.sh not found in {SCRIPT_DIR}"
        }

    try:
        with open(log_file_path, "a", encoding="utf-8") as log_file:
            log_file.write(f"\n{'='*20} Task Started: {datetime.now()} {'='*20}\n")
            log_file.flush()
            
            process = subprocess.Popen(
                ["bash", shell_script],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(PROJECT_ROOT),
                bufsize=1
            )
            
            exclude_keywords = [
                "AUG:", "CACHE_DIR:", "CUDNN_BENCHMARK:", "DATALOADER:", 
                "DATASETS:", "GLOBAL:", "ICDAR_DATA_DIR", "INPUT:", 
                "MODEL:", "OUTPUT_DIR:", "SCIHUB_DATA_DIR", "SEED:", 
                "SOLVER:", "TEST:", "VERSION:", "VIS_PERIOD:", "VIT:",
                "detectron2]:", "PyTorch built with:", "DETR:", "ASPECT_RATIO_GROUPING:", 
                "FILTER_EMPTY_ANNOTATIONS:", "NUM_WORKERS:", "REPEAT_THRESHOLD:", 
                "SAMPLER_TRAIN:", "PRECOMPUTED_PROPOSAL_TOPK_TRAIN:", "PROPOSAL_FILES_TRAIN:", 
                "scihub_train", "TRAIN:", "HACK:", "CROP:", "ENABLED:", "SIZE:", 
                "TYPE:", "FORMAT:", "MASK_FORMAT:", "MAX_SIZE_TRAIN:", "MIN_SIZE_TRAIN:", 
                "MIN_SIZE_TRAIN_SAMPLING:", "RANDOM_FLIP:", "ANCHOR_GENERATOR:", "ANGLES:", 
                "ASPECT_RATIOS:", "NAME:", "OFFSET:", "SIZES:", "BACKBONE:", "FREEZE_AT:", 
                "CONFIG_PATH:", "DEVICE:", "FPN:", "FUSE_TYPE:", "IN_FEATURES:", "NORM:", 
                "OUT_CHANNELS:", "IMAGE_ONLY:", "KEYPOINT_ON:", "LOAD_PROPOSALS:", "MASK_ON:", 
                "META_ARCHITECTURE:", "PANOPTIC_FPN:", "COMBINE:", "INSTANCES_CONFIDENCE_THRESH:", 
                "OVERLAP_THRESH:", "STUFF_AREA_LIMIT:", "INSTANCE_LOSS_WEIGHT:", "PIXEL_MEAN:", 
                "PIXEL_STD:", "PROPOSAL_GENERATOR:", "MIN_SIZE:", "RESNETS:", "DEFORM_MODULATED:", 
                "DEFORM_NUM_GROUPS:", "DEFORM_ON_PER_STAGE:", "DEPTH:", "FrozenBN:", "NUM_GROUPS:", 
                "OUT_FEATURES:", "RES2_OUT_CHANNELS:", "RES5_DILATION:", "STEM_OUT_CHANNELS:", 
                "STRIDE_IN_1X1:", "WIDTH_PER_GROUP:", "RETINANET:", "BBOX_REG_LOSS_TYPE:", 
                "BBOX_REG_WEIGHTS:", "FOCAL_LOSS_ALPHA:", "FOCAL_LOSS_GAMMA:", "IOU_LABELS:", 
                "IOU_THRESHOLDS:", "NUM_CLASSES:", "NUM_CONVS:", "PRIOR_PROB:", "SMOOTH_L1_LOSS_BETA:", 
                "ROI_BOX_CASCADE_HEAD:", "IOUS:", "ROI_BOX_HEAD:", "BBOX_REG_LOSS_WEIGHT:", 
                "CLS_AGNOSTIC_BBOX_REG:", "CONV_DIM:", "FC_DIM:", "NUM_CONV:", "NUM_FC:", 
                "POOLER_RESOLUTION:", "POOLER_SAMPLING_RATIO:", "POOLER_TYPE:", "ROIAlignV2:", 
                "SMOOTH_L1_BETA:", "TRAIN_ON_PRED_BOXES:", "ROI_HEADS:", "BATCH_SIZE_PER_IMAGE:", 
                "POSITIVE_FRACTION:", "PROPOSAL_APPEND_GT:", "ROI_KEYPOINT_HEAD:", "CONV_DIMS:", 
                "LOSS_WEIGHT:", "MIN_KEYPOINTS_PER_IMAGE:", "NORMALIZE_LOSS_BY_VISIBLE_KEYPOINTS:", 
                "NUM_KEYPOINTS:", "ROI_MASK_HEAD:", "CLS_AGNOSTIC_MASK:", "RPN:", "BOUNDARY_THRESH:", 
                "HEAD_NAME:", "NMS_THRESH:", "POST_NMS_TOPK_TRAIN:", "PRE_NMS_TOPK_TRAIN:", 
                "SEM_SEG_HEAD:", "COMMON_STRIDE:", "CONVS_DIM:", "IGNORE_VALUE:", "SemSegFPNHead:", 
                "GN:", "DROP_PATH:", "IMG_SIZE:", "layoutlmv3_base:", "POS_TYPE:", "WEIGHTS:", 
                "AMP:", "BACKBONE_MULTIPLIER:", "BASE_LR:", "BIAS_LR_FACTOR:", "CHECKPOINT_PERIOD:", 
                "CLIP_GRADIENTS:", "CLIP_TYPE:", "CLIP_VALUE:", "NORM_TYPE:", "GAMMA:", 
                "GRADIENT_ACCUMULATION_STEPS:", "IMS_PER_BATCH:", "LR_SCHEDULER_NAME:", 
                "MAX_ITER:", "MOMENTUM:", "NESTEROV:", "OPTIMIZER:", "REFERENCE_WORLD_SIZE:", 
                "STEPS:", "WARMUP_FACTOR:", "WARMUP_ITERS:", "WARMUP_METHOD:", "WEIGHT_DECAY:", 
                "WEIGHT_DECAY_BIAS:", "WEIGHT_DECAY_NORM:", "FLIP:", "MAX_SIZE:", "MIN_SIZES:", 
                "DETECTIONS_PER_IMAGE:", "EVAL_PERIOD:", "EXPECTED_RESULTS:", "KEYPOINT_OKS_SIGMAS:", 
                "PRECISE_BN:", "NUM_ITER:", "VIS_PERIOD:", "GCC", "C++ Version", "Intel(R)", 
                "MKL-DNN", "OpenMP", "LAPACK", "NNPACK", "CPU capability", "CUDA Runtime", 
                "NVCC", "CuDNN", "Magma", "Build settings",
                "- 384", "- 600", "- 480", "- 512", "- 544", "- 576", "- 608", "- 640", 
                "- 672", "- 704", "- 736", "- 768", "- 800", "- -90", "- 0", "- 90", 
                "- 0.5", "- 1.0", "- 2.0", "- 32", "- 64", "- 128", "- 256", "layer3", 
                "layer5", "layer7", "layer11", "- 127.5", "false", "res4", "p3", "p4", 
                "p5", "p6", "p7", "- -1", "- 1", "- 0.4", "- 10.0", "- 5.0", "- 20.0", 
                "- 30.0", "- 15.0", "- 0.6", "- 0.7", "p2", "ROIAlignV2", "512", "- -1", 
                "- 0.3", "224", "10000", "400", "500", "700", "900", "1100", "1200"
            ]
            
            for line in process.stdout:
                if not any(kw in line for kw in exclude_keywords):
                    log_file.write(line)
                    log_file.flush()
            
            process.wait()

        if process.returncode == 0:
            return {
                "status": "success",
                "log_file": str(log_file_path),
                "message": "DocParser task completed successfully"
            }
        else:
            return {
                "status": "error",
                "message": f"Shell script failed, exit code: {process.returncode}",
                "log_file": str(log_file_path)
            }

    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    input_str = sys.argv[1] if len(sys.argv) > 1 else "{}"
    try:
        params = json.loads(input_str)
        response = run_pdf_expert(params)
        print(json.dumps(response))
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}))