from __future__ import annotations

from pathlib import Path

from .workflow import atomic_write_text


FEISHU_FIELDS = (
    "标题（文本）\n"
    "来源类型（单选：收藏、喜欢）\n"
    "作者（文本）\n"
    "原视频（超链接）\n"
    "标签（多选）\n"
    "转录状态（单选）\n"
    "沉淀时间（日期）\n"
    "Obsidian 笔记（文本）\n"
)

NOTE_TEMPLATE = (
    "---\n来源类型: {source}\n作者: \n原视频: \n标签: []\n转录状态: \n沉淀时间: \n---\n\n"
    "# {{title}}\n\n"
    "## 原始材料\n\n"
    "### 原始描述\n\n"
    "### 转录\n\n"
    "## 来源\n"
)


def initialize_obsidian(vault: Path, subdir: str) -> Path:
    name = subdir.strip().strip("/\\")
    if not name or name in {".", ".."}:
        raise ValueError("Obsidian 子目录不能为空")
    knowledge_dir = vault.expanduser().resolve() / name
    for directory in ("收藏", "喜欢", "日报", "模板", "系统"):
        (knowledge_dir / directory).mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        knowledge_dir / "模板" / "抖音收藏.md",
        NOTE_TEMPLATE.format(source="收藏"),
    )
    atomic_write_text(
        knowledge_dir / "模板" / "抖音喜欢.md",
        NOTE_TEMPLATE.format(source="喜欢"),
    )
    atomic_write_text(
        knowledge_dir / "日报索引.md",
        "# 抖音日报索引\n\n日报由每日同步写入 `日报/`。收藏与喜欢分别统计，不会混合。\n",
    )
    write_feishu_fields_template(knowledge_dir)
    probe = knowledge_dir / "系统" / ".write-check.md"
    atomic_write_text(probe, "ok\n")
    probe.unlink()
    return knowledge_dir


def write_feishu_fields_template(knowledge_dir: Path) -> None:
    atomic_write_text(
        knowledge_dir / "系统" / "飞书多维表字段模板.md",
        "# 飞书多维表字段\n\n" + FEISHU_FIELDS,
    )
