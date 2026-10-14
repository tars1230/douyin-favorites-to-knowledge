"""Low-cost screen reading for Douyin items that have no usable speech.

SiliconFlow prices checked 2026-10-13, USD per million tokens:

- Qwen/Qwen3-VL-8B-Instruct: input 0.18, output 0.68
- Qwen/Qwen3-VL-32B-Instruct: input 0.20, output 0.60
- Qwen/Qwen3-VL-30B-A3B-Instruct: input 0.29, output 1.00

8B is not the cheap choice. 32B costs about the same and is the model the
local daily report already verified. MoE and Thinking variants cost more.
Qwen3-Omni video upload is the expensive path and is not used.

PaddlePaddle/PaddleOCR-VL-1.5 was listed at $0 on SiliconFlow. Use it first
for words already on the picture. Call 32B only when that text is too short.
"""
from __future__ import annotations

import re
from typing import Any

from .media_kind import is_image_post

OCR_MODEL = "PaddlePaddle/PaddleOCR-VL-1.5"
SCENE_MODEL = "Qwen/Qwen3-VL-32B-Instruct"
OCR_DETAIL = "high"
SCENE_DETAIL = "low"
MAX_IMAGES = 3
MAX_OUTPUT_TOKENS = 400
MAX_DAILY_ITEMS = 20
MIN_SPEECH_CHARS = 40
MIN_OCR_CHARS = 12
_SPECIAL_TOKEN = re.compile(r"<\|[^|>]{0,80}\|>")

# Qwen detail=low bills a 448px square, about 256 input tokens.
LOW_DETAIL_INPUT_TOKENS = 256
SCENE_INPUT_USD_PER_M = 0.20
SCENE_OUTPUT_USD_PER_M = 0.60


def vision_enabled(options: dict[str, Any] | None) -> bool:
    vision = (options or {}).get("vision")
    return isinstance(vision, dict) and vision.get("enabled") is True


def needs_screen_read(item: dict[str, Any]) -> bool:
    """Only picture posts. A video cover is not the video."""
    status = str(item.get("transcript_status") or "")
    if status == "success" and len(str(item.get("transcript") or "").strip()) >= MIN_SPEECH_CHARS:
        return False
    return is_image_post(item) or status == "skipped_image"


def clean_ocr_text(text: str) -> str:
    """Drop PaddleOCR location tokens before judging whether the words are enough."""
    cleaned = _SPECIAL_TOKEN.sub("", text or "")
    return "\n".join(line.strip() for line in cleaned.splitlines() if line.strip()).strip()


def _image_urls(item: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    raw = item.get("image_urls") or []
    if isinstance(raw, list):
        urls.extend(str(url).strip() for url in raw if str(url).strip())
    cover = str(item.get("cover_url") or "").strip()
    if cover:
        urls.append(cover)
    seen: set[str] = set()
    unique: list[str] = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        unique.append(url)
    return unique[:MAX_IMAGES]


def screen_targets(item: dict[str, Any]) -> list[str]:
    return _image_urls(item)


def estimate_scene_call_usd(images: int = 1, output_tokens: int = MAX_OUTPUT_TOKENS) -> float:
    """Upper bound for one 32B call at detail=low. OCR-first calls are $0."""
    images = max(0, min(images, MAX_IMAGES))
    input_tokens = images * LOW_DETAIL_INPUT_TOKENS
    return (input_tokens * SCENE_INPUT_USD_PER_M + output_tokens * SCENE_OUTPUT_USD_PER_M) / 1_000_000
