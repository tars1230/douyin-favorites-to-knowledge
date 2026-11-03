"""Optional speech-quality gate for one favorites item.

Public defaults are mild and off. There is no song list and no category
table. A low score changes how the note is labeled. It does not drop the
item, and it does not turn screen reading on.
"""
from __future__ import annotations

import json
import re
from typing import Any


QUALITIES = frozenset({"empty", "low", "medium", "high", "lyric_conflict"})
UNTRUSTED = frozenset({"empty", "low", "lyric_conflict"})
DEFAULT_MIN_CHARS = 40
DEFAULT_MIN_CJK_RATIO = 0.5
DEFAULT_MAX_FRAGMENT_RATIO = 0.45
DEFAULT_MIN_OVERLAP = 0.15
DEFAULT_MAX_MISSING_TOPIC_RATIO = 0.8
DEFAULT_MAX_LOW_QUALITY_RATIO = 0.5

# Generic caption cues that a clip is marked as music. Not a song list.
_MUSIC_SIGNAL = re.compile(
    r"🎼|🎵|🎶|♪|♫|BGM|bgm|背景音乐|纯音乐|伴奏|原声|翻唱|歌词",
    re.IGNORECASE,
)
_CJK = re.compile(r"[\u4e00-\u9fff]")
_LETTER = re.compile(r"[\u4e00-\u9fffA-Za-z]")
_CLAUSE = re.compile(r"[，。！？、,.!?;；\s]+")


def default_transcript_quality() -> dict[str, Any]:
    return {
        "enabled": False,
        "min_chars": DEFAULT_MIN_CHARS,
        "min_cjk_ratio": DEFAULT_MIN_CJK_RATIO,
        "max_fragment_ratio": DEFAULT_MAX_FRAGMENT_RATIO,
        "lyric_conflict": True,
        "min_overlap": DEFAULT_MIN_OVERLAP,
    }


def default_batch_quality() -> dict[str, Any]:
    return {
        "enabled": False,
        "warn_only": True,
        "max_missing_topic_ratio": DEFAULT_MAX_MISSING_TOPIC_RATIO,
        "max_low_quality_ratio": DEFAULT_MAX_LOW_QUALITY_RATIO,
    }


def cjk_ratio(text: str) -> float:
    letters = _LETTER.findall(text or "")
    if not letters:
        return 0.0
    return len(_CJK.findall(text or "")) / len(letters)


def fragment_ratio(text: str) -> float:
    parts = [part for part in _CLAUSE.split(text or "") if part]
    if not parts:
        return 1.0
    short = 0
    for part in parts:
        if len(_LETTER.findall(part)) <= 2:
            short += 1
    return short / len(parts)


def _cjk_bigrams(text: str) -> set[str]:
    chars = _CJK.findall(text or "")
    if len(chars) < 2:
        return set()
    return {chars[index] + chars[index + 1] for index in range(len(chars) - 1)}


def conflicts_with_caption(transcript: str, description: str, *, min_overlap: float = DEFAULT_MIN_OVERLAP) -> bool:
    """Music-marked caption with almost no shared wording is not speech.

    The cue is a generic music mark in the description. Overlap is the share
    of the shorter Chinese-bigram set. No artist or title list is used.
    """
    if not _MUSIC_SIGNAL.search(description or ""):
        return False
    caption = _MUSIC_SIGNAL.sub(" ", description or "")
    spoken = _cjk_bigrams(transcript or "")
    noted = _cjk_bigrams(caption)
    if not spoken or not noted:
        return bool((transcript or "").strip())
    score = len(spoken & noted) / min(len(spoken), len(noted))
    return score < min_overlap


def _number(value: Any, default: float, *, upper: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    number = float(value)
    if number < 0:
        return default
    if upper is not None and number > upper:
        return default
    return number


def assess_transcript(item: dict[str, Any], settings: dict[str, Any] | None) -> dict[str, str]:
    """Return ``transcript_quality`` or nothing.

    Screen text is a different layer and is left alone. The gate stays quiet
    when disabled, and any unexpected error returns nothing so the note can
    still be written.
    """
    options = settings or {}
    if options.get("enabled") is not True:
        return {}
    try:
        status = str(item.get("transcript_status") or "")
        if status != "success":
            return {}
        text = str(item.get("transcript") or "").strip()
        if not text:
            return {"transcript_quality": "empty"}
        if options.get("lyric_conflict", True) is not False and conflicts_with_caption(
            text,
            str(item.get("description") or ""),
            min_overlap=_number(options.get("min_overlap", DEFAULT_MIN_OVERLAP), DEFAULT_MIN_OVERLAP, upper=1),
        ):
            return {"transcript_quality": "lyric_conflict"}
        min_chars = int(_number(options.get("min_chars", DEFAULT_MIN_CHARS), DEFAULT_MIN_CHARS))
        if min_chars <= 0:
            min_chars = DEFAULT_MIN_CHARS
        if len(text) < min_chars:
            return {"transcript_quality": "low"}
        if cjk_ratio(text) < _number(options.get("min_cjk_ratio", DEFAULT_MIN_CJK_RATIO), DEFAULT_MIN_CJK_RATIO, upper=1):
            return {"transcript_quality": "low"}
        if fragment_ratio(text) > _number(
            options.get("max_fragment_ratio", DEFAULT_MAX_FRAGMENT_RATIO),
            DEFAULT_MAX_FRAGMENT_RATIO,
            upper=1,
        ):
            return {"transcript_quality": "low"}
        if len(text) >= max(min_chars * 3, 120):
            return {"transcript_quality": "high"}
        return {"transcript_quality": "medium"}
    except Exception:
        return {}


def understanding_layer(item: dict[str, Any]) -> str:
    """``speech``, ``screen``, or ``none``.

    A caption is never a layer here. Low, empty, and lyric-conflict speech
    is ``none`` so the note cannot present it as understood speech.
    """
    status = str(item.get("transcript_status") or "")
    text = str(item.get("transcript") or "").strip()
    quality = str(item.get("transcript_quality") or "")
    if status == "success" and text and quality not in UNTRUSTED:
        return "speech"
    if status == "screen_text" and text:
        return "screen"
    return "none"


def layer_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    """Count caption, speech, and screen only. Comments and chat are not counted."""
    counts = {"caption": 0, "speech": 0, "screen": 0}
    for item in items:
        if str(item.get("description") or "").strip():
            counts["caption"] += 1
        layer = understanding_layer(item)
        if layer in {"speech", "screen"}:
            counts[layer] += 1
    return counts


def batch_report(
    items: list[dict[str, Any]],
    settings: dict[str, Any] | None,
    *,
    topic_enabled: bool,
) -> dict[str, Any] | None:
    """Warn when configured ratios are high. Never rejects a batch.

    Missing-topic uses the neutral field ``topic``. It does not look for a
    leftover category name. The topic ratio is skipped when classification
    is off, because every note would otherwise look unlabeled.
    """
    options = settings or {}
    if options.get("enabled") is not True:
        return None
    total = len(items)
    warnings: list[str] = []
    report: dict[str, Any] = {"status": "ok", "warn_only": True, "item_count": total, "warnings": warnings}
    if total == 0:
        return report
    if topic_enabled:
        missing = sum(1 for item in items if not str(item.get("topic") or "").strip())
        ratio = missing / total
        report["missing_topic_ratio"] = round(ratio, 4)
        limit = _number(
            options.get("max_missing_topic_ratio", DEFAULT_MAX_MISSING_TOPIC_RATIO),
            DEFAULT_MAX_MISSING_TOPIC_RATIO,
            upper=1,
        )
        if ratio > limit:
            warnings.append(f"missing_topic_ratio {ratio:.2f} is above {limit:.2f}")
    scored = [str(item.get("transcript_quality") or "") for item in items if item.get("transcript_quality")]
    if scored:
        low = sum(1 for quality in scored if quality in UNTRUSTED)
        ratio = low / len(scored)
        report["low_quality_ratio"] = round(ratio, 4)
        limit = _number(
            options.get("max_low_quality_ratio", DEFAULT_MAX_LOW_QUALITY_RATIO),
            DEFAULT_MAX_LOW_QUALITY_RATIO,
            upper=1,
        )
        if ratio > limit:
            warnings.append(f"low_quality_ratio {ratio:.2f} is above {limit:.2f}")
    report["status"] = "warn" if warnings else "ok"
    return report


def saved_quality(note: str) -> dict[str, str]:
    """Read a promoted quality so the next sync hashes the same note."""
    if not note.startswith("---\n"):
        return {}
    end = note.find("\n---", 4)
    if end < 0:
        return {}
    for line in note[4:end].splitlines():
        if not line.startswith("transcript_quality:"):
            continue
        raw = line.split(":", 1)[1].strip()
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = raw.strip('"')
        if isinstance(value, str) and value in QUALITIES:
            return {"transcript_quality": value}
    return {}
