from __future__ import annotations

import json
import math
import os
import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .security import assert_safe_value
from .transcript_quality import default_batch_quality, default_transcript_quality


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


# ``manual`` keeps nickname-only drift from aborting sync and does not rewrite notes.
# ``auto_update_metadata`` rewrites those non-identity fields. Content conflicts stay protected.
DRIFT_POLICIES = frozenset({"manual", "auto_update_metadata"})
DEFAULT_DRIFT_POLICY = "manual"
TOPIC_CLASSIFY_MODES = frozenset({"suggest", "assign"})


def default_topic_classify() -> dict[str, Any]:
    return {"enabled": False, "mode": "suggest", "taxonomy_file": ""}


@dataclass(frozen=True)
class Config:
    knowledge_dir: Path
    ledger_path: Path
    mode: str
    transcription: StageConfig
    analysis: StageConfig
    notification: StageConfig
    raw: dict[str, Any]
    drift_policy: str = DEFAULT_DRIFT_POLICY
    topic_classify: dict[str, Any] = field(default_factory=default_topic_classify)
    transcript_quality: dict[str, Any] = field(default_factory=default_transcript_quality)
    batch_quality: dict[str, Any] = field(default_factory=default_batch_quality)

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
    allowed = {"schema_version", "knowledge_dir", "ledger_path", "drift_policy"}
    if version == 2:
        allowed.update({
            "mode",
            "transcription",
            "analysis",
            "notification",
            "topic_classify",
            "transcript_quality",
            "batch_quality",
        })
    unknown = set(raw) - allowed
    if unknown:
        raise ValueError(f"unknown config fields: {sorted(unknown)}")
    drift_policy = raw.get("drift_policy", DEFAULT_DRIFT_POLICY)
    if not isinstance(drift_policy, str) or drift_policy not in DRIFT_POLICIES:
        raise ValueError("config drift_policy must be manual or auto_update_metadata")
    for key in ("knowledge_dir", "ledger_path"):
        if not isinstance(raw.get(key), str) or not raw[key].strip():
            raise ValueError(f"config {key} must be a non-empty string")

    base = path.resolve().parent
    topic_classify = _topic_classify_config(raw, base) if version == 2 else default_topic_classify()
    transcript_quality = _transcript_quality_config(raw) if version == 2 else default_transcript_quality()
    batch_quality = _batch_quality_config(raw) if version == 2 else default_batch_quality()

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
        drift_policy=drift_policy,
        topic_classify=topic_classify,
        transcript_quality=transcript_quality,
        batch_quality=batch_quality,
    )


def _topic_classify_config(raw: dict[str, Any], base: Path) -> dict[str, Any]:
    value = raw.get("topic_classify", {})
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ValueError("config topic_classify must be an object")
    unknown = set(value) - {"enabled", "mode", "taxonomy_file"}
    if unknown:
        raise ValueError(f"unknown config fields at topic_classify: {sorted(unknown)}")
    enabled = value.get("enabled", False)
    mode = value.get("mode", "suggest")
    taxonomy = value.get("taxonomy_file", "")
    if not isinstance(enabled, bool):
        raise ValueError("config topic_classify.enabled must be a boolean")
    if not isinstance(mode, str) or mode not in TOPIC_CLASSIFY_MODES:
        raise ValueError("config topic_classify.mode must be suggest or assign")
    if not isinstance(taxonomy, str):
        raise ValueError("config topic_classify.taxonomy_file must be a string")
    taxonomy = taxonomy.strip()
    resolved = ""
    if taxonomy:
        candidate = Path(taxonomy).expanduser()
        resolved = str(candidate.resolve() if candidate.is_absolute() else (base / candidate).resolve())
    return {"enabled": enabled, "mode": mode, "taxonomy_file": resolved}


def _bounded_number(value: Any, name: str, default: float, *, upper: float | None) -> float:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"config {name} must be a non-negative number")
    if upper is not None and value > upper:
        raise ValueError(f"config {name} must be at most {upper}")
    return float(value)


def _positive_int(value: Any, name: str, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"config {name} must be a positive integer")
    return value


def _transcript_quality_config(raw: dict[str, Any]) -> dict[str, Any]:
    value = raw.get("transcript_quality", {})
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ValueError("config transcript_quality must be an object")
    unknown = set(value) - {
        "enabled",
        "min_chars",
        "min_cjk_ratio",
        "max_fragment_ratio",
        "lyric_conflict",
        "min_overlap",
    }
    if unknown:
        raise ValueError(f"unknown config fields at transcript_quality: {sorted(unknown)}")
    defaults = default_transcript_quality()
    enabled = value.get("enabled", False)
    lyric = value.get("lyric_conflict", True)
    if not isinstance(enabled, bool):
        raise ValueError("config transcript_quality.enabled must be a boolean")
    if not isinstance(lyric, bool):
        raise ValueError("config transcript_quality.lyric_conflict must be a boolean")
    return {
        "enabled": enabled,
        "min_chars": _positive_int(value.get("min_chars"), "transcript_quality.min_chars", defaults["min_chars"]),
        "min_cjk_ratio": _bounded_number(
            value.get("min_cjk_ratio"),
            "transcript_quality.min_cjk_ratio",
            defaults["min_cjk_ratio"],
            upper=1,
        ),
        "max_fragment_ratio": _bounded_number(
            value.get("max_fragment_ratio"),
            "transcript_quality.max_fragment_ratio",
            defaults["max_fragment_ratio"],
            upper=1,
        ),
        "lyric_conflict": lyric,
        "min_overlap": _bounded_number(
            value.get("min_overlap"),
            "transcript_quality.min_overlap",
            defaults["min_overlap"],
            upper=1,
        ),
    }


def _batch_quality_config(raw: dict[str, Any]) -> dict[str, Any]:
    value = raw.get("batch_quality", {})
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ValueError("config batch_quality must be an object")
    unknown = set(value) - {"enabled", "warn_only", "max_missing_topic_ratio", "max_low_quality_ratio"}
    if unknown:
        raise ValueError(f"unknown config fields at batch_quality: {sorted(unknown)}")
    defaults = default_batch_quality()
    enabled = value.get("enabled", False)
    warn_only = value.get("warn_only", True)
    if not isinstance(enabled, bool):
        raise ValueError("config batch_quality.enabled must be a boolean")
    if not isinstance(warn_only, bool):
        raise ValueError("config batch_quality.warn_only must be a boolean")
    return {
        "enabled": enabled,
        "warn_only": warn_only,
        "max_missing_topic_ratio": _bounded_number(
            value.get("max_missing_topic_ratio"),
            "batch_quality.max_missing_topic_ratio",
            defaults["max_missing_topic_ratio"],
            upper=1,
        ),
        "max_low_quality_ratio": _bounded_number(
            value.get("max_low_quality_ratio"),
            "batch_quality.max_low_quality_ratio",
            defaults["max_low_quality_ratio"],
            upper=1,
        ),
    }
