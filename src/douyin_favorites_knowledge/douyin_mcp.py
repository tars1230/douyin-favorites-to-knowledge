from __future__ import annotations

import json
import os
import shutil
import subprocess
import re
from typing import Any


MCP_SERVER = "douyin-mcp"
MCP_TOOL = "douyin-mcp.extract_douyin_text"
KEY_NAME = "DASHSCOPE_API_KEY"
MIN_SERVER_VERSION = (1, 2, 1)


def _configured_server_is_current() -> bool:
    """Reject an explicitly configured legacy server that used a different ASR provider."""
    try:
        result = subprocess.run(
            ["mcporter", "config", "get", MCP_SERVER, "--json"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return True
    if result.returncode != 0:
        return True
    match = re.search(r"douyin-mcp-server@(\d+)\.(\d+)\.(\d+)", result.stdout)
    if not match:
        return True
    return tuple(int(part) for part in match.groups()) >= MIN_SERVER_VERSION


def check_environment() -> dict[str, Any]:
    """Report readiness without exposing credentials or local configuration paths."""
    missing: list[str] = []
    if not os.environ.get(KEY_NAME, "").strip():
        missing.append(KEY_NAME)
    if not shutil.which("mcporter"):
        missing.append("mcporter")
    if missing:
        return {"ready": False, "missing": missing}
    try:
        result = subprocess.run(
            ["mcporter", "list"], capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"ready": False, "missing": [MCP_SERVER]}
    if result.returncode != 0 or MCP_SERVER not in f"{result.stdout}\n{result.stderr}":
        return {"ready": False, "missing": [MCP_SERVER]}
    if not _configured_server_is_current():
        return {"ready": False, "missing": ["douyin-mcp-server>=1.2.1"]}
    return {"ready": True}


def _extract_text(value: Any) -> str:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ""
        try:
            return _extract_text(json.loads(text))
        except json.JSONDecodeError:
            return text
    if isinstance(value, dict):
        for key in ("transcript", "result", "content", "text", "data"):
            if key in value:
                text = _extract_text(value[key])
                if text:
                    return text
    if isinstance(value, list):
        return "\n".join(part for part in (_extract_text(item) for item in value) if part)
    return ""


def transcribe(item: dict[str, Any], _context: dict[str, Any]) -> dict[str, str]:
    """Use the user's configured douyin-mcp service to extract speech text."""
    readiness = check_environment()
    if not readiness["ready"]:
        raise ValueError(f"douyin-mcp transcription is not ready: {', '.join(readiness['missing'])}")
    source_url = str(item.get("source_url") or "").strip()
    if not source_url:
        raise ValueError("cannot transcribe an item without source_url")
    try:
        result = subprocess.run(
            ["mcporter", "call", MCP_TOOL, f"share_link={source_url}"],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"transcript": "", "transcript_source": "none", "transcript_status": "timeout"}
    except OSError:
        return {"transcript": "", "transcript_source": "none", "transcript_status": "failed"}
    if result.returncode != 0:
        return {"transcript": "", "transcript_source": "none", "transcript_status": "failed"}
    try:
        payload: Any = json.loads(result.stdout)
    except json.JSONDecodeError:
        payload = result.stdout
    transcript = _extract_text(payload)
    if not transcript:
        return {"transcript": "", "transcript_source": "none", "transcript_status": "unavailable"}
    return {"transcript": transcript, "transcript_source": "douyin_mcp", "transcript_status": "success"}
