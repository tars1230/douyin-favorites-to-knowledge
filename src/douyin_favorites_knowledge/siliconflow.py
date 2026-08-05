# -*- coding: utf-8 -*-
"""SiliconFlow SenseVoice ASR for Douyin CDN media.

Douyin ``*.douyinvod.com`` play URLs require browser-like Referer headers and
cannot be fetched by Bailian server-side URL-ASR. This provider downloads with
Referer, optionally extracts audio via ffmpeg, and uploads to SiliconFlow.
"""
from __future__ import annotations

import mimetypes
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

KEY_NAME = "SILICONFLOW_API_KEY"
DEFAULT_MODEL = "FunAudioLLM/SenseVoiceSmall"
DEFAULT_ENDPOINT = "https://api.siliconflow.cn/v1/audio/transcriptions"
MAX_MEDIA_BYTES = 512 * 1024 * 1024
TEMP_PREFIX = "douyin-sf-asr-"


def check_environment() -> dict[str, Any]:
    """Check prerequisites only; never call the API during health checks."""
    missing: list[str] = []
    if not os.environ.get(KEY_NAME, "").strip():
        missing.append(KEY_NAME)
    # ffmpeg optional: upload raw media if missing
    return {"ready": not missing, **({"missing": missing} if missing else {})}


def _failed(status: str) -> dict[str, str]:
    return {
        "transcript": "",
        "transcript_source": "siliconflow_sensevoice",
        "transcript_status": status,
    }


def _download_media(url: str, destination: Path, max_bytes: int) -> str | None:
    """Download media. Return error status or None on success."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.douyin.com/",
            "Origin": "https://www.douyin.com",
            "Accept": "*/*",
        },
    )
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
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
        return "failed"
    return None if destination.exists() and destination.stat().st_size > 0 else "failed"


def _extract_audio(source: Path, audio: Path) -> bool:
    if not shutil.which("ffmpeg"):
        return False
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
            "16000",
            "-b:a",
            "64k",
            str(audio),
        ],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    return completed.returncode == 0 and audio.exists() and audio.stat().st_size > 0


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


def transcribe(item: dict[str, Any], context: dict[str, Any]) -> dict[str, str]:
    """Download authorized play_url with Referer and transcribe via SiliconFlow."""
    readiness = check_environment()
    if not readiness["ready"]:
        raise ValueError(f"SiliconFlow transcription is not ready: {', '.join(readiness['missing'])}")
    play_url = str(item.get("play_url") or "").strip()
    if not play_url:
        return _failed("unavailable")

    api_key = os.environ[KEY_NAME].strip()
    ctx = context if isinstance(context, dict) else {}
    options = ctx.get("options") if isinstance(ctx.get("options"), dict) else {}
    max_media_bytes = int(options.get("max_media_bytes", MAX_MEDIA_BYTES) or MAX_MEDIA_BYTES)
    model = str(ctx.get("model") or os.environ.get("SILICONFLOW_ASR_MODEL") or DEFAULT_MODEL).strip()
    endpoint = str(os.environ.get("SILICONFLOW_ASR_URL") or DEFAULT_ENDPOINT).strip()

    try:
        with tempfile.TemporaryDirectory(prefix=TEMP_PREFIX) as temp_dir:
            root = Path(temp_dir)
            media_path = root / "source.mp4"
            err = _download_media(play_url, media_path, max_media_bytes)
            if err:
                return _failed(err)
            upload_path = media_path
            audio_path = root / "audio.mp3"
            if _extract_audio(media_path, audio_path):
                upload_path = audio_path
            text = _upload_transcribe(upload_path, api_key, model, endpoint)
    except (OSError, subprocess.TimeoutExpired, TimeoutError, urllib.error.HTTPError, urllib.error.URLError):
        return _failed("failed")
    except Exception:
        return _failed("failed")

    if not text:
        return _failed("unavailable")
    return {
        "transcript": text,
        "transcript_source": "siliconflow_sensevoice",
        "transcript_status": "success",
    }
