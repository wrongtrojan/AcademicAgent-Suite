import os
import sys
import yaml
import json
import logging
from pathlib import Path
from vllm import LLM, SamplingParams
from qwen_vl_utils import process_vision_info

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [VisualExpert] - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("QwenInference")

def load_config():
    current_dir = Path(__file__).resolve().parent
    config_path = current_dir.parent.parent / "configs" / "model_config.yaml"
        
    if not config_path.exists():
        logger.error(f"Configuration file missing: {config_path}")
        raise FileNotFoundError(f"Error: Configuration file not found at: {config_path}: {config_path}")
        
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            logger.info("Configuration loaded successfully.")
            return config
    except Exception as e:
        logger.error(f"Failed to parse config: {e}")
        raise

class VisualExpert:
    def __init__(self, config):
        self.model_path = config['model_paths']['qwen2_vl']
        
        logger.info(f"[VisualExpert] Loading model: {self.model_path}")
        
        self.llm = LLM(
            model=self.model_path,
            trust_remote_code=True,
            max_model_len=8192,
            limit_mm_per_prompt={"image": 4, "video": 1},
            gpu_memory_utilization=0.85,
            dtype="bfloat16"
        )
        self.sampling_params = SamplingParams(
            temperature=0.1, 
            max_tokens=1024,
            top_p=0.9
        )

    def reason(self, prompt, visual_content):
        messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
        
        for item in visual_content:
            if not os.path.exists(item):
                logger.warning(f"Resource not found, skipping: {item}")
                continue
            ext = os.path.splitext(item)[1].lower()
            if ext in ['.jpg', '.jpeg', '.png', '.webp']:
                messages[0]["content"].append({"type": "image", "image": item})
            elif ext in ['.mp4', '.mkv', '.avi', '.mov']:
                messages[0]["content"].append({"type": "video", "video": item})

        prompt_text = self.llm.get_tokenizer().apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        
        image_inputs, video_inputs = process_vision_info(messages)
        mm_data = {}
        if image_inputs is not None: mm_data["image"] = image_inputs
        if video_inputs is not None: mm_data["video"] = video_inputs
        
        outputs = self.llm.generate(
            [{"prompt": prompt_text, "multi_modal_data": mm_data}], 
            sampling_params=self.sampling_params
        )
        return outputs[0].outputs[0].text

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Qwen2-VL Logic Executor")
    parser.add_argument("--image", type=str, help="Path to a single image")
    parser.add_argument("--prompt", type=str, default="Prompt (Default: Please describe the image)")
    parser.add_argument("--files", type=str, help="JSON formatted list of files")
    
    args = parser.parse_args()
    
    try:
        config = load_config()
        expert = VisualExpert(config)
        
        visual_content = []
        if args.image:
            visual_content.append(args.image)
        if args.files:
            visual_content.extend(json.loads(args.files))
            
        if not visual_content:
            raise ValueError("No image or video resources provided")

        result = expert.reason(args.prompt, visual_content)
        
        print("\n--- RESULT_START ---")
        print(json.dumps({"status": "success", "response": result}, ensure_ascii=False))
        print("--- RESULT_END ---")
        
    except Exception as e:
        sys.stderr.write(f"Logic layer crash: {str(e)}\n")
        sys.exit(1)

if __name__ == "__main__":
    main()