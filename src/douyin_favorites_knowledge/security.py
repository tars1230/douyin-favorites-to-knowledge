from __future__ import annotations

import re
from typing import Any


BLOCKED_PATTERNS = {
    "reasoning tag": re.compile(r"<\s*/?\s*(?:think|analysis)\b", re.IGNORECASE),
    "Unicode replacement character": re.compile("\ufffd"),
    "GitHub token": re.compile(r"gh[oprsu]_[A-Za-z0-9]{20,}"),
    "OpenAI-style key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    "Apify token": re.compile(r"apify_api_[A-Za-z0-9_-]{20,}"),
}

SECRET_KEY = re.compile(
    r"(?:token|secret|password|cookie|credential|api[_-]?key|access[_-]?key|private[_-]?key|authorization)",
    re.IGNORECASE,
)
PRIVATE_PATH = re.compile(r"(?:/Users/|/home/)[^\s:]+")


def assert_safe_text(value: str, location: str) -> None:
    if "\x00" in value:
        raise ValueError(f"NUL byte blocked at {location}")
    for label, pattern in BLOCKED_PATTERNS.items():
        if pattern.search(value):
            raise ValueError(f"{label} blocked at {location}")


def assert_safe_value(value: Any, location: str = "root") -> None:
    if isinstance(value, str):
        assert_safe_text(value, location)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            assert_safe_value(item, f"{location}[{index}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            if SECRET_KEY.search(str(key)):
                raise ValueError(f"secret-like key blocked at {location}.{key}")
            assert_safe_value(item, f"{location}.{key}")


def safe_error_message(exc: BaseException) -> str:
    """Avoid reflecting adapter credentials or private paths into logs."""
    message = str(exc).replace("\x00", "[REDACTED]")
    if BLOCKED_PATTERNS["reasoning tag"].search(message):
        return "sensitive error detail redacted"
    for pattern in BLOCKED_PATTERNS.values():
        message = pattern.sub("[REDACTED]", message)
    message = PRIVATE_PATH.sub("[PRIVATE_PATH]", message)
    return message[:500]
