from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import date
from pathlib import Path

from .adapters import load_adapter
from .bailian import check_environment as check_bailian_environment
from .bailian import transcribe as transcribe_with_bailian
from .browser_collector import browser_status, collect_browser_favorites, login_browser, logout_browser
from .config import Config, StageConfig, default_config_path, load_config
from .local_whisper import check_environment as check_local_whisper_environment
from .knowledge_setup import initialize_obsidian, write_feishu_fields_template
from .local_whisper import transcribe as transcribe_with_local_whisper
from .provider_discovery import discover as discover_providers
from .siliconflow import check_environment as check_siliconflow_environment
from .siliconflow import transcribe as transcribe_with_siliconflow
from .security import safe_error_message
from .workflow import (
    atomic_write_json,
    atomic_write_text,
    build_approval,
    build_review,
    promote,
    read_input,
    read_review,
)

DEFAULT_MAX_DAILY_AUDIO_SECONDS = 3600
DEFAULT_MAX_DAILY_ITEMS = 100


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="将已授权的抖音收藏静默同步到本地知识库")
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
        "--transcription",
        choices=("siliconflow", "cloud", "bailian", "local", "none"),
        help=(
            "非交互时明确选择：siliconflow（推荐，抖音 CDN 主路径）、"
            "bailian（URL-ASR，对 douyinvod 常失败）、local（本地 Whisper）或 none；"
            "cloud 现为 siliconflow 别名（旧文档里 cloud=百炼已废弃）"
        ),
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

    obsidian = commands.add_parser("configure-obsidian", help="初始化 Obsidian 默认模板并切换知识库目录")
    obsidian.add_argument("--vault", type=Path, required=True, help="用户选择的 Obsidian Vault 目录")
    obsidian.add_argument("--subdir", default="抖音知识库", help="Vault 内知识库子目录")

    feishu = commands.add_parser("configure-feishu", help="配置可选飞书通知或生成多维表字段模板")
    feishu.add_argument("--mode", choices=("webhook", "bitable-existing", "bitable-new"), required=True)

    sync = commands.add_parser("sync", help="扫描新增收藏并静默写入知识库")
    _add_sync_arguments(sync)
    sync.add_argument("--yes", action="store_true", help="兼容旧版本；同步默认已静默写入")

    daily = commands.add_parser("daily", help="同步并生成当天 Markdown 日报")
    _add_sync_arguments(daily)
    daily.add_argument("--date", type=date.fromisoformat, help="日报日期（YYYY-MM-DD，默认今天）")

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


def _add_sync_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("--max-items", type=int, default=200, help="浏览器单次最多采集条数")
    command.add_argument("--headed", action="store_true", help="采集时保持浏览器可见")
    command.add_argument("--no-login-prompt", action="store_true", help="登录失效时直接失败，不打开登录页")
    command.add_argument("--browser-channel", help="Playwright 浏览器通道，如 chrome 或 msedge")
    command.add_argument("--dry-run", action="store_true", help="只显示新增候选，不写入知识库")
    command.add_argument("--source", choices=("collection", "like"), default="collection", help="默认收藏；喜欢需明确选择")


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
    if config.transcription.enabled and config.transcription.provider == "siliconflow":
        readiness = check_siliconflow_environment()
        pricing = {
            "currency": "CNY",
            "model": "FunAudioLLM/SenseVoiceSmall",
            "provider": "siliconflow",
            "list_price_label": "免费",
            "list_price_as_of": "2026-08-05",
            "official_pricing": "https://siliconflow.cn/pricing",
            "official_console": "https://cloud.siliconflow.cn/account/ak",
            "referral_signup": "https://cloud.siliconflow.cn/i/1srulim9",
            "note": (
                "抖音 CDN 推荐主路径：本机带 Referer 下载后上传。"
                "截至 2026-08-05 官方价格页标注 SenseVoiceSmall 为免费；价格会变，"
                "以 https://siliconflow.cn/pricing 与控制台账单为准，不承诺永久免费。注册推荐链接：https://cloud.siliconflow.cn/i/1srulim9。"
            ),
        }
    if config.transcription.enabled and config.transcription.provider == "bailian":
        readiness = check_bailian_environment()
        pricing = {
            "currency": "CNY",
            "model": "qwen3-asr-flash",
            "unit_rmb_per_second": 0.00022,
            "estimated_rmb_per_minute": 0.0132,
            "estimated_audio_minutes_per_10_rmb": 757.6,
            "estimated_audio_hours_per_10_rmb": 12.63,
            "north_china_2_free_seconds": 36000,
            "official_pricing": "https://help.aliyun.com/zh/model-studio/model-pricing",
            "note": "URL-ASR；抖音 douyinvod CDN 服务端常拉不到。价格页以控制台账单为准。",
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
    if transcription == "siliconflow":
        readiness = check_siliconflow_environment()
        if not readiness["ready"]:
            return "SiliconFlow 转录尚未就绪：设置 SILICONFLOW_API_KEY（https://cloud.siliconflow.cn/account/ak），然后执行 check-config。"
    if transcription == "bailian":
        readiness = check_bailian_environment()
        if not readiness["ready"]:
            return "百炼转录尚未就绪：设置 DASHSCOPE_API_KEY，并运行 python -m pip install '.[bailian-asr]'，然后执行 check-config。注意：抖音 CDN 上百炼 URL-ASR 常失败，优先 SiliconFlow。"
    if transcription == "local":
        readiness = check_local_whisper_environment()
        if not readiness["ready"]:
            return "本地转录尚未就绪：安装 ffmpeg 与 python -m pip install '.[local-asr]'；首次同步会下载模型。"
    return None


def _config_payload(config_path: Path, knowledge_dir: Path, transcription: str) -> dict:
    # cloud 历史别名曾指向 bailian；2.2+ 改为 siliconflow（抖音真实可用主路径）
    transcription = "siliconflow" if transcription == "cloud" else transcription
    provider = {
        "siliconflow": "siliconflow",
        "bailian": "bailian",
        "local": "local_whisper",
        "none": "none",
    }[transcription]
    model = {
        "siliconflow": "FunAudioLLM/SenseVoiceSmall",
        "bailian": "qwen3-asr-flash",
        "local": "small",
        "none": "",
    }[transcription]
    if provider == "bailian":
        options = {
            "max_daily_audio_seconds": DEFAULT_MAX_DAILY_AUDIO_SECONDS,
            "max_daily_items": DEFAULT_MAX_DAILY_ITEMS,
        }
    elif provider in {"siliconflow", "local_whisper"}:
        options = {"max_media_bytes": 512 * 1024 * 1024}
    else:
        options = {}
    return {
        "schema_version": 2,
        "mode": "full" if transcription != "none" else "light",
        "knowledge_dir": str(knowledge_dir.expanduser().resolve()),
        "ledger_path": str((config_path.parent / "state" / "ledger.sqlite3").resolve()),
        "transcription": (
            {
                "enabled": True,
                "provider": provider,
                "model": model,
                "options": options,
            }
            if transcription != "none"
            else {"enabled": False, "provider": "none"}
        ),
        "analysis": {"enabled": False, "provider": "none"},
        "notification": {"enabled": False, "provider": "none"},
    }


def _choose_transcription(args: argparse.Namespace) -> str:
    if args.transcription:
        return "siliconflow" if args.transcription == "cloud" else args.transcription
    discovery = discover_providers()
    label = {
        "siliconflow": "SiliconFlow（抖音 CDN 推荐）",
        "bailian": "百炼 URL-ASR（抖音 CDN 常失败）",
        "local": "本地 Whisper",
    }.get(discovery["recommended"], "SiliconFlow（抖音 CDN 推荐）")
    prompt = (
        f"本机检测（不会读取密钥、下载模型或产生费用）：推荐 {label}。\n"
        "选择转录方案：\n"
        "  1. SiliconFlow 云端（推荐，需 SILICONFLOW_API_KEY；本机 Referer 下载后上传 SenseVoice）\n"
        "  2. 百炼 URL-ASR（可选，需 DASHSCOPE_API_KEY；抖音 douyinvod 服务端常拉不到）\n"
        "  3. 本地 Whisper（无 API 费用；首次约下载 500 MB 模型，需要 ffmpeg）\n"
        "  4. 暂不转录（只保存标题、描述与链接）\n"
        "选择 [1/2/3/4，默认 1]: "
    )
    try:
        answer = input(prompt).strip().lower()
    except EOFError as exc:
        raise ValueError(
            "非交互安装请明确使用 setup --transcription siliconflow|bailian|local|none"
        ) from exc
    choices = {
        "": "siliconflow",
        "1": "siliconflow",
        "siliconflow": "siliconflow",
        "cloud": "siliconflow",
        "2": "bailian",
        "bailian": "bailian",
        "3": "local",
        "local": "local",
        "4": "none",
        "none": "none",
    }
    if answer not in choices:
        raise ValueError("转录方案只能选择 1/2/3/4 或 siliconflow|bailian|local|none")
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


def _save_config(path: Path, raw: dict) -> Config:
    atomic_write_json(path, raw)
    return load_config(path)


def _configure_obsidian(args: argparse.Namespace) -> int:
    config_path = (args.config or default_config_path()).expanduser().resolve()
    config = load_config(config_path)
    knowledge_dir = initialize_obsidian(args.vault, args.subdir)
    raw = dict(config.raw)
    raw["knowledge_dir"] = str(knowledge_dir)
    _save_config(config_path, raw)
    _print({"status": "ready", "output": "obsidian", "templates": "created", "write_check": "passed"})
    return 0


def _configure_feishu(args: argparse.Namespace) -> int:
    config_path = (args.config or default_config_path()).expanduser().resolve()
    config = load_config(config_path)
    if args.mode != "webhook":
        write_feishu_fields_template(config.knowledge_dir)
        _print({"status": "needs_authorization", "output": "feishu_bitable", "fields_template": "created"})
        return 0
    raw = dict(config.raw)
    if raw["schema_version"] == 1:
        raw.update(
            {
                "schema_version": 2,
                "transcription": {"enabled": False, "provider": "none"},
                "analysis": {"enabled": False, "provider": "none"},
            }
        )
    raw["mode"] = "full"
    raw["notification"] = {
        "enabled": True,
        "provider": "feishu",
        "adapter": "douyin_favorites_knowledge.feishu:notify_webhook",
    }
    _save_config(config_path, raw)
    _print({"status": "ready", "output": "feishu_webhook", "credential_source": "FEISHU_WEBHOOK_URL"})
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


def _reserve_bailian_budget(config: Config, item: dict, duration: float) -> int | None:
    """Atomically reserve today's configured ASR allowance before an API call."""
    options = config.transcription.options
    max_seconds = options.get("max_daily_audio_seconds", DEFAULT_MAX_DAILY_AUDIO_SECONDS)
    max_items = options.get("max_daily_items", DEFAULT_MAX_DAILY_ITEMS)
    config.ledger_path.parent.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    with sqlite3.connect(config.ledger_path, timeout=30) as connection:
        connection.execute("pragma busy_timeout=30000")
        connection.execute(
            "create table if not exists transcription_usage (id integer primary key, usage_date text not null, duration_seconds real not null, status text not null, reserved_at integer not null)"
        )
        connection.execute("begin immediate")
        connection.execute(
            "delete from transcription_usage where status = 'reserved' and reserved_at < ?",
            (int(time.time()) - 15 * 60,),
        )
        used_seconds, used_items = connection.execute(
            "select coalesce(sum(duration_seconds), 0), count(*) from transcription_usage where usage_date = ? and status in ('reserved', 'success')",
            (today,),
        ).fetchone()
        if (max_seconds is not None and used_seconds + duration > float(max_seconds)) or (
            max_items is not None and used_items >= int(max_items)
        ):
            connection.commit()
            return None
        cursor = connection.execute(
            "insert into transcription_usage (usage_date, duration_seconds, status, reserved_at) values (?, ?, 'reserved', ?)",
            (today, duration, int(time.time())),
        )
        connection.commit()
        return int(cursor.lastrowid)


def _finish_bailian_budget(config: Config, reservation_id: int, success: bool) -> None:
    if not reservation_id:
        return
    with sqlite3.connect(config.ledger_path, timeout=30) as connection:
        if success:
            connection.execute("update transcription_usage set status = 'success' where id = ?", (reservation_id,))
        else:
            connection.execute("delete from transcription_usage where id = ?", (reservation_id,))
        connection.commit()


def _apply_configured_stages(raw_items: list[dict], config: Config) -> list[dict]:
    for stage in config.enrichment_stages():
        if stage.name == "transcription" and stage.provider == "siliconflow":
            readiness = check_siliconflow_environment()
            if not readiness["ready"]:
                raise ValueError(
                    f"SiliconFlow transcription is not ready: {', '.join(readiness['missing'])}"
                )
            raw_items = _apply_enricher(
                raw_items, "", stage.context(config.mode), transcribe_with_siliconflow
            )
        elif stage.name == "transcription" and stage.provider == "bailian":
            readiness = check_bailian_environment()
            if not readiness["ready"]:
                raise ValueError(f"Bailian transcription is not ready: {', '.join(readiness['missing'])}")
            enriched = []
            for raw in raw_items:
                duration = raw.get("duration_seconds", 0)
                try:
                    duration = max(0.0, float(duration or 0))
                except (TypeError, ValueError):
                    duration = 0.0
                reservation_id = _reserve_bailian_budget(config, raw, duration)
                if reservation_id is None:
                    enriched.append({
                        **raw,
                        "transcript": "",
                        "transcript_source": "bailian_qwen3_asr_flash",
                        "transcript_status": "budget_exceeded",
                    })
                    continue
                try:
                    item = _apply_enricher([raw], "", stage.context(config.mode), transcribe_with_bailian)[0]
                except Exception:
                    _finish_bailian_budget(config, reservation_id, False)
                    raise
                enriched.append(item)
                _finish_bailian_budget(config, reservation_id, item.get("transcript_status") == "success")
            raw_items = enriched
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
    try:
        notifier(dict(result), configured[1])
    except Exception:
        result["notification"] = "not_sent"
        return
    result["notification"] = "sent"


def _write_daily_report(config: Config, source: str, report_date: date, items: list[dict]) -> None:
    source_name = "收藏" if source == "collection" else "喜欢"
    lines = [
        "---",
        f"date: {json.dumps(report_date.isoformat())}",
        f"source: {json.dumps(source)}",
        f"new_count: {len(items)}",
        "---",
        "",
        f"# {report_date.isoformat()} 抖音{source_name}日报",
        "",
        f"今日新增 {len(items)} 条。",
        "",
    ]
    if items:
        lines.extend(["## 新增笔记", ""])
        for item in items:
            note_name = f"{item['source']}-{item['aweme_id']}"
            author = f" - {item['author']}" if item["author"] else ""
            lines.append(f"- [[{note_name}|{item['title']}]]{author} ([原链接]({item['source_url']}))")
    else:
        lines.append("今日没有新增条目。")
    lines.append("")
    suffix = "收藏" if source == "collection" else "喜欢"
    atomic_write_text(config.knowledge_dir / "日报" / f"{report_date.isoformat()}-{suffix}日报.md", "\n".join(lines))


def _sync(args: argparse.Namespace, config: Config, report_date: date | None = None) -> int:
    raw_items = collect_browser_favorites(
        max_items=args.max_items,
        interactive_login=not args.no_login_prompt,
        headed=args.headed,
        channel=args.browser_channel,
        source=args.source,
    )
    mismatched = [item for item in raw_items if item.get("source") and item["source"] != args.source]
    if mismatched:
        raise ValueError(f"collector returned items outside requested source: {args.source}")
    raw_items = _apply_configured_stages(list(raw_items), config)
    retryable_statuses = {"failed", "unavailable", "too_large", "budget_exceeded"}
    retryable_count = sum(item.get("transcript_status") in retryable_statuses for item in raw_items)
    if config.transcription.enabled:
        raw_items = [item for item in raw_items if item.get("transcript_status") not in retryable_statuses]
    manifest = build_review(config, raw_items, f"authorized_browser:{args.source}")
    candidates = manifest["items"]
    if not candidates:
        summary = {"status": "no_changes", **({"retryable_count": retryable_count} if retryable_count else {})}
        if report_date:
            _write_daily_report(config, args.source, report_date, [])
            summary["daily_report"] = "written"
        _print(summary)
        return 0

    if args.dry_run:
        preview = [
            {"aweme_id": item["aweme_id"], "title": item["title"][:120]}
            for item in candidates[:20]
        ]
        _print({"status": "dry_run", **manifest["summary"], "preview": preview})
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
    if retryable_count:
        summary["retryable_count"] = retryable_count
    if "notification" in result:
        summary["notification"] = result["notification"]
    if report_date:
        promoted_ids = set(result["ids"])
        _write_daily_report(
            config,
            args.source,
            report_date,
            [item for item in candidates if item["aweme_id"] in promoted_ids],
        )
        summary["daily_report"] = "written"
    _print(summary)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "setup":
            return _setup(args)

        if args.command == "configure-obsidian":
            return _configure_obsidian(args)

        if args.command == "configure-feishu":
            return _configure_feishu(args)

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
        if args.command == "daily":
            return _sync(args, config, args.date or date.today())
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
