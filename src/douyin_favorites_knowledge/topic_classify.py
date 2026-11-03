"""Optional topic labels for one favorites library.

There is no built-in category list. Suggestions come from the item's own
tags, hashtags and bracketed phrases. A single ``topic`` is written only in
``assign`` mode, and only when the user-supplied taxonomy file has one
clear winner. Classification never raises into transcription or note writing.

``media_kind`` is image-versus-video routing. It is not a topic.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


_HASHTAG = re.compile(r"[#＃]([^\s#＃]{1,24})")
_BRACKET = re.compile(r"[【\[]([^】\]]{1,24})[】\]]")
_PHRASE_CHAR = re.compile(r"[\w\u4e00-\u9fff]", re.UNICODE)
MAX_SUGGESTIONS = 8
MAX_LABEL_CHARS = 24


def _phrase(value: Any) -> str:
    text = str(value or "").strip().strip("#＃")
    if not 2 <= len(text) <= MAX_LABEL_CHARS:
        return ""
    if text.isdigit() or not _PHRASE_CHAR.search(text):
        return ""
    return text


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        text = _phrase(value)
        if not text or text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return unique


def suggest_from_item(item: dict[str, Any]) -> list[str]:
    """Phrases already on this item. Not a fixed taxonomy."""
    found: list[str] = []
    raw_tags = item.get("tags") or []
    if isinstance(raw_tags, list):
        found.extend(str(tag) for tag in raw_tags)
    blob = "\n".join(
        str(item.get(key) or "")
        for key in ("title", "description", "transcript")
    )
    found.extend(match.group(1) for match in _HASHTAG.finditer(blob))
    found.extend(match.group(1) for match in _BRACKET.finditer(blob))
    return _unique(found)[:MAX_SUGGESTIONS]


def load_taxonomy(path: Path) -> list[str]:
    """Read a user file: JSON list, ``{"labels": [...]}``, or one name per line.

    Raises ``OSError`` or ``ValueError`` when the file cannot be used.
    Callers treat that as "no taxonomy", not as a failed note.
    """
    text = path.read_text(encoding="utf-8")
    stripped = text.strip()
    if not stripped:
        return []
    if stripped[0] in "[{":
        payload = json.loads(stripped)
        if isinstance(payload, list):
            labels = payload
        elif isinstance(payload, dict) and isinstance(payload.get("labels"), list):
            labels = payload["labels"]
        else:
            raise ValueError("taxonomy must be a list or an object with labels")
    else:
        labels = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
    if not isinstance(labels, list) or any(not isinstance(label, str) for label in labels):
        raise ValueError("taxonomy labels must be strings")
    return _unique([label.strip() for label in labels])


def _ranked(item: dict[str, Any], labels: list[str]) -> list[tuple[int, str]]:
    title = str(item.get("title") or "").casefold()
    body = "\n".join(
        str(item.get(key) or "") for key in ("description", "transcript")
    ).casefold()
    raw_tags = item.get("tags") or []
    tags = set()
    if isinstance(raw_tags, list):
        tags = {str(tag).strip().casefold() for tag in raw_tags if str(tag).strip()}
    scored: list[tuple[int, str]] = []
    for label in labels:
        name = _phrase(label)
        if not name:
            continue
        key = name.casefold()
        score = 0
        if key in tags:
            score += 3
        if key in title:
            score += 2
        if key in body:
            score += 1
        if score:
            scored.append((score, name))
    return scored


def classify_item(item: dict[str, Any], settings: dict[str, Any] | None) -> dict[str, Any]:
    """Return ``topic`` and/or ``topic_suggestions``. Empty dict when off or broken.

    ``suggest`` never writes ``topic``. ``assign`` writes it only when one
    taxonomy label scores strictly above the others. A missing or invalid
    taxonomy file leaves suggestions from the item itself, if any.
    """
    options = settings or {}
    if options.get("enabled") is not True:
        return {}
    try:
        mode = str(options.get("mode") or "suggest")
        if mode not in {"suggest", "assign"}:
            mode = "suggest"
        suggestions = suggest_from_item(item)
        labels: list[str] = []
        path = str(options.get("taxonomy_file") or "").strip()
        if path:
            try:
                labels = load_taxonomy(Path(path))
            except (OSError, ValueError, json.JSONDecodeError, UnicodeError):
                labels = []
        scored = _ranked(item, labels)
        best = max((score for score, _name in scored), default=0)
        winners = [name for score, name in scored if score == best] if best else []
        others = [name for score, name in scored if score != best]
        topic = winners[0] if mode == "assign" and len(winners) == 1 else ""
        ordered = _unique([*winners, *others, *suggestions])
        extra = [name for name in ordered if name != topic][:MAX_SUGGESTIONS]
        result: dict[str, Any] = {}
        if topic:
            result["topic"] = topic
        if extra:
            result["topic_suggestions"] = extra
        return result
    except Exception:
        return {}


def saved_topic_fields(note: str) -> dict[str, Any]:
    """Read topic frontmatter so a later sync hashes the same note."""
    if not note.startswith("---\n"):
        return {}
    end = note.find("\n---", 4)
    if end < 0:
        return {}
    topic = ""
    suggestions: list[str] = []
    for line in note[4:end].splitlines():
        if line.startswith("topic_suggestions:"):
            raw = line.split(":", 1)[1].strip()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, list):
                suggestions = [text for text in (str(item).strip() for item in payload) if text]
        elif line.startswith("topic:"):
            raw = line.split(":", 1)[1].strip()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = raw.strip('"')
            if isinstance(payload, str) and payload.strip():
                topic = payload.strip()
    result: dict[str, Any] = {}
    if topic:
        result["topic"] = topic
    extra = [name for name in suggestions if name != topic]
    if extra:
        result["topic_suggestions"] = extra
    return result
