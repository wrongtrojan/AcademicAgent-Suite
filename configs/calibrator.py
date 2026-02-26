import os
import yaml
import json
from pathlib import Path

def calibrate_project_configs():
    # 1. 动态获取项目根目录 (Current script is in configs/, so parent is root)
    # resolve() 用于处理符号链接并获取绝对路径
    script_path = Path(__file__).resolve()
    project_root = script_path.parents[1]
    configs_dir = script_path.parent
    
    print(f"[INFO] Initializing path calibration...")
    print(f"[INFO] Detected Project Root: {project_root}")

    # 定义配置文件路径
    yaml_path = configs_dir / "model_config.yaml"
    json_path = configs_dir / "magic-pdf.json"

    # --- 处理 YAML 配置文件 ---
    if yaml_path.exists():
        print(f"[PROCESS] Syncing configuration: {yaml_path.name}")
        try:
            with open(yaml_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            # 更新基础路径
            data['paths']['base_dir'] = str(project_root)
            data['paths']['raw_storage'] = str(project_root / "storage/raw")
            data['paths']['processed_storage'] = str(project_root / "storage/processed")

            # 内部辅助函数：智能替换旧的前缀
            def update_prefix(old_path):
                if isinstance(old_path, str) and "AcademicAgent-Suite" in old_path:
                    # 提取项目名称之后的部分 (e.g., envs/DocRecognize/bin/python)
                    relative_part = old_path.split("AcademicAgent-Suite")[-1].lstrip("/")
                    return str(project_root / relative_part)
                return old_path

            # 批量校准 environments 和 model_paths
            for section in ['environments', 'model_paths']:
                if section in data:
                    for key in data[section]:
                        data[section][key] = update_prefix(data[section][key])

            with open(yaml_path, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, allow_unicode=True, sort_keys=False)
            print(f"[SUCCESS] YAML configuration calibrated successfully.")
        except Exception as e:
            print(f"[ERROR] Failed to calibrate YAML: {str(e)}")

    # --- 处理 JSON 配置文件 ---
    if json_path.exists():
        print(f"[PROCESS] Syncing configuration: {json_path.name}")
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                j_data = json.load(f)

            # 更新 JSON 中的特定字段
            j_data['models-dir'] = str(project_root / "models/miner_u/models")
            j_data['temp-output-dir'] = str(project_root / "storage/processed")

            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(j_data, f, indent=4, ensure_ascii=False)
            print(f"[SUCCESS] JSON configuration calibrated successfully.")
        except Exception as e:
            print(f"[ERROR] Failed to calibrate JSON: {str(e)}")

    print(f"[INFO] Calibration process completed.")

if __name__ == "__main__":
    calibrate_project_configs()