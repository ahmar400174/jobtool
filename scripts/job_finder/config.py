"""Load job finder configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def load_settings() -> dict[str, Any]:
    path = project_root() / "config" / "settings.yaml"
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}
