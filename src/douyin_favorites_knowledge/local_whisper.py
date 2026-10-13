from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .media_kind import is_image_post, skipped_image


MIN_FREE_BYTES = 1_500_000_000
MAX_MEDIA_BYTES = 512 * 1024 * 1024
TEMP_PREFIX = "douyin-local-asr-"
STALE_TEMP_SECONDS = 24 * 60 * 60
DEFAULT_SAMPLE_RATE = "16000"
_MODEL_CACHE: dict[str, Any] = {}
_MODEL_ERRORS: dict[str, str] = {}


def cleanup_stale_temp_dirs() -> int:
    """Remove abandoned media workspaces left by a killed process."""
    root = Path(tempfile.gettempdir())
    removed = 0
    now = time.time()
    for path in root.glob(f"{TEMP_PREFIX}*"):
        try:
            if path.is_dir() and now - path.stat().st_mtime > STALE_TEMP_SECONDS:
                shutil.rmtree(path)
                removed += 1
        except OSError:
            continue
    return removed


def check_environment() -> dict[str, Any]:
    """Check prerequisites only; never download a model during a health check."""
    cleanup_stale_temp_dirs()
    missing: list[str] = []
    if not shutil.which("ffmpeg"):
        missing.append("ffmpeg")
    if importlib.util.find_spec("faster_whisper") is None:
        missing.append("faster-whisper (install .[local-asr])")
    if shutil.disk_usage(tempfile.gettempdir()).free < MIN_FREE_BYTES:
        missing.append("at least 1.5 GB temporary disk space")
    return {"ready": not missing, **({"missing": missing} if missing else {})}


def _failed(status: str, error: str = "") -> dict[str, str]:
    result = {"transcript": "", "transcript_source": "local_whisper", "transcript_status": status}
    if error:
        result["transcript_error"] = error[:180]
    return result


def _sample_rate() -> str:
    rate = (os.environ.get("DOUYIN_ASR_SAMPLE_RATE") or DEFAULT_SAMPLE_RATE).strip() or DEFAULT_SAMPLE_RATE
    return rate if re.fullmatch(r"\d{4,6}", rate) else DEFAULT_SAMPLE_RATE


def _candidate_urls(item: dict[str, Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    # Video/play only — skip audio_url (often commercial BGM, not speech).
    for key in ("play_url", "video_url"):
        url = str(item.get(key) or "").strip()
        if url and url not in seen:
            seen.add(url)
            out.append(url)
    return out


def _suffix_for_url(url: str) -> str:
    path = url.split("?", 1)[0].lower()
    for ext in (".m4a", ".mp3", ".aac", ".wav", ".mp4", ".webm", ".mov"):
        if path.endswith(ext):
            return ext
    return ".bin"


def _download(url: str, destination: Path, max_media_bytes: int) -> tuple[str | None, str]:
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
                    if int(declared) > max_media_bytes:
                        return "too_large", "too_large"
                except ValueError:
                    pass
            total = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_media_bytes:
                    return "too_large", "too_large"
                output.write(chunk)
    except urllib.error.HTTPError as exc:
        return "failed", f"http_{exc.code}"
    except Exception as exc:
        return "failed", type(exc).__name__
    if destination.exists() and destination.stat().st_size > 0:
        return None, ""
    return "failed", "empty_download"


def _load_model(model_name: str):
    """Load each Whisper model once. A load failure must stop the run, not mark every item retryable."""
    cached = _MODEL_CACHE.get(model_name)
    if cached is not None:
        return cached
    previous = _MODEL_ERRORS.get(model_name)
    if previous:
        raise RuntimeError(previous)
    try:
        from faster_whisper import WhisperModel

        model = WhisperModel(model_name, device="cpu", compute_type="int8")
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        _MODEL_ERRORS[model_name] = message[:300]
        raise RuntimeError(message) from exc
    _MODEL_CACHE[model_name] = model
    return model


def transcribe(item: dict[str, Any], context: dict[str, Any]) -> dict[str, str]:
    """Download authorized play/video media, extract audio, transcribe locally."""
    if is_image_post(item):
        return skipped_image("local_whisper")
    readiness = check_environment()
    if not readiness["ready"]:
        raise ValueError(f"local Whisper transcription is not ready: {', '.join(readiness['missing'])}")
    candidates = _candidate_urls(item)
    if not candidates:
        return _failed("unavailable")
    model_name = str(context.get("model") or "small").strip() or "small"
    options = context.get("options") if isinstance(context.get("options"), dict) else {}
    max_media_bytes = int(options.get("max_media_bytes", MAX_MEDIA_BYTES))
    if max_media_bytes <= 0:
        return _failed("failed", "invalid_media_limit")

    last = "failed"
    last_error = ""
    try:
        with tempfile.TemporaryDirectory(prefix=TEMP_PREFIX) as temp_dir:
            root = Path(temp_dir)
            audio_path = root / "audio.wav"
            rate = _sample_rate()
            extracted_ok = False
            for idx, url in enumerate(candidates):
                media_path = root / f"source-{idx}{_suffix_for_url(url)}"
                err, reason = _download(url, media_path, max_media_bytes)
                if err:
                    last = err
                    last_error = reason or err
                    continue
                extracted = subprocess.run(
                    ["ffmpeg", "-nostdin", "-y", "-i", str(media_path), "-vn", "-ac", "1", "-ar", rate, str(audio_path)],
                    capture_output=True,
                    text=True,
                    timeout=180,
                    check=False,
                )
                if extracted.returncode != 0:
                    last = "failed"
                    last_error = "ffmpeg_extract_failed"
                    continue
                extracted_ok = True
                break
            if not extracted_ok:
                return _failed(last, last_error)
            model = _load_model(model_name)
            segments, _ = model.transcribe(str(audio_path), vad_filter=True, task="transcribe")
            transcript = "\n".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
            if transcript:
                return {
                    "transcript": transcript,
                    "transcript_source": "local_whisper",
                    "transcript_status": "success",
                }
            return _failed("unavailable", "no_speech")
    except RuntimeError:
        raise
    except (OSError, subprocess.TimeoutExpired, TimeoutError) as exc:
        return _failed("failed", type(exc).__name__)
    except Exception as exc:
        return _failed("failed", type(exc).__name__)

