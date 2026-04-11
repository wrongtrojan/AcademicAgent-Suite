from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_workflow(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)
