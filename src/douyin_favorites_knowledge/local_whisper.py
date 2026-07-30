from __future__ import annotations

import importlib.util
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import Any


MIN_FREE_BYTES = 1_500_000_000


def check_environment() -> dict[str, Any]:
    """Check prerequisites only; never download a model during a health check."""
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
    try:
        from faster_whisper import WhisperModel

        with tempfile.TemporaryDirectory(prefix="douyin-local-asr-") as temp_dir:
            root = Path(temp_dir)
            media_path = root / "source.mp4"
            audio_path = root / "audio.wav"
            request = urllib.request.Request(play_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=180) as response, media_path.open("wb") as output:
                shutil.copyfileobj(response, output)
            extracted = subprocess.run(
                ["ffmpeg", "-y", "-i", str(media_path), "-vn", "-ac", "1", "-ar", "16000", str(audio_path)],
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            if extracted.returncode != 0:
                return _failed("failed")
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
