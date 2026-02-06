import subprocess
import json
import os
import yaml
import logging
from pathlib import Path

# 初始化大脑层日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [Brain-Center] - %(levelname)s - %(message)s')
logger = logging.getLogger("ToolsManager")

class ToolsManager:
    def __init__(self, config_path="configs/model_config.yaml"):
        # 定位项目根目录
        self.project_root = Path(__file__).resolve().parent.parent
        full_config_path = self.project_root / config_path
        
        with open(full_config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
        self.envs = self.config.get('environments', {})
        self.base_dir = str(self.project_root)
        logger.info("✅ 学术大脑工具箱已上线：所有专家环境已挂载。")

    def _dispatch_raw(self, env_key, script_rel_path, params=None):
        """通用底层派发逻辑：跨环境调用并捕获最后一行 JSON"""
        python_exe = self.envs.get(env_key)
        if not python_exe or not os.path.exists(python_exe):
            return {"status": "error", "message": f"环境 {env_key} 配置无效或不存在"}

        script_path = os.path.join(self.base_dir, script_rel_path)
        json_params = json.dumps(params if params else {}, ensure_ascii=False)

        try:
            # 执行专家脚本
            result = subprocess.run(
                [python_exe, script_path, json_params],
                capture_output=True,
                text=True,
                cwd=self.base_dir
            )
            
            if result.returncode != 0:
                # 记录错误到大脑日志，但不崩溃
                logger.error(f"❌ 专家 {script_rel_path} 异常退出: {result.stderr}")
                return {"status": "error", "message": "子进程执行失败", "details": result.stderr}

            # 核心：只解析最后一行非空输出作为结果
            output_lines = [l for l in result.stdout.strip().split('\n') if l.strip()]
            if not output_lines:
                return {"status": "error", "message": "专家未返回有效 JSON 结果"}
                
            return json.loads(output_lines[-1])

        except Exception as e:
            return {"status": "error", "message": f"大脑派发链路故障: {str(e)}"}

    # ================= 显式专家接口 (Explicit Expert Interfaces) =================

    def call_visual_eye(self, image_path, prompt):
        """调度 Qwen2-VL 推理：让大脑『看见』"""
        logger.info(f"👁️ [视觉推理] 处理图片: {os.path.basename(image_path)}")
        return self._dispatch_raw(
            "visual_reasoning_env", 
            "services/reasoning_eye/visual_wrapper.py", 
            {"image": image_path, "prompt": prompt}
        )

    def call_whisper_node(self, audio_id=None):
        """调度 Whisper 转录：让大脑『听见』"""
        logger.info("👂 [语音转录] 启动音频转录专家流水线...")
        return self._dispatch_raw(
            "audio_processing_env", 
            "data_layer/audio_pro/audio_wrapper.py", 
            {"audio_id": audio_id}
        )

    def call_pdf_expert(self, pdf_id=None):
        """调度 MinerU 专家：让大脑『阅读』"""
        logger.info(f"📄 [文档解析] 调度 MinerU 解析任务: {pdf_id}")
        return self._dispatch_raw(
            "pdf_processing_env", 
            "data_layer/pdf_pro/pdf_wrapper.py", 
            {"pdf_id": pdf_id}
        )

    def call_sandbox(self, expression, mode="eval"):
        """调度计算沙盒：让大脑『计算』"""
        logger.info(f"🔢 [科学计算] 执行表达式: {expression}")
        return self._dispatch_raw(
            "scientific_env", 
            "services/sandbox/sandbox_wrapper.py", 
            {"expression": expression, "mode": mode}
        )

    def call_video_slicer(self, video_path=None):
        """调度切片专家：让大脑『解构』视频"""
        logger.info("✂️ [视频切片] 启动全量视频资产预处理...")
        return self._dispatch_raw(
            "video_vision_env", 
            "data_layer/video_pro/video_wrapper.py", 
            {"video_path": video_path}
        )

# ================= 调度示例 =================
if __name__ == "__main__":
    manager = ToolsManager()
    
    # 场景示例：大脑发现一段公式图片，需要计算结果
    # 1. 先问视觉专家公式是什么
    # v_res = manager.call_visual_eye("path/to/formula.jpg", "图中公式是什么？只返回 LaTeX")
    
    # 2. 将结果扔进沙盒
    # s_res = manager.call_sandbox(v_res.get('response'), mode="eval")