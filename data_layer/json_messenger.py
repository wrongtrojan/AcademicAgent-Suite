import json
import yaml
import logging
from pathlib import Path

logger = logging.getLogger("JsonMessenger")

class JsonMessenger:
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        config_path = self.project_root / "configs" / "model_config.yaml"
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
        self.storage_root = self.project_root / "storage" / "processed"

    def scan_increments(self):
        """
        [Loop & Incremental]
        """
        pending_tasks = []
        
        scan_map = {
            "video": self.storage_root / "video",
            "pdf": self.storage_root / "magic-pdf"
        }

        for asset_type, base_path in scan_map.items():
            if not base_path.exists(): continue
            
            for folder in base_path.iterdir():
                if not folder.is_dir(): continue
                
                asset_id = folder.name
                outline_file = folder / "summary_outline.json"
                
                if outline_file.exists():
                    logger.info(f"⏭️  [Incremental] Skip {asset_id}, outline exists.")
                    continue

                raw_file = self._locate_raw_file(folder, asset_id, asset_type)
                if raw_file and raw_file.exists():
                    context = self._build_context(raw_file, asset_type)
                    if context:
                        pending_tasks.append({
                            "asset_id": asset_id,
                            "asset_type": asset_type,
                            "context": context
                        })
        
        return pending_tasks

    def _locate_raw_file(self, folder, asset_id, asset_type):
        if asset_type == "video":
            return folder / "transcript.json"
        else: # pdf
            return folder / "ocr" / f"{asset_id}_content_list.json"

    def _build_context(self, raw_file, asset_type):
        with open(raw_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if asset_type == "video":
            return "\n".join([f"[{s['start']}s]: {s['text']}" for s in data.get('segments', [])])
        else:
            return "\n".join([f"[Page {i['page_idx']}]: {i['text']}" for i in data if i.get('type') == 'text'])

    def messenger_back(self, asset_id, asset_type, content):
        
        if asset_type == "video":
            base = self.storage_root / "video" / asset_id
        else:
            base = self.storage_root / "magic-pdf" / asset_id
            
        output_path = base / "summary_outline.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(content, f, ensure_ascii=False, indent=2)
        return str(output_path)