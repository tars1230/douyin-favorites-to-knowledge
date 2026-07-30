from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .config import Config
from .security import assert_safe_value


SCHEMA_VERSION = 1
AWEME_ID = re.compile(r"^[0-9]{6,30}$")
SOURCES = frozenset({"collection", "like", "import"})
ANALYSIS_FIELDS = (
    "content_summary",
    "value_judgment",
    "deep_analysis",
    "extensions",
    "action_items",
    "related_knowledge",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def file_sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _text(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"item {key} must be a string")
    return value.replace("\r\n", "\n").replace("\r", "\n").strip()


def _analysis(raw: dict[str, Any]) -> dict[str, str]:
    value = raw.get("analysis")
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("item analysis must be an object")
    unknown = set(value) - set(ANALYSIS_FIELDS)
    if unknown:
        raise ValueError(f"item analysis has unknown fields: {sorted(unknown)}")
    result: dict[str, str] = {}
    for key in ANALYSIS_FIELDS:
        if key not in value:
            continue
        field_value = value[key]
        if not isinstance(field_value, str):
            raise ValueError(f"item analysis {key} must be a string")
        text = field_value.replace("\r\n", "\n").replace("\r", "\n").strip()
        if text:
            result[key] = text
    return result


def normalize_item(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("each source item must be an object")
    assert_safe_value(raw, "source_item")
    aweme_id = str(raw.get("aweme_id", "")).strip()
    if not AWEME_ID.fullmatch(aweme_id):
        raise ValueError(f"invalid aweme_id: {aweme_id!r}")
    title = _text(raw, "title") or _text(raw, "description")
    if not title:
        raise ValueError(f"item {aweme_id} has no title or description")
    tags = raw.get("tags") or []
    if not isinstance(tags, list) or not all(isinstance(tag, str) and tag.strip() for tag in tags):
        raise ValueError(f"item {aweme_id} tags must be non-empty strings")
    transcript = _text(raw, "transcript")
    source = _text(raw, "source") or "import"
    if source not in SOURCES:
        raise ValueError(f"unsupported item source: {source!r}")
    item = {
        "aweme_id": aweme_id,
        "title": title,
        "author": _text(raw, "author"),
        "description": _text(raw, "description"),
        "transcript": transcript,
        "transcript_source": _text(raw, "transcript_source") or ("provided" if transcript else "none"),
        "transcript_status": _text(raw, "transcript_status") or ("success" if transcript else "not_requested"),
        "tags": sorted(set(tag.strip() for tag in tags)),
        "observed_at": _text(raw, "observed_at"),
        "source_url": f"https://www.douyin.com/video/{aweme_id}",
        "source": source,
    }
    analysis = _analysis(raw)
    if analysis:
        item["analysis"] = analysis
    item["content_sha256"] = sha256_bytes(canonical_json(item))
    item["note"] = render_note(item)
    return item


def render_note(item: dict[str, Any]) -> str:
    quote = lambda value: json.dumps(value, ensure_ascii=False)
    lines = [
        "---",
        f"aweme_id: {quote(item['aweme_id'])}",
        f"title: {quote(item['title'])}",
        f"author: {quote(item['author'])}",
        f"source_url: {quote(item['source_url'])}",
        f"observed_at: {quote(item['observed_at'])}",
        f"tags: {json.dumps(item['tags'], ensure_ascii=False)}",
        f"source: {quote(item['source'])}",
        f"transcript_source: {quote(item['transcript_source'])}",
        f"transcript_status: {quote(item['transcript_status'])}",
        "---",
        "",
        f"# {item['title']}",
        "",
    ]
    analysis = item.get("analysis", {})
    if analysis.get("content_summary"):
        lines.extend(["## 要点", "", analysis["content_summary"], ""])

    if item["description"] or item["transcript"] or item["transcript_status"] != "not_requested":
        lines.extend(["## 原始材料", ""])
        if item["description"]:
            lines.extend(["### 原始描述", "", item["description"], ""])
        if item["transcript"]:
            lines.extend(["### 转录", "", item["transcript"], ""])
        elif item["transcript_status"] != "not_requested":
            lines.extend(["### 转录", "", "未获得语音转录；上方原始描述不是逐字稿。", ""])

    analysis_sections = (
        ("value_judgment", "价值判断"),
        ("deep_analysis", "深度分析"),
        ("extensions", "延展补充"),
        ("action_items", "行动启示"),
        ("related_knowledge", "关联知识"),
    )
    if any(analysis.get(key) for key, _ in analysis_sections):
        lines.extend(["## 研判", ""])
    for key, heading in analysis_sections:
        if analysis.get(key):
            lines.extend([f"### {heading}", "", analysis[key], ""])
    lines.extend(["## Source", "", item["source_url"], ""])
    note = "\n".join(lines)
    assert_safe_value(note, f"note:{item['aweme_id']}")
    return note


def read_input(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read source input: {exc}") from exc
    items = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise ValueError("source input must be a list or an object containing items")
    return items


def load_ledger(config: Config) -> dict[str, str]:
    if not config.ledger_path.exists():
        return {}
    with sqlite3.connect(config.ledger_path) as connection:
        exists = connection.execute(
            "select 1 from sqlite_master where type='table' and name='promotions'"
        ).fetchone()
        if not exists:
            return {}
        return dict(connection.execute("select aweme_id, content_sha256 from promotions"))


def _known_hash(known: dict[str, str], item: dict[str, Any]) -> str | None:
    """v1 collection entries used a bare aweme_id before source separation."""
    keyed = known.get(f"{item['source']}:{item['aweme_id']}")
    if keyed:
        return keyed
    if item["source"] == "collection" and item["aweme_id"] in known:
        return "legacy"
    return None


def build_review(
    config: Config,
    raw_items: Iterable[dict[str, Any]],
    source_label: str,
) -> dict[str, Any]:
    assert_safe_value(source_label, "source_label")
    known = load_ledger(config)
    normalized: dict[str, dict[str, Any]] = {}
    input_count = 0
    already_promoted = 0
    for raw in raw_items:
        input_count += 1
        item = normalize_item(raw)
        previous = normalized.get(item["aweme_id"])
        if previous:
            if previous["content_sha256"] != item["content_sha256"]:
                raise ValueError(f"conflicting duplicate aweme_id: {item['aweme_id']}")
            continue
        known_hash = _known_hash(known, item)
        if known_hash:
            if known_hash == "legacy":
                already_promoted += 1
                continue
            if known_hash != item["content_sha256"]:
                raise ValueError(
                    f"promoted item changed: {item['aweme_id']}; manual migration required"
                )
            already_promoted += 1
            continue
        normalized[item["aweme_id"]] = item
    items = [normalized[key] for key in sorted(normalized)]
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "source_label": source_label,
        "summary": {
            "input_count": input_count,
            "candidate_count": len(items),
            "already_promoted_count": already_promoted,
        },
        "items": items,
    }


def validate_review(review: dict[str, Any]) -> list[dict[str, Any]]:
    assert_safe_value(review, "review")
    if not isinstance(review, dict) or review.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("review schema_version must be 1")
    items = review.get("items")
    if not isinstance(items, list):
        raise ValueError("review items must be a list")
    seen: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"review item {index} must be an object")
        required = {
            "aweme_id",
            "title",
            "author",
            "description",
            "transcript",
            "transcript_source",
            "transcript_status",
            "tags",
            "observed_at",
            "source_url",
            "source",
            "content_sha256",
            "note",
        }
        optional = {"analysis"}
        if set(item) - optional != required or not set(item) <= required | optional:
            raise ValueError(f"review item {index} fields do not match schema")
        aweme_id = item["aweme_id"]
        if aweme_id in seen:
            raise ValueError(f"duplicate aweme_id in review: {aweme_id}")
        seen.add(aweme_id)
        base = {key: item[key] for key in required - {"content_sha256", "note"}}
        if "analysis" in item:
            normalized_analysis = _analysis({"analysis": item["analysis"]})
            if normalized_analysis != item["analysis"]:
                raise ValueError(f"invalid analysis fields for {aweme_id}")
            base["analysis"] = item["analysis"]
        expected_hash = sha256_bytes(canonical_json(base))
        if item["content_sha256"] != expected_hash:
            raise ValueError(f"content hash mismatch for {aweme_id}")
        if item["note"] != render_note(item):
            raise ValueError(f"rendered note mismatch for {aweme_id}")
    return items


def read_review(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read review: {exc}") from exc
    validate_review(payload)
    return payload


def build_approval(review_path: Path, approved_ids: list[str]) -> dict[str, Any]:
    review = read_review(review_path)
    available = {item["aweme_id"] for item in review["items"]}
    approved = sorted(set(approved_ids))
    if not approved:
        raise ValueError("approval must contain at least one aweme_id")
    unknown = set(approved) - available
    if unknown:
        raise ValueError(f"approval references unknown IDs: {sorted(unknown)}")
    return {
        "schema_version": SCHEMA_VERSION,
        "review_sha256": file_sha256(review_path),
        "approved_at": utc_now(),
        "approved_ids": approved,
    }


def read_approval(path: Path, review_path: Path) -> dict[str, Any]:
    try:
        approval = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read approval: {exc}") from exc
    assert_safe_value(approval, "approval")
    required = {"schema_version", "review_sha256", "approved_at", "approved_ids"}
    if not isinstance(approval, dict) or set(approval) != required:
        raise ValueError("approval fields do not match schema")
    if approval["schema_version"] != SCHEMA_VERSION:
        raise ValueError("approval schema_version must be 1")
    if approval["review_sha256"] != file_sha256(review_path):
        raise ValueError("review changed after approval")
    if not isinstance(approval["approved_ids"], list) or not approval["approved_ids"]:
        raise ValueError("approval approved_ids must be a non-empty list")
    return approval


def _promotion_plan(
    config: Config,
    selected: list[dict[str, Any]],
    known: dict[str, str],
) -> tuple[list[dict[str, Any]], int]:
    pending: list[dict[str, Any]] = []
    skipped = 0
    for item in selected:
        aweme_id = item["aweme_id"]
        known_hash = _known_hash(known, item)
        if known_hash:
            if known_hash == "legacy":
                skipped += 1
                continue
            if known_hash != item["content_sha256"]:
                raise ValueError(f"ledger content conflict for {aweme_id}")
            skipped += 1
            continue
        final_path = config.knowledge_dir / f"{item['source']}-{aweme_id}.md"
        if final_path.exists() and final_path.read_text(encoding="utf-8") != item["note"]:
            raise ValueError(f"untracked note conflict for {aweme_id}")
        pending.append(item)
    return pending, skipped


def promote(
    config: Config,
    review_path: Path,
    approval_path: Path,
    dry_run: bool = False,
) -> dict[str, Any]:
    review = read_review(review_path)
    approval = read_approval(approval_path, review_path)
    by_id = {item["aweme_id"]: item for item in review["items"]}
    unknown = set(approval["approved_ids"]) - set(by_id)
    if unknown:
        raise ValueError(f"approval references unknown IDs: {sorted(unknown)}")
    selected = [by_id[aweme_id] for aweme_id in approval["approved_ids"]]

    if dry_run:
        pending, skipped = _promotion_plan(config, selected, load_ledger(config))
        return {
            "promoted_count": len(pending),
            "skipped_count": skipped,
            "ids": [item["aweme_id"] for item in pending],
        }

    config.knowledge_dir.mkdir(parents=True, exist_ok=True)
    config.ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(config.ledger_path, timeout=30) as connection:
        connection.execute("pragma busy_timeout=30000")
        connection.execute(
            """
            create table if not exists promotions (
                aweme_id text primary key,
                content_sha256 text not null,
                note_name text not null,
                review_sha256 text not null,
                promoted_at text not null
            )
            """
        )
        connection.commit()
        connection.execute("begin immediate")
        known = dict(connection.execute("select aweme_id, content_sha256 from promotions"))
        pending, skipped = _promotion_plan(config, selected, known)
        result = {
            "promoted_count": len(pending),
            "skipped_count": skipped,
            "ids": [item["aweme_id"] for item in pending],
        }
        if not pending:
            connection.commit()
            return result

        staging = Path(tempfile.mkdtemp(prefix=".promote-", dir=config.knowledge_dir))
        try:
            for item in pending:
                staged = staging / f"{item['source']}-{item['aweme_id']}.md"
                staged.write_text(item["note"], encoding="utf-8")
                with staged.open("rb") as handle:
                    os.fsync(handle.fileno())
            for item in pending:
                os.replace(
                    staging / f"{item['source']}-{item['aweme_id']}.md",
                    config.knowledge_dir / f"{item['source']}-{item['aweme_id']}.md",
                )

            now = utc_now()
            review_hash = file_sha256(review_path)
            connection.executemany(
                "insert into promotions values (?, ?, ?, ?, ?)",
                [
                    (
                        f"{item['source']}:{item['aweme_id']}",
                        item["content_sha256"],
                        f"{item['source']}-{item['aweme_id']}.md",
                        review_hash,
                        now,
                    )
                    for item in pending
                ],
            )
            connection.commit()
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        return result
