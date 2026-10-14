"""Read on-screen Douyin text through SiliconFlow without uploading the video.

Pictures are downloaded locally and sent as small image payloads. The Douyin
CDN URL is never given to SiliconFlow. A free OCR model runs first. The paid
32B model runs once, and only when OCR did not find enough words.
"""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from typing import Any, Callable

from .siliconflow import KEY_NAME, _download_media
from .vision_policy import (
    MAX_DAILY_ITEMS,
    MAX_OUTPUT_TOKENS,
    MIN_OCR_CHARS,
    OCR_DETAIL,
    OCR_MODEL,
    SCENE_DETAIL,
    SCENE_MODEL,
    clean_ocr_text,
    needs_screen_read,
    screen_targets,
)

CHAT_URL = "https://api.siliconflow.cn/v1/chat/completions"
OCR_PROMPT = "OCR:"
SCENE_PROMPT = (
    "用中文提取这一帧里对读者有用的信息。"
    "先逐字写出画面上的字，再写两句画面在讲什么。"
    "不要营销词，不要把背景音乐歌词当成正文。"
)


def _vision_options(options: dict[str, Any] | None) -> dict[str, Any]:
    vision = (options or {}).get("vision")
    return vision if isinstance(vision, dict) else {}


def _image_mime(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    return "application/octet-stream"


def _post_image(
    urlopen: Callable,
    *,
    api_key: str,
    model: str,
    image_bytes: bytes,
    prompt: str,
    max_tokens: int,
    detail: str,
) -> str:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    mime = _image_mime(image_bytes)
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{encoded}", "detail": detail},
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }
    request = urllib.request.Request(
        CHAT_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=90) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    content = (((payload or {}).get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    return str(content).strip()


def _load_images(urls: list[str], dest_dir, max_bytes: int) -> list[bytes]:
    from pathlib import Path

    root = Path(dest_dir)
    images: list[bytes] = []
    for index, url in enumerate(urls):
        path = root / f"frame-{index}.img"
        if _download_media(url, path, max_bytes):
            continue
        data = path.read_bytes()
        if data:
            images.append(data)
    return images


def read_screen(
    item: dict[str, Any],
    options: dict[str, Any] | None = None,
    *,
    urlopen: Callable | None = None,
    daily_used: int = 0,
    allow_paid: bool = True,
) -> dict[str, Any]:
    """Read on-screen words. Free OCR always runs; the paid model is optional."""
    if not needs_screen_read(item):
        return item
    vision = _vision_options(options)
    cap = int(vision.get("max_daily_items") or MAX_DAILY_ITEMS)
    paid_allowed = allow_paid and daily_used < cap
    urls = screen_targets(item)
    if not urls:
        return item
    api_key = os.environ.get(KEY_NAME, "").strip()
    if not api_key:
        return item
    opener = urlopen or urllib.request.urlopen
    ocr_model = str(vision.get("ocr_model") or OCR_MODEL)
    scene_model = str(vision.get("scene_model") or SCENE_MODEL)
    max_tokens = int(vision.get("max_output_tokens") or MAX_OUTPUT_TOKENS)
    import tempfile
    from pathlib import Path

    paid = False
    try:
        with tempfile.TemporaryDirectory(prefix="douyin-sf-vision-") as temp_dir:
            images = _load_images(urls, Path(temp_dir), 8 * 1024 * 1024)
            if not images:
                return item
            ocr_parts: list[str] = []
            for image in images:
                try:
                    text = _post_image(
                        opener,
                        api_key=api_key,
                        model=ocr_model,
                        image_bytes=image,
                        prompt=OCR_PROMPT,
                        max_tokens=max_tokens,
                        detail=OCR_DETAIL,
                    )
                except (OSError, TimeoutError, urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, KeyError, IndexError):
                    text = ""
                cleaned = clean_ocr_text(text)
                if cleaned:
                    ocr_parts.append(cleaned)
            ocr_text = "\n".join(ocr_parts).strip()
            if len(ocr_text) >= MIN_OCR_CHARS or not paid_allowed:
                if not ocr_text:
                    return item
                return {
                    **item,
                    "transcript": ocr_text,
                    "transcript_source": "siliconflow_paddleocr",
                    "transcript_status": "screen_text",
                }
            paid = True
            scene = _post_image(
                opener,
                api_key=api_key,
                model=scene_model,
                image_bytes=images[0],
                prompt=SCENE_PROMPT,
                max_tokens=max_tokens,
                detail=SCENE_DETAIL,
            )
    except (OSError, TimeoutError, urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, KeyError, IndexError):
        if paid:
            return {**item, "_vision_paid": 1}
        return item
    if not scene:
        return {**item, "_vision_paid": 1}
    return {
        **item,
        "transcript": scene,
        "transcript_source": "siliconflow_qwen3_vl_32b",
        "transcript_status": "screen_text",
        "_vision_paid": 1,
    }
