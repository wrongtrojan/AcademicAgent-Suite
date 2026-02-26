import os
import sys
import json
import yaml
import httpx
import asyncio
import dotenv
import traceback
from pathlib import Path
from datetime import datetime

# 加载环境变量
dotenv.load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

from core.assets_manager import AcademicAsset, AssetType
from core.prompts_manager import PromptManager

# --- 基础日志函数 ---
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
log_file_path = LOG_DIR / "structure_generate.log"

def log_message(level, msg):
    """最基础的日志重定向：同时打印到控制台并追加到文件"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
    formatted_msg = f"{timestamp} - [StructureGen] - {level} - {msg}"
    
    # 输出到控制台
    print(formatted_msg)
    
    # 追加到文件
    with open(log_file_path, "a", encoding="utf-8") as f:
        f.write(formatted_msg + "\n")

class StructureGenerator:
    def __init__(self, global_cfg_path="configs/model_config.yaml"):
        self.project_root = PROJECT_ROOT
        
        # 加载配置
        config_path = self.project_root / global_cfg_path
        if not config_path.exists():
            log_message("ERROR", f"Config file not found: {config_path}")
            raise FileNotFoundError(f"Config file not found: {config_path}")
            
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
            
        # 初始化 Prompt Manager
        self.prompt_manager = PromptManager()
        
        # API 配置
        llm_cfg = self.config.get("llm", {})
        self.api_url = llm_cfg.get("api_url", "https://api.deepseek.com/v1/chat/completions")
        self.api_key = os.getenv("DEEPSEEK_API_KEY")

    def _extract_context(self, asset: AcademicAsset) -> str:
        """从处理后的文件中提取文本内容作为 LLM 上下文"""
        processed_root = Path(self.config['paths']['processed_storage'])
        
        try:
            if asset.asset_type == AssetType.PDF:
                clean_id = asset.asset_id.replace(".pdf", "")
                base_path = processed_root / "magic-pdf" / clean_id
                content_path = base_path / "ocr" / f"{clean_id}_content_list.json"
                if not content_path.exists():
                    raise FileNotFoundError(f"Missing processed PDF content (middle.json) for {asset.asset_id}")
                
                with open(content_path, 'r', encoding='utf-8') as f:
                    content_to_send = json.load(f)
                return json.dumps(content_to_send, ensure_ascii=False)[:50000] 

            elif asset.asset_type == AssetType.VIDEO:
                transcript_path = processed_root / "video" / asset.asset_id / "transcript.json"
                if not transcript_path.exists():
                    raise FileNotFoundError(f"Missing transcript for video {asset.asset_id}")
                
                with open(transcript_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    segments = data.get("segments", [])
                    return "\n".join([f"[{s['start']}s]: {s['text']}" for s in segments])[:50000]
        except Exception as e:
            log_message("ERROR", f"Context extraction failed for {asset.asset_id}: {str(e)}")
            raise

        return ""

    async def generate_outline(self, asset: AcademicAsset):
        """渲染 Prompt 并调用 DeepSeek API"""
        log_message("INFO", f"Starting structure generation for asset: {asset.asset_id}")
        
        try:
            context = self._extract_context(asset)
            
            # 渲染 Prompt
            prompt = self.prompt_manager.render(
                "structural_outline", 
                raw_context=context, 
                asset_type=asset.asset_type.value
            )

            log_message("INFO", f"Sending request to DeepSeek for asset: {asset.asset_id}")
            
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    self.api_url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": "deepseek-chat",
                        "messages": [
                            {"role": "system", "content": "You are a professional academic assistant. Return results in JSON format."},
                            {"role": "user", "content": prompt}
                        ],
                        "response_format": {"type": "json_object"}
                    }
                )
                response.raise_for_status()
                res_data = response.json()
                outline_content = json.loads(res_data['choices'][0]['message']['content'])
                
                # 确定保存路径
                processed_root = Path(self.config['paths']['processed_storage'])
                if asset.asset_type == AssetType.PDF:
                    clean_id = asset.asset_id.replace(".pdf", "")
                    save_dir = processed_root / "magic-pdf" / clean_id
                else:
                    save_dir = processed_root / "video" / asset.asset_id
                save_dir.mkdir(parents=True, exist_ok=True)
                save_path = save_dir / "summary_outline.json"
                
                result_payload = {
                    "asset_id": asset.asset_id,
                    "generated_at": datetime.now().isoformat(),
                    "outline": outline_content
                }
                
                with open(save_path, 'w', encoding='utf-8') as f:
                    json.dump(result_payload, f, ensure_ascii=False, indent=4)
                
                log_message("INFO", f"Successfully generated outline for {asset.asset_id}. Saved to: {save_path}")
                return {
                    "status": "success",
                    "save_path": str(save_path),
                    "asset_id": asset.asset_id
                }

        except Exception as e:
            log_message("ERROR", f"DeepSeek call or processing failed for {asset.asset_id}: {str(e)}")
            log_message("DEBUG", traceback.format_exc())
            return {"status": "error", "message": str(e), "asset_id": asset.asset_id}

async def run_structure_generate(asset: AcademicAsset):
    """外部调用的异步包装器"""
    generator = StructureGenerator()
    return await generator.generate_outline(asset)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        try:
            asset_data = json.loads(sys.argv[1])
            asset_obj = AcademicAsset.from_dict(asset_data)
            
            result = asyncio.run(run_structure_generate(asset_obj))
            print(json.dumps(result))
        except Exception as e:
            log_message("ERROR", f"CLI execution error: {str(e)}")
            print(json.dumps({"status": "error", "message": f"CLI execution error: {str(e)}"}))