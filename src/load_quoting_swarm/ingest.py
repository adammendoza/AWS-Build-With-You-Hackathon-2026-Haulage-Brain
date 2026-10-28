from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import FreightLoad, InputError


def load_freight_loads(path: str | Path) -> list[FreightLoad]:
    source = Path(path)
    if not source.exists():
        raise InputError(f"load fixture not found: {source}")
    payload: Any = json.loads(source.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("loads", payload.get("items"))
    if not isinstance(payload, list):
        raise InputError("loads JSON must be an array or an object with a loads array")

    loads: list[FreightLoad] = []
    errors: list[str] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            errors.append(f"row {index}: expected object")
            continue
        try:
            loads.append(FreightLoad.from_raw(item))
        except InputError as exc:
            errors.append(f"row {index}: {exc}")
    if errors:
        raise InputError("invalid load fixture:\n" + "\n".join(errors))
    return loads


def available_loads(loads: list[FreightLoad], *, limit: int | None = None) -> list[FreightLoad]:
    selected = [load for load in loads if load.is_available]
    return selected[:limit] if limit is not None else selected
