from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .adapters import load_adapter
from .bailian import check_environment as check_bailian_environment
from .bailian import transcribe as transcribe_with_bailian
from .browser_collector import browser_status, collect_browser_favorites, login_browser, logout_browser
from .config import Config, StageConfig, default_config_path, load_config
from .douyin_mcp import check_environment as check_douyin_mcp_environment
from .douyin_mcp import transcribe as transcribe_with_douyin_mcp
from .local_whisper import check_environment as check_local_whisper_environment
from .local_whisper import transcribe as transcribe_with_local_whisper
from .provider_discovery import discover as discover_providers
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
    root.add_argument("--config", type=Path, help="可选配置路径；setup 后通常不需要填写")
    commands = root.add_subparsers(dest="command", required=True)

    setup = commands.add_parser("setup", help="完成首次配置并登录抖音")
    setup.add_argument("--knowledge-dir", type=Path, help="Markdown 或 Obsidian 知识库目录")
    setup.add_argument("--skip-login", action="store_true", help="只创建配置，暂不打开登录页")
    setup.add_argument("--force", action="store_true", help="覆盖已有配置并重新选择知识库")
    setup.add_argument("--timeout", type=int, default=300, help="等待登录的秒数")
    setup.add_argument("--browser-channel", help="Playwright 浏览器通道，如 chrome 或 msedge")
    transcription = setup.add_mutually_exclusive_group()
    transcription.add_argument(
        "--transcription", choices=("bailian", "cloud", "local", "none"),
        help="非交互时明确选择：bailian（推荐百炼）、local（本地 Whisper）或 none；cloud 是 bailian 的兼容别名",
    )
    transcription.add_argument(
        "--enable-douyin-mcp-transcription", action="store_true",
        help="兼容旧命令，等同于 --transcription bailian",
    )

    login = commands.add_parser("login", help="打开本地浏览器并保存授权登录状态")
    login.add_argument("--timeout", type=int, default=300, help="等待登录的秒数")
    login.add_argument("--browser-channel", help="Playwright 浏览器通道，如 chrome 或 msedge")
    login.add_argument("--source", choices=("collection", "like"), default="collection")

    status = commands.add_parser("status", help="检查已保存的浏览器登录状态，不输出会话内容")
    status.add_argument("--browser-channel", help="Playwright 浏览器通道，如 chrome 或 msedge")

    logout = commands.add_parser("logout", help="清除本地保存的抖音浏览器会话")
    logout.add_argument("--browser-channel", help="Playwright 浏览器通道，如 chrome 或 msedge")

    commands.add_parser("check-config", help="检查配置并显示已启用模式，不输出敏感信息")

    sync = commands.add_parser("sync", help="扫描新增收藏，确认后写入知识库")
    sync.add_argument("--yes", action="store_true", help="明确批准本次全部新增，适合自动任务")
    sync.add_argument("--max-items", type=int, default=200, help="浏览器单次最多采集条数")
    sync.add_argument("--headed", action="store_true", help="采集时保持浏览器可见")
    sync.add_argument("--no-login-prompt", action="store_true", help="登录失效时直接失败，不打开登录页")
    sync.add_argument("--browser-channel", help="Playwright 浏览器通道，如 chrome 或 msedge")
    sync.add_argument("--dry-run", action="store_true", help="只显示新增候选，不写入知识库")
    sync.add_argument("--source", choices=("collection", "like"), default="collection", help="默认收藏；喜欢需明确选择")

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
    scan.add_argument("--source", choices=("collection", "like"), default="collection", help="内置浏览器采集的来源")

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
    readiness = None
    pricing = None
    if config.transcription.enabled and config.transcription.provider == "bailian":
        readiness = check_bailian_environment()
        pricing = {
            "currency": "CNY",
            "model": "qwen3-asr-flash",
            "unit_rmb_per_second": 0.00022,
            "estimated_rmb_per_minute": 0.0132,
            "north_china_2_free_seconds": 36000,
            "official_pricing": "https://help.aliyun.com/zh/model-studio/model-pricing",
            "note": "官方价格页于 2026-07-30 核验；地域、额度和价格会变化，以控制台账单为准。",
        }
    elif config.transcription.enabled and config.transcription.provider == "douyin_mcp":
        readiness = check_douyin_mcp_environment()
        pricing = {
            "currency": "CNY",
            "model": "qwen3-asr-flash",
            "unit_rmb_per_second": 0.00022,
            "estimated_rmb_per_minute": 0.0132,
            "north_china_2_free_seconds": 36000,
            "official_pricing": "https://help.aliyun.com/zh/model-studio/model-pricing",
            "note": "官方价格页于 2026-07-30 核验；地域、额度和价格会变化，以控制台账单为准。",
        }
    if config.transcription.enabled and config.transcription.provider == "local_whisper":
        readiness = check_local_whisper_environment()
    return {
        "status": "valid" if readiness is None else ("ready" if readiness["ready"] else "action_required"),
        "schema_version": config.raw["schema_version"],
        "mode": config.mode,
        "stages": stages,
        **({"transcription_readiness": readiness} if readiness is not None else {}),
        **({"cloud_transcription_pricing": pricing} if pricing is not None else {}),
        "provider_discovery": discover_providers(),
    }


def _transcription_next_step(transcription: str) -> str | None:
    if transcription == "bailian":
        readiness = check_bailian_environment()
        if not readiness["ready"]:
            return "百炼转录尚未就绪：设置 DASHSCOPE_API_KEY，并运行 python -m pip install '.[bailian-asr]'，然后执行 check-config。"
    if transcription == "local":
        readiness = check_local_whisper_environment()
        if not readiness["ready"]:
            return "本地转录尚未就绪：安装 ffmpeg 与 python -m pip install '.[local-asr]'；首次同步会下载模型。"
    return None


def _config_payload(config_path: Path, knowledge_dir: Path, transcription: str) -> dict:
    transcription = "bailian" if transcription == "cloud" else transcription
    provider = {"bailian": "bailian", "local": "local_whisper", "none": "none"}[transcription]
    model = {"bailian": "qwen3-asr-flash", "local": "small", "none": ""}[transcription]
    return {
        "schema_version": 2,
        "mode": "full" if transcription != "none" else "light",
        "knowledge_dir": str(knowledge_dir.expanduser().resolve()),
        "ledger_path": str((config_path.parent / "state" / "ledger.sqlite3").resolve()),
        "transcription": (
            {"enabled": True, "provider": provider, "model": model}
            if transcription != "none"
            else {"enabled": False, "provider": "none"}
        ),
        "analysis": {"enabled": False, "provider": "none"},
        "notification": {"enabled": False, "provider": "none"},
    }


def _choose_transcription(args: argparse.Namespace) -> str:
    if args.enable_douyin_mcp_transcription:
        return "bailian"
    if args.transcription:
        return "bailian" if args.transcription == "cloud" else args.transcription
    discovery = discover_providers()
    recommendation = "百炼云端" if discovery["recommended"] == "bailian" else "本地 Whisper"
    prompt = (
        f"本机检测（不会读取密钥、下载模型或产生费用）：推荐 {recommendation}。\n"
        "选择转录方案：\n"
        "  1. 百炼云端（推荐，需 DASHSCOPE_API_KEY 和 .[bailian-asr]；按音频时长计费）\n"
        "  2. 本地 Whisper（无 API 费用；首次约下载 500 MB 模型，需要 ffmpeg、CPU 和临时磁盘）\n"
        "  3. 暂不转录（只保存标题、描述与链接）\n"
        "选择 [1/2/3，默认 1]: "
    )
    try:
        answer = input(prompt).strip().lower()
    except EOFError as exc:
        raise ValueError("非交互安装请明确使用 setup --transcription bailian|local|none") from exc
    choices = {"": "bailian", "1": "bailian", "bailian": "bailian", "cloud": "bailian", "2": "local", "local": "local", "3": "none", "none": "none"}
    if answer not in choices:
        raise ValueError("转录方案只能选择 1、2、3、bailian、local 或 none")
    return choices[answer]


def _setup(args: argparse.Namespace) -> int:
    config_path = (args.config or default_config_path()).expanduser().resolve()
    if config_path.exists() and not args.force:
        if args.knowledge_dir is not None:
            raise ValueError("配置已存在；更换知识库目录请使用 setup --force")
        config = load_config(config_path)
    else:
        default_knowledge = Path.home() / "Douyin Knowledge"
        knowledge_dir = args.knowledge_dir
        if knowledge_dir is None:
            try:
                answer = input(f"知识库目录 [{default_knowledge}]: ").strip()
            except EOFError as exc:
                raise ValueError("非交互安装请使用 setup --knowledge-dir 指定知识库目录") from exc
            knowledge_dir = Path(answer).expanduser() if answer else default_knowledge
        transcription = _choose_transcription(args)
        atomic_write_json(config_path, _config_payload(config_path, knowledge_dir, transcription))
        config = load_config(config_path)

    transcription = {
        "bailian": "bailian",
        "local_whisper": "local",
        "none": "none",
    }.get(config.transcription.provider, config.transcription.provider)

    login_status = "skipped"
    if not args.skip_login:
        login_status = login_browser(
            timeout_seconds=args.timeout,
            channel=args.browser_channel,
        )["status"]
    next_step = _transcription_next_step(transcription)
    _print({
        "status": "ready",
        "login": login_status,
        "transcription": transcription,
        "provider_discovery": discover_providers(),
        **({"next_step": next_step} if next_step else {}),
    })
    return 0


def _apply_enricher(raw_items: list[dict], spec: str, context: dict, built_in=None) -> list[dict]:
    enricher = built_in or load_adapter(spec)
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
        if stage.name == "transcription" and stage.provider == "bailian":
            readiness = check_bailian_environment()
            if not readiness["ready"]:
                raise ValueError(f"Bailian transcription is not ready: {', '.join(readiness['missing'])}")
            raw_items = _apply_enricher(raw_items, "", stage.context(config.mode), transcribe_with_bailian)
        elif stage.name == "transcription" and stage.provider == "douyin_mcp":
            readiness = check_douyin_mcp_environment()
            if not readiness["ready"]:
                raise ValueError(f"douyin-mcp transcription is not ready: {', '.join(readiness['missing'])}")
            raw_items = _apply_enricher(raw_items, "", stage.context(config.mode), transcribe_with_douyin_mcp)
        elif stage.name == "transcription" and stage.provider == "local_whisper":
            readiness = check_local_whisper_environment()
            if not readiness["ready"]:
                raise ValueError(f"local Whisper transcription is not ready: {', '.join(readiness['missing'])}")
            raw_items = _apply_enricher(raw_items, "", stage.context(config.mode), transcribe_with_local_whisper)
        else:
            raw_items = _apply_enricher(raw_items, stage.adapter, stage.context(config.mode))
    return raw_items


def _configured_notifier(config: Config) -> tuple[str, dict] | None:
    stage: StageConfig = config.notification
    if not stage.enabled:
        return None
    return stage.adapter, stage.context(config.mode)


def _notify_if_configured(config: Config, result: dict) -> None:
    configured = _configured_notifier(config)
    if not configured or not result["promoted_count"]:
        return
    notifier = load_adapter(configured[0])
    notifier(dict(result), configured[1])
    result["notification"] = "sent"


def _sync(args: argparse.Namespace, config: Config) -> int:
    raw_items = collect_browser_favorites(
        max_items=args.max_items,
        interactive_login=not args.no_login_prompt,
        headed=args.headed,
        channel=args.browser_channel,
        source=args.source,
    )
    raw_items = _apply_configured_stages(list(raw_items), config)
    manifest = build_review(config, raw_items, f"authorized_browser:{args.source}")
    candidates = manifest["items"]
    if not candidates:
        _print({"status": "no_changes"})
        return 0

    preview = [
        {"aweme_id": item["aweme_id"], "title": item["title"][:120]}
        for item in candidates[:20]
    ]
    if args.dry_run:
        _print({"status": "review_required", **manifest["summary"], "preview": preview})
        return 0

    if not args.yes:
        print(f"发现 {len(candidates)} 条新增{'收藏' if args.source == 'collection' else '喜欢'}：")
        for item in preview:
            print(f"- {item['aweme_id']}  {item['title']}")
        if len(candidates) > len(preview):
            print(f"- 以及另外 {len(candidates) - len(preview)} 条")
        try:
            answer = input("确认写入知识库？[y/N]: ").strip().lower()
        except EOFError as exc:
            raise ValueError("非交互同步请明确使用 sync --yes 或 sync --dry-run") from exc
        if answer not in {"y", "yes"}:
            _print({"status": "cancelled", "candidate_count": len(candidates)})
            return 0

    runtime_dir = config.ledger_path.parent / "sync"
    review_path = runtime_dir / "review.json"
    approval_path = runtime_dir / "approval.json"
    atomic_write_json(review_path, manifest)
    approval = build_approval(review_path, [item["aweme_id"] for item in candidates])
    atomic_write_json(approval_path, approval)
    result = promote(config, review_path, approval_path)
    result["status"] = "committed"
    _notify_if_configured(config, result)
    summary = {
        "status": result["status"],
        "promoted_count": result["promoted_count"],
        "skipped_count": result["skipped_count"],
    }
    if "notification" in result:
        summary["notification"] = result["notification"]
    _print(summary)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "setup":
            return _setup(args)

        if args.command == "login":
            _print(login_browser(timeout_seconds=args.timeout, channel=args.browser_channel, source=args.source))
            return 0

        if args.command == "status":
            result = browser_status(channel=args.browser_channel)
            _print(result)
            return 0 if result["status"] == "authenticated" else 1

        if args.command == "logout":
            _print(logout_browser(channel=args.browser_channel))
            return 0

        config_path = (args.config or default_config_path()).expanduser().resolve()
        if not config_path.exists():
            raise ValueError("尚未完成配置，请先运行 douyin-favorites-knowledge setup")
        config = load_config(config_path)
        if args.command == "check-config":
            summary = _config_summary(config)
            _print(summary)
            return 0 if summary["status"] in {"valid", "ready"} else 1
        if args.command == "sync":
            return _sync(args, config)
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
                    source=args.source,
                )
                default_source_label = f"authorized_browser:{args.source}"
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
