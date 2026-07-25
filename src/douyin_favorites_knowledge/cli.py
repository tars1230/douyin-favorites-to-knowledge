from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from .adapters import load_adapter
from .browser_collector import browser_status, collect_browser_favorites, login_browser, logout_browser
from .config import load_config
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
    root = argparse.ArgumentParser(description="Promote reviewed Douyin favorites into local knowledge notes")
    root.add_argument("--config", type=Path, help="Path to schema_version=1 JSON config")
    commands = root.add_subparsers(dest="command", required=True)

    login = commands.add_parser("login", help="Open a local browser and save an authorized session")
    login.add_argument("--timeout", type=int, default=300, help="Seconds to wait for login")
    login.add_argument("--browser-channel", help="Playwright channel such as chrome or msedge")

    status = commands.add_parser("status", help="Check the saved browser session without exposing it")
    status.add_argument("--browser-channel", help="Playwright channel such as chrome or msedge")

    logout = commands.add_parser("logout", help="Clear the locally saved Douyin browser session")
    logout.add_argument("--browser-channel", help="Playwright channel such as chrome or msedge")

    scan = commands.add_parser("scan", help="Create a non-mutating review manifest")
    source = scan.add_mutually_exclusive_group()
    source.add_argument("--input", type=Path, help="JSON list or object containing items")
    source.add_argument("--collector", help="Collector adapter in module:function format")
    source.add_argument("--browser", action="store_true", help="Use the built-in authorized browser collector")
    scan.add_argument("--enricher", help="Optional per-item enricher adapter in module:function format")
    scan.add_argument("--source-label", help="Non-sensitive source label stored in the manifest")
    scan.add_argument("--review", type=Path, required=True, help="Review manifest output")
    scan.add_argument("--max-items", type=int, default=200, help="Maximum browser items to collect")
    scan.add_argument("--headed", action="store_true", help="Keep the collection browser visible")
    scan.add_argument("--no-login-prompt", action="store_true", help="Fail instead of opening login")
    scan.add_argument("--browser-channel", help="Playwright channel such as chrome or msedge")
    scan.add_argument("--dry-run", action="store_true", help="Validate and summarize without writing")

    review = commands.add_parser("review", help="Validate a review and optionally create explicit approval")
    review.add_argument("--review", type=Path, required=True)
    review.add_argument("--approval", type=Path)
    selection = review.add_mutually_exclusive_group()
    selection.add_argument("--approve-all", action="store_true")
    selection.add_argument("--approve", action="append", default=[], metavar="AWEME_ID")
    review.add_argument("--dry-run", action="store_true", help="Validate selection without writing approval")

    promote_cmd = commands.add_parser("promote", help="Atomically write approved notes and ledger entries")
    promote_cmd.add_argument("--review", type=Path, required=True)
    promote_cmd.add_argument("--approval", type=Path, required=True)
    promote_cmd.add_argument("--notifier", help="Optional post-commit notifier in module:function format")
    promote_cmd.add_argument("--dry-run", action="store_true", help="Validate transaction without writing")
    return root


def _print(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


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
            if args.enricher:
                enricher = load_adapter(args.enricher)
                enriched = []
                for raw in raw_items:
                    update = enricher(dict(raw), dict(config.raw))
                    if not isinstance(update, dict):
                        raise ValueError("enricher must return an object")
                    enriched.append({**raw, **update})
                raw_items = enriched
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
        if args.notifier and not args.dry_run and result["promoted_count"]:
            notifier = load_adapter(args.notifier)
            notifier(dict(result), dict(config.raw))
            result["notification"] = "sent"
        _print(result)
        return 0
    except (ImportError, AttributeError, OSError, ValueError, sqlite3.Error) as exc:
        print(f"ERROR: {safe_error_message(exc)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
