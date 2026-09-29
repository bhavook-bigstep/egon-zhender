"""Load and validate the versioned WS-1 configuration (Contract 4).

Taxonomy version, thresholds, model version, and paths come from YAML config, never
from literals in code (`.claude/rules/python.md`).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from libs.schemas import Ws1Config


def load_ws1_config(path: str | Path) -> Ws1Config:
    """Parse and validate a WS-1 config file into a typed model."""
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise ValueError(f"config at {config_path} is not a mapping")
    return Ws1Config(**raw)
