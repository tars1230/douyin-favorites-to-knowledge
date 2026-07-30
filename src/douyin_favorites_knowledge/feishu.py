from __future__ import annotations

import json
import os
from urllib.request import Request, urlopen


def notify_webhook(result: dict, _context: dict) -> None:
    webhook = os.environ.get("FEISHU_WEBHOOK_URL", "").strip()
    if not webhook:
        raise ValueError("飞书 webhook 未配置；请设置 FEISHU_WEBHOOK_URL")
    count = result.get("promoted_count", 0)
    payload = {"msg_type": "text", "content": {"text": f"抖音知识库已沉淀 {count} 条新笔记。"}}
    request = Request(
        webhook,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        if response.status // 100 != 2:
            raise ValueError("飞书 webhook 返回非成功状态")
