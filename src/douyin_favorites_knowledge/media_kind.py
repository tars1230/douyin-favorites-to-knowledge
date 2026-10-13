"""Classify Douyin items before speech transcription.

Image and slideshow posts often still expose a rendered play URL. That URL is
the pictures plus background music, not speech. Sending it to ASR writes song
lyrics into the note.
"""
from __future__ import annotations

from typing import Any

IMAGE_AWEME_TYPES = frozenset({2, 68, 150})


def is_image_post(item: dict[str, Any]) -> bool:
    """True when the item is a picture post, not a spoken video."""
    if str(item.get("media_kind") or "").strip() == "image":
        return True
    try:
        aweme_type = int(item.get("aweme_type") or 0)
    except (TypeError, ValueError):
        aweme_type = 0
    try:
        image_count = int(item.get("image_count") or 0)
    except (TypeError, ValueError):
        image_count = 0
    return aweme_type in IMAGE_AWEME_TYPES or image_count > 0


def skipped_image(source: str) -> dict[str, str]:
    """Non-retryable skip. The description can still be saved."""
    return {
        "transcript": "",
        "transcript_source": source,
        "transcript_status": "skipped_image",
    }
