from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .security import assert_safe_value


@dataclass(frozen=True)
class Config:
    knowledge_dir: Path
    ledger_path: Path
    raw: dict[str, Any]


def load_config(path: Path) -> Config:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read config: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ValueError("config schema_version must be 1")
    assert_safe_value(raw, "config")
    allowed = {"schema_version", "knowledge_dir", "ledger_path"}
    unknown = set(raw) - allowed
    if unknown:
        raise ValueError(f"unknown config fields: {sorted(unknown)}")
    for key in ("knowledge_dir", "ledger_path"):
        if not isinstance(raw.get(key), str) or not raw[key].strip():
            raise ValueError(f"config {key} must be a non-empty string")

    base = path.resolve().parent

    def resolve(value: str) -> Path:
        candidate = Path(value).expanduser()
        return candidate.resolve() if candidate.is_absolute() else (base / candidate).resolve()

    knowledge_dir = resolve(raw["knowledge_dir"])
    ledger_path = resolve(raw["ledger_path"])
    if knowledge_dir == ledger_path:
        raise ValueError("knowledge_dir and ledger_path must be different")
    return Config(knowledge_dir=knowledge_dir, ledger_path=ledger_path, raw=dict(raw))
