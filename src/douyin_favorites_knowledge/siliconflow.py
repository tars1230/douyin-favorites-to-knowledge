# -*- coding: utf-8 -*-
"""SiliconFlow SenseVoice ASR for Douyin CDN media.

Douyin ``*.douyinvod.com`` play URLs require browser-like Referer headers and
cannot be fetched by Bailian server-side URL-ASR. This provider downloads with
Referer, extracts audio via ffmpeg, and uploads to SiliconFlow.

Stable path (deliberately simple):
1. Download ``play_url`` / ``video_url`` (video stream).
2. ``ffmpeg -vn`` extract mono 16 kHz mp3.
3. Upload to SiliconFlow SenseVoice.

Do **not** prefer ``audio_url`` / ``music.play_url`` — that is often commercial
BGM, not speech, and adds a flaky branch. Keep one media path.
"""
from __future__ import annotations

import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .cdn_auth import download_request
from .media_kind import is_image_post, skipped_image

KEY_NAME = "SILICONFLOW_API_KEY"
DEFAULT_MODEL = "FunAudioLLM/SenseVoiceSmall"
FALLBACK_MODEL = "XingChenAGI/XingChenASR-V3.2"
DEFAULT_ENDPOINT = "https://api.siliconflow.cn/v1/audio/transcriptions"
MAX_MEDIA_BYTES = 512 * 1024 * 1024
TEMP_PREFIX = "douyin-sf-asr-"
DEFAULT_BITRATE = "64k"
DEFAULT_SAMPLE_RATE = "16000"


def check_environment() -> dict[str, Any]:
    """Check prerequisites only; never call the API during health checks."""
    missing: list[str] = []
    if not os.environ.get(KEY_NAME, "").strip():
        missing.append(KEY_NAME)
    return {"ready": not missing, **({"missing": missing} if missing else {})}


def _failed(status: str, error: str = "") -> dict[str, str]:
    result = {
        "transcript": "",
        "transcript_source": "siliconflow_sensevoice",
        "transcript_status": status,
    }
    if error:
        result["transcript_error"] = error[:180]
    return result


def _audio_encode_settings() -> tuple[str, str]:
    """Return (sample_rate, bitrate) for ffmpeg ASR extract."""
    rate = (os.environ.get("DOUYIN_ASR_SAMPLE_RATE") or DEFAULT_SAMPLE_RATE).strip() or DEFAULT_SAMPLE_RATE
    if not re.fullmatch(r"\d{4,6}", rate):
        rate = DEFAULT_SAMPLE_RATE
    br = (os.environ.get("DOUYIN_ASR_AUDIO_BITRATE") or DEFAULT_BITRATE).strip() or DEFAULT_BITRATE
    if not re.fullmatch(r"\d{2,4}k", br, flags=re.I):
        br = DEFAULT_BITRATE
    return rate, br.lower()


def _suffix_for_url(url: str) -> str:
    path = url.split("?", 1)[0].lower()
    for ext in (".m4a", ".mp3", ".aac", ".wav", ".mp4", ".webm", ".mov"):
        if path.endswith(ext):
            return ext
    return ".bin"


def _looks_like_audio_url(url: str) -> bool:
    path = url.split("?", 1)[0].lower()
    return any(path.endswith(ext) for ext in (".m4a", ".mp3", ".aac", ".wav", ".ogg", ".flac"))


def _candidate_urls(item: dict[str, Any]) -> list[tuple[str, str]]:
    """Ordered (kind, url) candidates: video/play only (no audio_url branch)."""
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for kind, key in (
        ("play", "play_url"),
        ("video", "video_url"),
    ):
        url = str(item.get(key) or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        out.append((kind, url))
    for index, url in enumerate(item.get("play_urls") or []):
        text = str(url or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append((f"play{index}", text))
    return out


def _download_media(url: str, destination: Path, max_bytes: int) -> str | None:
    """Download media. Return error status or None on success."""
    request = download_request(url)
    try:
        with urllib.request.urlopen(request, timeout=180) as response, destination.open("wb") as output:
            declared = response.headers.get("Content-Length")
            if declared:
                try:
                    if int(declared) > max_bytes:
                        return "too_large"
                except ValueError:
                    pass
            total = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    return "too_large"
                output.write(chunk)
    except urllib.error.HTTPError as exc:
        return f"http_{exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError):
        return "failed"
    return None if destination.exists() and destination.stat().st_size > 0 else "failed"


def _extract_audio(source: Path, audio: Path) -> bool:
    if not shutil.which("ffmpeg"):
        return False
    rate, bitrate = _audio_encode_settings()
    completed = subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            rate,
            "-b:a",
            bitrate,
            str(audio),
        ],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    return completed.returncode == 0 and audio.exists() and audio.stat().st_size > 0


def _prepare_upload(source: Path, root: Path) -> Path:
    """Prefer compact mp3 for upload; fall back to source bytes."""
    if _looks_like_audio_url(source.name) and source.stat().st_size <= 20 * 1024 * 1024:
        # Already audio and modest size — still normalize when ffmpeg exists.
        pass
    audio_path = root / "audio.mp3"
    if _extract_audio(source, audio_path):
        return audio_path
    return source


def _upload_transcribe(path: Path, api_key: str, model: str, endpoint: str) -> str:
    import json
    import uuid

    boundary = f"----DouyinSF{uuid.uuid4().hex}"
    filename = path.name
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    body = bytearray()
    for name, value in (("model", model), ("language", "zh"), ("response_format", "json")):
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n".encode()
    )
    body.extend(path.read_bytes())
    body.extend(f"\r\n--{boundary}--\r\n".encode())

    request = urllib.request.Request(
        endpoint,
        data=bytes(body),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "douyin-favorites-to-knowledge/siliconflow",
        },
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    if isinstance(payload, dict):
        text = payload.get("text") or payload.get("transcript") or ""
        if isinstance(text, str) and text.strip():
            return text.strip()
    return ""


def _success(text: str, source: str, kind: str) -> dict[str, str]:
    return {
        "transcript": text,
        "transcript_source": source,
        "transcript_status": "success",
        "media_kind_used": kind,
    }


def _transcribe_file(path: Path, api_key: str, model: str, endpoint: str) -> tuple[str, str]:
    try:
        return _upload_transcribe(path, api_key, model, endpoint), ""
    except urllib.error.HTTPError as exc:
        return "", f"http_{exc.code}"
    except (OSError, TimeoutError, urllib.error.URLError) as exc:
        return "", type(exc).__name__


def transcribe(item: dict[str, Any], context: dict[str, Any]) -> dict[str, str]:
    """Download video/play with Referer, extract audio, transcribe via SiliconFlow."""
    if is_image_post(item):
        return skipped_image("siliconflow_sensevoice")
    readiness = check_environment()
    if not readiness["ready"]:
        raise ValueError(f"SiliconFlow transcription is not ready: {', '.join(readiness['missing'])}")

    candidates = _candidate_urls(item)
    if not candidates:
        return _failed("unavailable")

    api_key = os.environ[KEY_NAME].strip()
    ctx = context if isinstance(context, dict) else {}
    options = ctx.get("options") if isinstance(ctx.get("options"), dict) else {}
    max_media_bytes = int(options.get("max_media_bytes", MAX_MEDIA_BYTES) or MAX_MEDIA_BYTES)
    model = str(ctx.get("model") or os.environ.get("SILICONFLOW_ASR_MODEL") or DEFAULT_MODEL).strip()
    endpoint = str(os.environ.get("SILICONFLOW_ASR_URL") or DEFAULT_ENDPOINT).strip()

    last_status = "failed"
    last_error = ""
    try:
        with tempfile.TemporaryDirectory(prefix=TEMP_PREFIX) as temp_dir:
            root = Path(temp_dir)
            for kind, url in candidates:
                media_path = root / f"source-{kind}{_suffix_for_url(url)}"
                err = _download_media(url, media_path, max_media_bytes)
                if err:
                    last_status = err if err in {"too_large", "unavailable"} else "failed"
                    last_error = err
                    continue
                upload_path = _prepare_upload(media_path, root)
                text, upload_error = _transcribe_file(upload_path, api_key, model, endpoint)
                if text:
                    return _success(text, "siliconflow_sensevoice", kind)
                if upload_error:
                    last_status = "failed"
                    last_error = upload_error
                else:
                    last_status = "unavailable"
                    last_error = "empty_transcript"
                if model == DEFAULT_MODEL:
                    fallback, fallback_error = _transcribe_file(upload_path, api_key, FALLBACK_MODEL, endpoint)
                    if fallback:
                        return _success(fallback, "siliconflow_xingchen_asr", kind)
                    if fallback_error and not upload_error:
                        last_error = fallback_error
    except (OSError, subprocess.TimeoutExpired, TimeoutError) as exc:
        return _failed("failed", type(exc).__name__)
    except Exception as exc:
        return _failed("failed", type(exc).__name__)

    return _failed(last_status, last_error)
