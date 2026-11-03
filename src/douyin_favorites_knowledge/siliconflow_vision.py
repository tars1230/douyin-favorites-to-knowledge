"""Read on-screen Douyin text through SiliconFlow without uploading the video.

Pictures are downloaded locally and sent as small image payloads. The Douyin
CDN URL is never given to SiliconFlow. A free OCR model runs first. The paid
32B model runs once, and only when OCR did not find enough words.

Videos stay on the ASR path unless ``vision.silent_video`` is on and the
transcript is missing. In that case ffmpeg grabs a few local frames. The
video file itself is not uploaded.
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from .media_kind import is_image_post
from .siliconflow import KEY_NAME, _candidate_urls, _download_media, _suffix_for_url
from .vision_policy import (
    MAX_DAILY_ITEMS,
    MAX_OUTPUT_TOKENS,
    MIN_OCR_CHARS,
    OCR_DETAIL,
    OCR_MODEL,
    SCENE_DETAIL,
    SCENE_MODEL,
    clean_ocr_text,
    is_useful_screen_text,
    needs_screen_read,
    screen_targets,
    video_frame_count,
)

CHAT_URL = "https://api.siliconflow.cn/v1/chat/completions"
OCR_PROMPT = "OCR:"
SCENE_PROMPT = (
    "用中文提取这一帧里对读者有用的信息。"
    "先逐字写出画面上的字，再写两句画面在讲什么。"
    "不要营销词，不要把背景音乐歌词当成正文。"
)
VIDEO_SCENE_PROMPT = (
    "这些是一段没有可用口播的视频里抽出的画面。请用中文写进笔记："
    "先逐字抄出画面上的字；字很少时再写两句画面里实际在发生什么。"
    "不要只回答“无”或“没有文字”，不要营销词，不要把背景音乐当成正文。"
)
_MAX_VIDEO_BYTES = 512 * 1024 * 1024


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


def ffmpeg_frame_command(source: Path, pattern: Path, count: int) -> list[str]:
    """Sample a few small JPEGs. The input is a local file, never a CDN URL."""
    return [
        "ffmpeg",
        "-nostdin",
        "-y",
        "-i",
        str(source),
        "-vf",
        "fps=1/4,scale='min(768,iw)':-2",
        "-frames:v",
        str(count),
        "-q:v",
        "5",
        str(pattern),
    ]


def _max_media_bytes(options: dict[str, Any] | None) -> int:
    raw = (options or {}).get("max_media_bytes", _MAX_VIDEO_BYTES)
    if isinstance(raw, bool):
        return _MAX_VIDEO_BYTES
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return _MAX_VIDEO_BYTES
    return value if value > 0 else _MAX_VIDEO_BYTES


def _extract_video_frames(
    item: dict[str, Any],
    dest: Path,
    options: dict[str, Any] | None,
    *,
    max_bytes: int,
) -> list[bytes]:
    """Download the play URL locally and keep a handful of JPEGs."""
    if not shutil.which("ffmpeg"):
        return []
    count = video_frame_count(options)
    for kind, url in _candidate_urls(item):
        media = dest / f"video-{kind}{_suffix_for_url(url)}"
        if _download_media(url, media, max_bytes):
            continue
        pattern = dest / "shot-%02d.jpg"
        try:
            subprocess.run(
                ffmpeg_frame_command(media, pattern, count),
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        frames: list[bytes] = []
        for path in sorted(dest.glob("shot-*.jpg")):
            data = path.read_bytes()
            if data:
                frames.append(data)
        if frames:
            return frames[:count]
    return []


def _strict_screen_text(item: dict[str, Any]) -> bool:
    """Video frames must clear the usefulness bar. Picture posts stay loose."""
    status = str(item.get("transcript_status") or "")
    return not is_image_post(item) and status != "skipped_image"


def _frames_for_item(
    item: dict[str, Any],
    dest: Path,
    options: dict[str, Any] | None,
    *,
    max_bytes: int,
) -> list[bytes]:
    if not _strict_screen_text(item):
        return _load_images(screen_targets(item), dest, 8 * 1024 * 1024)
    frames = _extract_video_frames(item, dest, options, max_bytes=max_bytes)
    if frames:
        return frames
    cover = str(item.get("cover_url") or "").strip()
    if not cover:
        return []
    return _load_images([cover], dest, 8 * 1024 * 1024)


def _ocr_images(
    urlopen: Callable,
    *,
    api_key: str,
    model: str,
    images: list[bytes],
    max_tokens: int,
) -> str:
    parts: list[str] = []
    for image in images:
        try:
            text = _post_image(
                urlopen,
                api_key=api_key,
                model=model,
                image_bytes=image,
                prompt=OCR_PROMPT,
                max_tokens=max_tokens,
                detail=OCR_DETAIL,
            )
        except (OSError, TimeoutError, urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, KeyError, IndexError):
            text = ""
        cleaned = clean_ocr_text(text)
        if cleaned:
            parts.append(cleaned)
    return "\n".join(parts).strip()


def _ocr_is_enough(text: str, *, strict: bool) -> bool:
    if len(text) < MIN_OCR_CHARS:
        return False
    if strict and not is_useful_screen_text(text):
        return False
    return True


def _keep_text(text: str, *, strict: bool) -> bool:
    if strict:
        return is_useful_screen_text(text)
    return bool(text.strip())


def _screen_item(item: dict[str, Any], text: str, source: str, *, paid: bool = False) -> dict[str, Any]:
    updated = {
        **item,
        "transcript": text,
        "transcript_source": source,
        "transcript_status": "screen_text",
    }
    if paid:
        updated["_vision_paid"] = 1
    return updated


def read_screen(
    item: dict[str, Any],
    options: dict[str, Any] | None = None,
    *,
    urlopen: Callable | None = None,
    daily_used: int = 0,
    allow_paid: bool = True,
) -> dict[str, Any]:
    """Read on-screen words. Free OCR always runs; the paid model is optional.

    Picture posts use their image URLs. A video is read only when
    ``needs_screen_read`` says so (``vision.silent_video``). Failure leaves
    the original transcript status in place.
    """
    if not needs_screen_read(item, options):
        return item
    vision = _vision_options(options)
    cap = int(vision.get("max_daily_items") or MAX_DAILY_ITEMS)
    paid_allowed = allow_paid and daily_used < cap
    api_key = os.environ.get(KEY_NAME, "").strip()
    if not api_key:
        return item
    opener = urlopen or urllib.request.urlopen
    ocr_model = str(vision.get("ocr_model") or OCR_MODEL)
    scene_model = str(vision.get("scene_model") or SCENE_MODEL)
    max_tokens = int(vision.get("max_output_length") or MAX_OUTPUT_TOKENS)
    strict = _strict_screen_text(item)
    import tempfile

    paid = False
    try:
        with tempfile.TemporaryDirectory(prefix="douyin-sf-vision-") as temp_dir:
            images = _frames_for_item(
                item,
                Path(temp_dir),
                options,
                max_bytes=_max_media_bytes(options),
            )
            if not images:
                return item
            ocr_text = _ocr_images(
                opener,
                api_key=api_key,
                model=ocr_model,
                images=images,
                max_tokens=max_tokens,
            )
            if _ocr_is_enough(ocr_text, strict=strict) or not paid_allowed:
                if not _keep_text(ocr_text, strict=strict):
                    return item
                return _screen_item(item, ocr_text, "siliconflow_paddleocr")
            paid = True
            scene = _post_image(
                opener,
                api_key=api_key,
                model=scene_model,
                image_bytes=images[0],
                prompt=VIDEO_SCENE_PROMPT if strict else SCENE_PROMPT,
                max_tokens=max_tokens,
                detail=SCENE_DETAIL,
            )
    except (OSError, TimeoutError, urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, KeyError, IndexError):
        if paid:
            return {**item, "_vision_paid": 1}
        return item
    if strict:
        scene = clean_ocr_text(scene)
    if not _keep_text(scene, strict=strict):
        return {**item, "_vision_paid": 1}
    return _screen_item(item, scene, "siliconflow_qwen3_vl_32b", paid=True)
