"""Loads a configuration, following `extends` so profiles stay small.

There is one real configuration file. A profile lists only what it changes,
which is the whole point: four near-identical copies drift, and the drift is
silent - a value measured at the station gets updated in one file and quietly
stays wrong in the others.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List

import yaml

log = logging.getLogger(__name__)

EXTENDS_KEY = "extends"
MAX_DEPTH = 5          # a profile chain longer than this is a mistake


def merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Deep-merge `override` onto `base`, without touching either."""
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path: Path) -> Dict[str, Any]:
    """Read a config, applying anything it extends first.

    `extends` is relative to the file that declares it, so a profile can sit in
    its own folder and still point at the base by name.
    """
    path = Path(path).resolve()
    chain: List[Path] = []

    while True:
        if path in chain:
            raise ValueError(f"Circular extends: {' -> '.join(p.name for p in chain)}")
        chain.append(path)
        if len(chain) > MAX_DEPTH:
            raise ValueError(f"extends nested more than {MAX_DEPTH} deep")

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        parent = data.get(EXTENDS_KEY)
        if not parent:
            break
        path = (path.parent / parent).resolve()

    # Deepest ancestor first, so the profile the user asked for wins.
    config: Dict[str, Any] = {}
    for file in reversed(chain):
        layer = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
        layer.pop(EXTENDS_KEY, None)
        config = merge(config, layer)

    if len(chain) > 1:
        log.info("config: %s", " <- ".join(p.name for p in chain))
    return config
