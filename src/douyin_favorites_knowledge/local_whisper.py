from __future__ import annotations

import importlib.util
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any


MIN_FREE_BYTES = 1_500_000_000
MAX_MEDIA_BYTES = 512 * 1024 * 1024
TEMP_PREFIX = "douyin-local-asr-"
STALE_TEMP_SECONDS = 24 * 60 * 60


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


def _failed(status: str) -> dict[str, str]:
    return {"transcript": "", "transcript_source": "local_whisper", "transcript_status": status}


def transcribe(item: dict[str, Any], context: dict[str, Any]) -> dict[str, str]:
    """Download an authorized temporary play URL, extract audio, and transcribe locally."""
    readiness = check_environment()
    if not readiness["ready"]:
        raise ValueError(f"local Whisper transcription is not ready: {', '.join(readiness['missing'])}")
    play_url = str(item.get("play_url") or "").strip()
    if not play_url:
        return _failed("unavailable")
    model_name = str(context.get("model") or "small").strip() or "small"
    options = context.get("options") if isinstance(context.get("options"), dict) else {}
    max_media_bytes = int(options.get("max_media_bytes", MAX_MEDIA_BYTES))
    if max_media_bytes <= 0:
        return _failed("failed")
    try:
        with tempfile.TemporaryDirectory(prefix="douyin-local-asr-") as temp_dir:
            root = Path(temp_dir)
            media_path = root / "source.mp4"
            audio_path = root / "audio.wav"
            request = urllib.request.Request(play_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=180) as response, media_path.open("wb") as output:
                declared = response.headers.get("Content-Length")
                if declared:
                    try:
                        if int(declared) > max_media_bytes:
                            return _failed("too_large")
                    except ValueError:
                        pass
                total = 0
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_media_bytes:
                        return _failed("too_large")
                    output.write(chunk)
            extracted = subprocess.run(
                ["ffmpeg", "-y", "-i", str(media_path), "-vn", "-ac", "1", "-ar", "16000", str(audio_path)],
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            if extracted.returncode != 0:
                return _failed("failed")
            from faster_whisper import WhisperModel

            model = WhisperModel(model_name, device="cpu", compute_type="int8")
            segments, _ = model.transcribe(str(audio_path), vad_filter=True, task="transcribe")
            transcript = "\n".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
    except (OSError, subprocess.TimeoutExpired, TimeoutError):
        return _failed("failed")
    except Exception:
        return _failed("failed")
    if not transcript:
        return _failed("unavailable")
    return {"transcript": transcript, "transcript_source": "local_whisper", "transcript_status": "success"}
