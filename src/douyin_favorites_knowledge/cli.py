from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .adapters import load_adapter
from .browser_collector import browser_status, collect_browser_favorites, login_browser, logout_browser
from .config import Config, StageConfig, load_config
from .security import safe_error_message
from .workflow import (
    atomic_write_json,
    build_approval,
    build_review,
    promote,
    read_input,
    read_review,
)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="将审核通过的抖音收藏写入本地知识库")
    root.add_argument("--config", type=Path, help="schema_version 为 1 或 2 的 JSON 配置路径")
    commands = root.add_subparsers(dest="command", required=True)

    login = commands.add_parser("login", help="打开本地浏览器并保存授权登录状态")
    login.add_argument("--timeout", type=int, default=300, help="等待登录的秒数")
    login.add_argument("--browser-channel", help="Playwright 浏览器通道，如 chrome 或 msedge")

    status = commands.add_parser("status", help="检查已保存的浏览器登录状态，不输出会话内容")
    status.add_argument("--browser-channel", help="Playwright 浏览器通道，如 chrome 或 msedge")

    logout = commands.add_parser("logout", help="清除本地保存的抖音浏览器会话")
    logout.add_argument("--browser-channel", help="Playwright 浏览器通道，如 chrome 或 msedge")

    commands.add_parser("check-config", help="检查配置并显示已启用模式，不输出敏感信息")

    scan = commands.add_parser("scan", help="生成待审核清单，不修改知识库")
    source = scan.add_mutually_exclusive_group()
    source.add_argument("--input", type=Path, help="包含收藏条目的 JSON 列表或对象")
    source.add_argument("--collector", help="module:function 格式的 collector adapter")
    source.add_argument("--browser", action="store_true", help="使用内置授权浏览器 collector")
    scan.add_argument("--enricher", help="可选的单条内容增强 adapter，格式为 module:function")
    scan.add_argument("--source-label", help="写入审核清单的非敏感来源标签")
    scan.add_argument("--review", type=Path, required=True, help="待审核清单输出路径")
    scan.add_argument("--max-items", type=int, default=200, help="浏览器单次最多采集条数")
    scan.add_argument("--headed", action="store_true", help="采集时保持浏览器可见")
    scan.add_argument("--no-login-prompt", action="store_true", help="登录失效时直接失败，不打开登录页")
    scan.add_argument("--browser-channel", help="Playwright 浏览器通道，如 chrome 或 msedge")
    scan.add_argument("--dry-run", action="store_true", help="只校验和汇总，不写入文件")

    review = commands.add_parser("review", help="校验待审核清单，并按明确选择生成批准文件")
    review.add_argument("--review", type=Path, required=True)
    review.add_argument("--approval", type=Path)
    selection = review.add_mutually_exclusive_group()
    selection.add_argument("--approve-all", action="store_true")
    selection.add_argument("--approve", action="append", default=[], metavar="AWEME_ID")
    review.add_argument("--dry-run", action="store_true", help="只校验批准选择，不写入批准文件")

    promote_cmd = commands.add_parser("promote", help="原子写入已批准笔记和防重账本")
    promote_cmd.add_argument("--review", type=Path, required=True)
    promote_cmd.add_argument("--approval", type=Path, required=True)
    promote_cmd.add_argument("--notifier", help="提交后可选通知 adapter，格式为 module:function")
    promote_cmd.add_argument("--dry-run", action="store_true", help="只校验事务，不写入知识库")
    return root


def _print(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _config_summary(config: Config) -> dict:
    stages = {}
    for stage in (config.transcription, config.analysis, config.notification):
        status = {"enabled": stage.enabled, "provider": stage.provider}
        if stage.model:
            status["model"] = stage.model
        stages[stage.name] = status
    return {
        "status": "valid",
        "schema_version": config.raw["schema_version"],
        "mode": config.mode,
        "stages": stages,
    }


def _apply_enricher(raw_items: list[dict], spec: str, context: dict) -> list[dict]:
    enricher = load_adapter(spec)
    enriched = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            raise ValueError("each source item must be an object before enrichment")
        update = enricher(dict(raw), dict(context))
        if not isinstance(update, dict):
            raise ValueError("enricher must return an object")
        if "aweme_id" in update and str(update["aweme_id"]) != str(raw.get("aweme_id", "")):
            raise ValueError("enricher cannot change aweme_id")
        update.pop("source_url", None)
        enriched.append({**raw, **update})
    return enriched


def _apply_configured_stages(raw_items: list[dict], config: Config) -> list[dict]:
    for stage in config.enrichment_stages():
        raw_items = _apply_enricher(raw_items, stage.adapter, stage.context(config.mode))
    return raw_items


def _configured_notifier(config: Config) -> tuple[str, dict] | None:
    stage: StageConfig = config.notification
    if not stage.enabled:
        return None
    return stage.adapter, stage.context(config.mode)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "login":
            _print(login_browser(timeout_seconds=args.timeout, channel=args.browser_channel))
            return 0

        if args.command == "status":
            result = browser_status(channel=args.browser_channel)
            _print(result)
            return 0 if result["status"] == "authenticated" else 1

        if args.command == "logout":
            _print(logout_browser(channel=args.browser_channel))
            return 0

        if args.config is None:
            raise ValueError(f"--config is required for {args.command}")
        config = load_config(args.config)
        if args.command == "check-config":
            _print(_config_summary(config))
            return 0
        if args.command == "scan":
            if args.input:
                raw_items = read_input(args.input)
                default_source_label = "authorized_export"
            elif args.collector:
                collector = load_adapter(args.collector)
                raw_items = list(collector(dict(config.raw)))
                default_source_label = "external_adapter"
            else:
                raw_items = collect_browser_favorites(
                    max_items=args.max_items,
                    interactive_login=not args.no_login_prompt,
                    headed=args.headed,
                    channel=args.browser_channel,
                )
                default_source_label = "authorized_browser"
            raw_items = _apply_configured_stages(list(raw_items), config)
            if args.enricher:
                raw_items = _apply_enricher(raw_items, args.enricher, dict(config.raw))
            manifest = build_review(config, raw_items, args.source_label or default_source_label)
            result = {"status": "valid", **manifest["summary"], "review": str(args.review)}
            if not args.dry_run:
                atomic_write_json(args.review, manifest)
                result["status"] = "written"
            _print(result)
            return 0

        if args.command == "review":
            manifest = read_review(args.review)
            available = [item["aweme_id"] for item in manifest["items"]]
            selection = available if args.approve_all else args.approve
            if args.approval:
                if not args.approve_all and not args.approve:
                    raise ValueError("--approval requires --approve-all or at least one --approve")
                approval = build_approval(args.review, selection)
                result = {
                    "status": "valid" if args.dry_run else "approved",
                    "approved_count": len(approval["approved_ids"]),
                    "approval": str(args.approval),
                }
                if not args.dry_run:
                    atomic_write_json(args.approval, approval)
            else:
                if args.approve_all or args.approve:
                    raise ValueError("approval selection requires --approval")
                result = {"status": "valid", "candidate_count": len(available)}
            _print(result)
            return 0

        result = promote(config, args.review, args.approval, dry_run=args.dry_run)
        result["status"] = "valid" if args.dry_run else "committed"
        configured = _configured_notifier(config)
        notifier_spec = args.notifier or (configured[0] if configured else "")
        notifier_context = dict(config.raw) if args.notifier else (configured[1] if configured else {})
        if notifier_spec and not args.dry_run and result["promoted_count"]:
            notifier = load_adapter(notifier_spec)
            notifier(dict(result), notifier_context)
            result["notification"] = "sent"
        _print(result)
        return 0
    except Exception as exc:
        print(f"ERROR: {safe_error_message(exc)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
