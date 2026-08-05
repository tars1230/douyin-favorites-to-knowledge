from __future__ import annotations

import importlib.util
import os
from typing import Any


KEY_NAME = "DASHSCOPE_API_KEY"
MODEL = "qwen3-asr-flash"


def check_environment() -> dict[str, Any]:
    """Check direct Bailian ASR prerequisites without calling the service."""
    missing: list[str] = []
    if not os.environ.get(KEY_NAME, "").strip():
        missing.append(KEY_NAME)
    if importlib.util.find_spec("dashscope") is None:
        missing.append("dashscope (install .[bailian-asr])")
    return {"ready": not missing, **({"missing": missing} if missing else {})}


def _failed(status: str) -> dict[str, str]:
    return {"transcript": "", "transcript_source": "bailian_qwen3_asr_flash", "transcript_status": status}


def _response_text(response: Any) -> str:
    try:
        content = response.output.choices[0].message.content
    except (AttributeError, IndexError, TypeError):
        return ""
    if isinstance(content, list):
        return "\n".join(str(part.get("text", "")).strip() for part in content if isinstance(part, dict)).strip()
    return ""


def transcribe(item: dict[str, Any], context: dict[str, Any]) -> dict[str, str]:
    """Send play URL to DashScope URL-ASR (no local download).

    Warning: Douyin CDN (*.douyinvod.com) is often unreachable from Bailian servers.
    Prefer siliconflow.transcribe for Douyin media.
    """
    readiness = check_environment()
    if not readiness["ready"]:
        raise ValueError(f"Bailian transcription is not ready: {', '.join(readiness['missing'])}")
    play_url = str(item.get("play_url") or "").strip()
    if not play_url:
        return _failed("unavailable")
    try:
        import dashscope

        response = dashscope.MultiModalConversation.call(
            api_key=os.environ[KEY_NAME],
            model=str(context.get("model") or MODEL),
            messages=[
                {"role": "system", "content": [{"text": ""}]},
                {"role": "user", "content": [{"audio": play_url}]},
            ],
            result_format="message",
            asr_options={"enable_lid": True, "enable_itn": False},
        )
    except Exception:
        return _failed("failed")
    transcript = _response_text(response)
    if not transcript:
        return _failed("unavailable")
    return {"transcript": transcript, "transcript_source": "bailian_qwen3_asr_flash", "transcript_status": "success"}
