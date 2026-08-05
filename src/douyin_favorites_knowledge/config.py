from __future__ import annotations

import json
import math
import os
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .security import assert_safe_value


@dataclass(frozen=True)
class StageConfig:
    name: str
    enabled: bool
    provider: str
    adapter: str
    model: str
    options: dict[str, Any]

    def context(self, mode: str) -> dict[str, Any]:
        return {
            "mode": mode,
            "stage": self.name,
            "provider": self.provider,
            "model": self.model,
            "options": dict(self.options),
        }


@dataclass(frozen=True)
class Config:
    knowledge_dir: Path
    ledger_path: Path
    mode: str
    transcription: StageConfig
    analysis: StageConfig
    notification: StageConfig
    raw: dict[str, Any]

    def enrichment_stages(self) -> tuple[StageConfig, ...]:
        return tuple(stage for stage in (self.transcription, self.analysis) if stage.enabled)


STAGE_PROVIDERS = {
    "transcription": {"none", "siliconflow", "bailian", "local_whisper", "local", "adapter"},
    "analysis": {"none", "local", "minimax", "adapter"},
    "notification": {"none", "feishu", "adapter"},
}


def default_config_path() -> Path:
    override = os.environ.get("DOUYIN_FAVORITES_CONFIG")
    if override:
        return Path(override).expanduser().resolve()
    system = platform.system()
    if system == "Darwin":
        root = Path.home() / "Library" / "Application Support"
    elif system == "Windows":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / "douyin-favorites-to-knowledge" / "config.json"


def _stage_config(raw: dict[str, Any], name: str) -> StageConfig:
    value = raw.get(name, {})
    if not isinstance(value, dict):
        raise ValueError(f"config {name} must be an object")
    if name in raw:
        missing = {"enabled", "provider"} - set(value)
        if missing:
            raise ValueError(f"missing config fields at {name}: {sorted(missing)}")
    allowed = {"enabled", "provider", "adapter", "model", "options"}
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(f"unknown config fields at {name}: {sorted(unknown)}")

    enabled = value.get("enabled", False)
    provider = value.get("provider", "none")
    adapter = value.get("adapter", "")
    model = value.get("model", "")
    options = value.get("options", {})
    if not isinstance(enabled, bool):
        raise ValueError(f"config {name}.enabled must be a boolean")
    if not isinstance(provider, str) or provider not in STAGE_PROVIDERS[name]:
        raise ValueError(f"unsupported {name} provider: {provider!r}")
    if not isinstance(adapter, str) or (adapter and ":" not in adapter):
        raise ValueError(f"config {name}.adapter must use module:function format")
    if not isinstance(model, str):
        raise ValueError(f"config {name}.model must be a string")
    if not isinstance(options, dict):
        raise ValueError(f"config {name}.options must be an object")
    for option_name in ("max_daily_audio_seconds", "max_daily_items", "max_media_bytes"):
        if option_name in options and (isinstance(options[option_name], bool) or not isinstance(options[option_name], (int, float)) or not math.isfinite(options[option_name]) or options[option_name] <= 0):
            raise ValueError(f"config {name}.options.{option_name} must be a positive number")
    if enabled and provider == "none":
        raise ValueError(f"config {name}.provider cannot be none when enabled")
    if enabled and provider not in {"siliconflow", "bailian", "local_whisper"} and not adapter:
        raise ValueError(f"config {name}.adapter is required when enabled")
    if not enabled and (provider != "none" or adapter or model or options):
        raise ValueError(f"disabled config {name} must not define provider settings")
    if enabled and provider in {"local", "local_whisper", "minimax"} and not model.strip():
        raise ValueError(f"config {name}.model is required for provider {provider}")
    return StageConfig(
        name=name,
        enabled=enabled,
        provider=provider,
        adapter=adapter,
        model=model.strip(),
        options=dict(options),
    )


def load_config(path: Path) -> Config:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read config: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("config must be an object")
    version = raw.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int) or version not in {1, 2}:
        raise ValueError("config schema_version must be 1 or 2")
    assert_safe_value(raw, "config")
    allowed = {"schema_version", "knowledge_dir", "ledger_path"}
    if version == 2:
        allowed.update({"mode", "transcription", "analysis", "notification"})
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

    mode = "light" if version == 1 else raw.get("mode", "light")
    if not isinstance(mode, str) or mode not in {"light", "full"}:
        raise ValueError("config mode must be light or full")
    stages = {
        name: _stage_config(raw if version == 2 else {}, name)
        for name in STAGE_PROVIDERS
    }
    if mode == "light" and any(stage.enabled for stage in stages.values()):
        raise ValueError("light mode cannot enable optional stages")
    return Config(
        knowledge_dir=knowledge_dir,
        ledger_path=ledger_path,
        mode=mode,
        transcription=stages["transcription"],
        analysis=stages["analysis"],
        notification=stages["notification"],
        raw=dict(raw),
    )
