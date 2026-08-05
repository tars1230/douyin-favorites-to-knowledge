from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
from typing import Any

from .bailian import check_environment as check_bailian
from .local_whisper import check_environment as check_local_whisper
from .siliconflow import check_environment as check_siliconflow


def _minimax_status() -> dict[str, Any]:
    """Recognize only an explicit local ASR interface, never infer it from a key alone."""
    if not shutil.which("mmx"):
        return {"state": "unavailable", "reason": "未发现 MiniMax 命令行转录接口"}
    try:
        result = subprocess.run(["mmx", "speech", "--help"], capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return {"state": "unavailable", "reason": "无法确认 MiniMax 是否提供转录接口"}
    help_text = f"{result.stdout}\n{result.stderr}".lower()
    if any(term in help_text for term in ("transcribe", "recognize", " asr")):
        return {"state": "candidate", "reason": "发现候选 ASR 命令；需确认兼容接口后才能启用"}
    return {"state": "unavailable", "reason": "已发现 mmx，但当前只暴露语音生成，不是转录接口"}


def discover() -> dict[str, Any]:
    """Return credential-free, non-billing readiness information for setup and diagnostics."""
    silicon = check_siliconflow()
    bailian = check_bailian()
    local = check_local_whisper()
    if silicon["ready"]:
        recommended = "siliconflow"
    elif bailian["ready"]:
        recommended = "bailian"
    elif local["ready"]:
        recommended = "local"
    else:
        recommended = "siliconflow"
    return {
        "siliconflow": {
            "state": "ready" if silicon["ready"] else "action_required",
            **({"missing": silicon["missing"]} if not silicon["ready"] else {}),
            "note": "Douyin CDN 推荐主路径：本机 Referer 下载后上传 SenseVoice",
        },
        "bailian": {
            "state": "ready" if bailian["ready"] else "action_required",
            **({"missing": bailian["missing"]} if not bailian["ready"] else {}),
            "note": "URL-ASR；抖音 douyinvod CDN 服务端常拉不到，不作为默认推荐",
        },
        "local_whisper": {
            "state": "ready" if local["ready"] else "action_required",
            **({"missing": local["missing"]} if not local["ready"] else {}),
        },
        "minimax": _minimax_status(),
        "recommended": recommended,
    }
