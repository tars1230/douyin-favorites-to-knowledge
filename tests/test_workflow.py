import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "favorites.json"
PYTHONPATH = str(ROOT / "src")
sys.path.insert(0, PYTHONPATH)

from douyin_favorites_knowledge.security import safe_error_message  # noqa: E402
from douyin_favorites_knowledge.cli import _apply_configured_stages, main  # noqa: E402
from douyin_favorites_knowledge.config import default_config_path, load_config  # noqa: E402
from douyin_favorites_knowledge.workflow import build_review  # noqa: E402


def cli(config: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = PYTHONPATH
    return subprocess.run(
        [sys.executable, "-m", "douyin_favorites_knowledge", "--config", str(config), *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = self.root / "config.json"
        self.knowledge = self.root / "knowledge"
        self.ledger = self.root / "state" / "ledger.sqlite3"
        self.review = self.root / "review.json"
        self.approval = self.root / "approval.json"
        self.config.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "knowledge_dir": "knowledge",
                    "ledger_path": "state/ledger.sqlite3",
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp.cleanup()

    def scan(self, input_path: Path = FIXTURE) -> subprocess.CompletedProcess[str]:
        return cli(
            self.config,
            "scan",
            "--input",
            str(input_path),
            "--source-label",
            "synthetic_fixture",
            "--review",
            str(self.review),
        )

    def approve(self) -> subprocess.CompletedProcess[str]:
        return cli(
            self.config,
            "review",
            "--review",
            str(self.review),
            "--approve-all",
            "--approval",
            str(self.approval),
        )

    def test_fixture_e2e_is_idempotent(self):
        scanned = self.scan()
        self.assertEqual(scanned.returncode, 0, scanned.stderr)
        review = json.loads(self.review.read_text(encoding="utf-8"))
        self.assertEqual(review["summary"]["candidate_count"], 2)
        self.assertEqual(
            review["items"][0]["source_url"],
            "https://www.douyin.com/video/7000000000000000001",
        )
        self.assertNotIn("example.invalid", self.review.read_text(encoding="utf-8"))

        approved = self.approve()
        self.assertEqual(approved.returncode, 0, approved.stderr)

        dry = cli(
            self.config,
            "promote",
            "--review",
            str(self.review),
            "--approval",
            str(self.approval),
            "--dry-run",
        )
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertFalse(self.knowledge.exists())
        self.assertFalse(self.ledger.exists())

        promoted = cli(
            self.config,
            "promote",
            "--review",
            str(self.review),
            "--approval",
            str(self.approval),
        )
        self.assertEqual(promoted.returncode, 0, promoted.stderr)
        self.assertEqual(len(list(self.knowledge.glob("*.md"))), 2)
        with sqlite3.connect(self.ledger) as connection:
            count = connection.execute("select count(*) from promotions").fetchone()[0]
        self.assertEqual(count, 2)

        repeated = cli(
            self.config,
            "promote",
            "--review",
            str(self.review),
            "--approval",
            str(self.approval),
        )
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        payload = json.loads(repeated.stdout)
        self.assertEqual(payload["promoted_count"], 0)
        self.assertEqual(payload["skipped_count"], 2)

    def test_reasoning_leak_is_blocked_before_review_write(self):
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        payload["items"][0]["transcript"] = "<think>private reasoning</think>"
        source = self.root / "leak.json"
        source.write_text(json.dumps(payload), encoding="utf-8")
        result = self.scan(source)
        self.assertEqual(result.returncode, 1)
        self.assertIn("reasoning tag blocked", result.stderr)
        self.assertFalse(self.review.exists())

    def test_review_tamper_after_approval_is_blocked(self):
        self.assertEqual(self.scan().returncode, 0)
        self.assertEqual(self.approve().returncode, 0)
        payload = json.loads(self.review.read_text(encoding="utf-8"))
        payload["source_label"] = "changed_after_approval"
        self.review.write_text(json.dumps(payload), encoding="utf-8")
        result = cli(
            self.config,
            "promote",
            "--review",
            str(self.review),
            "--approval",
            str(self.approval),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("review changed after approval", result.stderr)

    def test_changed_promoted_item_requires_manual_migration(self):
        self.assertEqual(self.scan().returncode, 0)
        self.assertEqual(self.approve().returncode, 0)
        promoted = cli(
            self.config,
            "promote",
            "--review",
            str(self.review),
            "--approval",
            str(self.approval),
        )
        self.assertEqual(promoted.returncode, 0, promoted.stderr)

        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        payload["items"][0]["transcript"] += " changed"
        changed = self.root / "changed.json"
        changed.write_text(json.dumps(payload), encoding="utf-8")
        next_review = self.root / "next-review.json"
        result = cli(
            self.config,
            "scan",
            "--input",
            str(changed),
            "--review",
            str(next_review),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("manual migration required", result.stderr)
        self.assertFalse(next_review.exists())

    def test_scan_dry_run_writes_nothing(self):
        result = cli(
            self.config,
            "scan",
            "--input",
            str(FIXTURE),
            "--review",
            str(self.review),
            "--dry-run",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.review.exists())
        self.assertFalse(self.ledger.exists())

    def test_scan_defaults_to_authorized_browser_collector(self):
        source_items = [{**item, "source": "collection"} for item in json.loads(FIXTURE.read_text(encoding="utf-8"))["items"]]
        output = StringIO()
        with patch(
            "douyin_favorites_knowledge.cli.collect_browser_favorites",
            return_value=source_items,
        ) as collect, redirect_stdout(output):
            returncode = main(
                [
                    "--config",
                    str(self.config),
                    "scan",
                    "--review",
                    str(self.review),
                    "--max-items",
                    "7",
                    "--no-login-prompt",
                ]
            )
        self.assertEqual(returncode, 0)
        collect.assert_called_once_with(
            max_items=7,
            interactive_login=False,
            headed=False,
            channel=None,
            source="collection",
        )
        review = json.loads(self.review.read_text(encoding="utf-8"))
        self.assertEqual(review["source_label"], "authorized_browser:collection")

    def test_login_does_not_require_config_or_expose_session_details(self):
        output = StringIO()
        with patch(
            "douyin_favorites_knowledge.cli.login_browser",
            return_value={"status": "authenticated"},
        ), redirect_stdout(output):
            returncode = main(["login", "--timeout", "30"])
        self.assertEqual(returncode, 0)
        self.assertEqual(json.loads(output.getvalue()), {"status": "authenticated"})

    def test_status_returns_nonzero_when_login_is_required(self):
        output = StringIO()
        with patch(
            "douyin_favorites_knowledge.cli.browser_status",
            return_value={"status": "login_required"},
        ), redirect_stdout(output):
            returncode = main(["status"])
        self.assertEqual(returncode, 1)
        self.assertEqual(json.loads(output.getvalue()), {"status": "login_required"})

    def test_logout_clears_session_without_requiring_config(self):
        output = StringIO()
        with patch(
            "douyin_favorites_knowledge.cli.logout_browser",
            return_value={"status": "logged_out"},
        ), redirect_stdout(output):
            returncode = main(["logout"])
        self.assertEqual(returncode, 0)
        self.assertEqual(json.loads(output.getvalue()), {"status": "logged_out"})

    def test_secret_like_config_key_is_rejected(self):
        payload = json.loads(self.config.read_text(encoding="utf-8"))
        payload["api_key"] = "placeholder"
        self.config.write_text(json.dumps(payload), encoding="utf-8")
        result = self.scan()
        self.assertEqual(result.returncode, 1)
        self.assertIn("secret-like key blocked", result.stderr)

    def test_schema_v1_config_remains_light_mode_compatible(self):
        config = load_config(self.config)
        self.assertEqual(config.mode, "light")
        self.assertEqual(config.enrichment_stages(), ())
        self.assertFalse(config.notification.enabled)

    def test_check_config_guides_setup_without_exposing_local_paths(self):
        result = cli(self.config, "check-config")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "valid")
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["mode"], "light")
        self.assertEqual(
            payload["stages"],
            {
                "analysis": {"enabled": False, "provider": "none"},
                "notification": {"enabled": False, "provider": "none"},
                "transcription": {"enabled": False, "provider": "none"},
            },
        )
        self.assertNotIn(str(self.root), result.stdout)
        self.assertNotIn("ledger.sqlite3", result.stdout)

    def test_default_config_path_honors_environment_override(self):
        custom = self.root / "app-config.json"
        with patch.dict(os.environ, {"DOUYIN_FAVORITES_CONFIG": str(custom)}):
            self.assertEqual(default_config_path(), custom.resolve())

    def test_setup_creates_safe_light_config_without_login(self):
        setup_config = self.root / "app" / "config.json"
        output = StringIO()
        with redirect_stdout(output):
            returncode = main(
                [
                    "--config",
                    str(setup_config),
                    "setup",
                    "--knowledge-dir",
                    str(self.knowledge),
                    "--transcription",
                    "none",
                    "--skip-login",
                ]
            )
        self.assertEqual(returncode, 0)
        payload = json.loads(setup_config.read_text(encoding="utf-8"))
        self.assertEqual(payload["mode"], "light")
        self.assertEqual(payload["knowledge_dir"], str(self.knowledge.resolve()))
        self.assertNotIn("cookie", setup_config.read_text(encoding="utf-8").lower())
        result = json.loads(output.getvalue())
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["login"], "skipped")
        self.assertNotIn(str(self.root), output.getvalue())

    def test_configure_obsidian_creates_templates_and_updates_knowledge_dir(self):
        vault = self.root / "vault"
        result = cli(self.config, "configure-obsidian", "--vault", str(vault), "--subdir", "抖音")
        self.assertEqual(result.returncode, 0, result.stderr)
        knowledge = vault / "抖音"
        self.assertTrue((knowledge / "模板" / "抖音收藏.md").exists())
        template = (knowledge / "模板" / "抖音收藏.md").read_text(encoding="utf-8")
        self.assertIn("## 原始材料", template)
        self.assertIn("### 原始描述", template)
        self.assertNotIn("## 研判", template)
        self.assertTrue((knowledge / "日报索引.md").exists())
        self.assertFalse((knowledge / "系统" / ".write-check.md").exists())
        self.assertEqual(load_config(self.config).knowledge_dir, knowledge.resolve())

    def test_configure_feishu_webhook_keeps_webhook_out_of_config(self):
        result = cli(self.config, "configure-feishu", "--mode", "webhook")
        self.assertEqual(result.returncode, 0, result.stderr)
        config_text = self.config.read_text(encoding="utf-8")
        self.assertNotIn("FEISHU_WEBHOOK_URL", config_text)
        config = load_config(self.config)
        self.assertTrue(config.notification.enabled)
        self.assertEqual(config.notification.provider, "feishu")

    def test_setup_opens_login_by_default(self):
        setup_config = self.root / "login-setup" / "config.json"
        output = StringIO()
        with patch(
            "douyin_favorites_knowledge.cli.login_browser",
            return_value={"status": "authenticated"},
        ) as login, redirect_stdout(output):
            returncode = main(
                [
                    "--config",
                    str(setup_config),
                    "setup",
                    "--knowledge-dir",
                    str(self.knowledge),
                    "--transcription",
                    "none",
                ]
            )
        self.assertEqual(returncode, 0)
        login.assert_called_once_with(timeout_seconds=300, channel=None)
        self.assertEqual(json.loads(output.getvalue())["login"], "authenticated")

    def test_setup_explicitly_selects_local_whisper(self):
        setup_config = self.root / "local-setup" / "config.json"
        with redirect_stdout(StringIO()):
            returncode = main(
                [
                    "--config", str(setup_config), "setup", "--knowledge-dir", str(self.knowledge),
                    "--transcription", "local", "--skip-login",
                ]
            )
        self.assertEqual(returncode, 0)
        payload = json.loads(setup_config.read_text(encoding="utf-8"))
        self.assertEqual(payload["transcription"], {
            "enabled": True, "provider": "local_whisper", "model": "small",
            "options": {"max_media_bytes": 512 * 1024 * 1024},
        })

    def test_setup_bailian_uses_direct_provider_and_reports_actionable_next_step(self):
        setup_config = self.root / "bailian-setup" / "config.json"
        output = StringIO()
        with patch("douyin_favorites_knowledge.cli.check_bailian_environment", return_value={"ready": False, "missing": ["DASHSCOPE_API_KEY"]}), patch(
            "douyin_favorites_knowledge.cli.discover_providers", return_value={"bailian": {"state": "action_required"}, "recommended": "bailian"}
        ), redirect_stdout(output):
            returncode = main([
                "--config", str(setup_config), "setup", "--knowledge-dir", str(self.knowledge),
                "--transcription", "bailian", "--skip-login",
            ])
        self.assertEqual(returncode, 0)
        payload = json.loads(setup_config.read_text(encoding="utf-8"))
        self.assertEqual(payload["transcription"]["provider"], "bailian")
        result = json.loads(output.getvalue())
        self.assertIn("DASHSCOPE_API_KEY", result["next_step"])

    def test_bailian_stage_uses_direct_provider(self):
        self.config.write_text(json.dumps({
            "schema_version": 2, "mode": "full", "knowledge_dir": "knowledge", "ledger_path": "state/ledger.sqlite3",
            "transcription": {"enabled": True, "provider": "bailian", "model": "qwen3-asr-flash"},
            "analysis": {"enabled": False, "provider": "none"},
            "notification": {"enabled": False, "provider": "none"},
        }), encoding="utf-8")
        item = json.loads(FIXTURE.read_text(encoding="utf-8"))["items"][0]
        with patch("douyin_favorites_knowledge.cli.check_bailian_environment", return_value={"ready": True}), patch(
            "douyin_favorites_knowledge.cli.transcribe_with_bailian", return_value={"transcript": "文本", "transcript_status": "success"}
        ) as bailian_transcribe:
            enriched = _apply_configured_stages([item], load_config(self.config))
        bailian_transcribe.assert_called_once()
        self.assertEqual(enriched[0]["transcript"], "文本")

    def test_bailian_daily_budget_marks_excess_items_retryable(self):
        self.config.write_text(json.dumps({
            "schema_version": 2, "mode": "full", "knowledge_dir": "knowledge", "ledger_path": "state/ledger.sqlite3",
            "transcription": {"enabled": True, "provider": "bailian", "model": "qwen3-asr-flash", "options": {"max_daily_audio_seconds": 30, "max_daily_items": 1}},
            "analysis": {"enabled": False, "provider": "none"}, "notification": {"enabled": False, "provider": "none"},
        }), encoding="utf-8")
        items = [{"aweme_id": "7000000000000000001", "description": "a", "play_url": "u", "duration_seconds": 20}, {"aweme_id": "7000000000000000002", "description": "b", "play_url": "u", "duration_seconds": 20}]
        with patch("douyin_favorites_knowledge.cli.check_bailian_environment", return_value={"ready": True}), patch(
            "douyin_favorites_knowledge.cli.transcribe_with_bailian", return_value={"transcript": "text", "transcript_status": "success"}
        ) as transcribe:
            enriched = _apply_configured_stages(items, load_config(self.config))
        self.assertEqual(transcribe.call_count, 1)
        self.assertEqual(enriched[1]["transcript_status"], "budget_exceeded")

    def test_cloud_check_config_shows_pricing_without_credentials(self):
        self.config.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "mode": "full",
                    "knowledge_dir": "knowledge",
                    "ledger_path": "state/ledger.sqlite3",
                    "transcription": {"enabled": True, "provider": "bailian", "model": "qwen3-asr-flash"},
                    "analysis": {"enabled": False, "provider": "none"},
                    "notification": {"enabled": False, "provider": "none"},
                }
            ),
            encoding="utf-8",
        )
        output = StringIO()
        with patch("douyin_favorites_knowledge.cli.check_bailian_environment", return_value={"ready": True}), redirect_stdout(output):
            returncode = main(["--config", str(self.config), "check-config"])
        self.assertEqual(returncode, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["cloud_transcription_pricing"]["unit_rmb_per_second"], 0.00022)
        self.assertEqual(payload["cloud_transcription_pricing"]["estimated_audio_hours_per_10_rmb"], 12.63)
        self.assertNotIn(str(self.root), output.getvalue())


    def test_siliconflow_check_config_shows_free_list_price(self):
        self.config.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "mode": "full",
                    "knowledge_dir": "knowledge",
                    "ledger_path": "state/ledger.sqlite3",
                    "transcription": {
                        "enabled": True,
                        "provider": "siliconflow",
                        "model": "FunAudioLLM/SenseVoiceSmall",
                    },
                    "analysis": {"enabled": False, "provider": "none"},
                    "notification": {"enabled": False, "provider": "none"},
                }
            ),
            encoding="utf-8",
        )
        output = StringIO()
        with patch(
            "douyin_favorites_knowledge.cli.check_siliconflow_environment",
            return_value={"ready": True},
        ), redirect_stdout(output):
            returncode = main(["--config", str(self.config), "check-config"])
        self.assertEqual(returncode, 0)
        payload = json.loads(output.getvalue())
        pricing = payload["cloud_transcription_pricing"]
        self.assertEqual(pricing["provider"], "siliconflow")
        self.assertEqual(pricing["list_price_label"], "免费")
        self.assertIn("siliconflow.cn/pricing", pricing["official_pricing"])


    def test_legacy_collection_ledger_is_not_reimported(self):
        self.ledger.parent.mkdir(parents=True)
        with sqlite3.connect(self.ledger) as connection:
            connection.execute(
                "create table promotions (aweme_id text primary key, content_sha256 text, note_name text, review_sha256 text, promoted_at text)"
            )
            connection.execute(
                "insert into promotions values (?, ?, ?, ?, ?)",
                ("7000000000000000001", "old-schema-hash", "7000000000000000001.md", "old", "old"),
            )
        raw = json.loads(FIXTURE.read_text(encoding="utf-8"))["items"][0]
        review = build_review(load_config(self.config), [{**raw, "source": "collection"}], "fixture")
        self.assertEqual(review["summary"]["candidate_count"], 0)
        self.assertEqual(review["summary"]["already_promoted_count"], 1)

    def test_setup_uses_default_config_for_followup_commands(self):
        setup_config = self.root / "default" / "config.json"
        with patch.dict(os.environ, {"DOUYIN_FAVORITES_CONFIG": str(setup_config)}):
            output = StringIO()
            with redirect_stdout(output):
                setup_code = main(
                    [
                        "setup",
                        "--knowledge-dir",
                        str(self.knowledge),
                        "--transcription",
                        "none",
                        "--skip-login",
                    ]
                )
            self.assertEqual(setup_code, 0)
            output = StringIO()
            with redirect_stdout(output):
                check_code = main(["check-config"])
        self.assertEqual(check_code, 0)
        self.assertEqual(json.loads(output.getvalue())["mode"], "light")

    def test_setup_does_not_silently_ignore_new_directory(self):
        output = StringIO()
        errors = StringIO()
        with redirect_stdout(output), patch("sys.stderr", errors):
            returncode = main(
                [
                    "--config",
                    str(self.config),
                    "setup",
                    "--knowledge-dir",
                    str(self.root / "another-knowledge"),
                    "--skip-login",
                ]
            )
        self.assertEqual(returncode, 1)
        self.assertIn("setup --force", errors.getvalue())
        self.assertFalse((self.root / "another-knowledge").exists())

    def test_sync_silently_promotes_new_favorites(self):
        source_items = json.loads(FIXTURE.read_text(encoding="utf-8"))["items"]
        output = StringIO()
        with patch(
            "douyin_favorites_knowledge.cli.collect_browser_favorites",
            return_value=source_items,
        ), patch("builtins.input") as prompt, redirect_stdout(output):
            returncode = main(["--config", str(self.config), "sync"])
        self.assertEqual(returncode, 0)
        prompt.assert_not_called()
        result = json.loads(output.getvalue())
        self.assertEqual(result["status"], "committed")
        self.assertEqual(result["promoted_count"], 2)
        self.assertEqual(len(list(self.knowledge.glob("*.md"))), 2)

    def test_sync_yes_remains_compatible_but_is_not_required(self):
        source_items = json.loads(FIXTURE.read_text(encoding="utf-8"))["items"]
        output = StringIO()
        with patch(
            "douyin_favorites_knowledge.cli.collect_browser_favorites",
            return_value=source_items,
        ), patch("builtins.input") as prompt, redirect_stdout(output):
            returncode = main(["--config", str(self.config), "sync", "--yes"])
        self.assertEqual(returncode, 0)
        prompt.assert_not_called()
        result = json.loads(output.getvalue())
        self.assertEqual(result["status"], "committed")
        self.assertEqual(result["promoted_count"], 2)

    def test_sync_reports_no_changes_after_same_items_are_committed(self):
        source_items = json.loads(FIXTURE.read_text(encoding="utf-8"))["items"]
        with patch(
            "douyin_favorites_knowledge.cli.collect_browser_favorites",
            return_value=source_items,
        ), redirect_stdout(StringIO()):
            self.assertEqual(main(["--config", str(self.config), "sync", "--yes"]), 0)
        output = StringIO()
        with patch(
            "douyin_favorites_knowledge.cli.collect_browser_favorites",
            return_value=source_items,
        ), redirect_stdout(output):
            returncode = main(["--config", str(self.config), "sync", "--yes"])
        self.assertEqual(returncode, 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["status"], "no_changes")
        self.assertEqual(result, {"status": "no_changes"})

    def test_sync_dry_run_writes_nothing(self):
        source_items = json.loads(FIXTURE.read_text(encoding="utf-8"))["items"]
        output = StringIO()
        with patch(
            "douyin_favorites_knowledge.cli.collect_browser_favorites",
            return_value=source_items,
        ), redirect_stdout(output):
            returncode = main(["--config", str(self.config), "sync", "--dry-run"])
        self.assertEqual(returncode, 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["status"], "dry_run")
        self.assertEqual(len(result["preview"]), 2)
        self.assertFalse(self.knowledge.exists())
        self.assertFalse(self.ledger.exists())

    def test_daily_writes_a_collection_report_without_prompting(self):
        source_items = [{**item, "source": "collection"} for item in json.loads(FIXTURE.read_text(encoding="utf-8"))["items"]]
        output = StringIO()
        with patch(
            "douyin_favorites_knowledge.cli.collect_browser_favorites",
            return_value=source_items,
        ), patch("builtins.input") as prompt, redirect_stdout(output):
            returncode = main(["--config", str(self.config), "daily", "--date", "2026-07-30"])
        self.assertEqual(returncode, 0)
        prompt.assert_not_called()
        result = json.loads(output.getvalue())
        self.assertEqual(result["daily_report"], "written")
        report = self.knowledge / "日报" / "2026-07-30-收藏日报.md"
        self.assertIn("今日新增 2 条", report.read_text(encoding="utf-8"))
        self.assertIn("[[collection-7000000000000000001|", report.read_text(encoding="utf-8"))

    def test_daily_keeps_like_reports_separate(self):
        source_items = [{**item, "source": "like"} for item in json.loads(FIXTURE.read_text(encoding="utf-8"))["items"]]
        with patch("douyin_favorites_knowledge.cli.collect_browser_favorites", return_value=source_items), redirect_stdout(StringIO()):
            returncode = main(["--config", str(self.config), "daily", "--source", "like", "--date", "2026-07-30"])
        self.assertEqual(returncode, 0)
        self.assertTrue((self.knowledge / "日报" / "2026-07-30-喜欢日报.md").exists())
        self.assertTrue((self.knowledge / "like-7000000000000000001.md").exists())

    def test_full_mode_runs_configured_stages_in_order(self):
        self.config.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "mode": "full",
                    "knowledge_dir": "knowledge",
                    "ledger_path": "state/ledger.sqlite3",
                    "transcription": {
                        "enabled": True,
                        "provider": "local",
                        "adapter": "example.pipeline:transcribe",
                        "model": "user-selected-asr",
                    },
                    "analysis": {
                        "enabled": True,
                        "provider": "minimax",
                        "adapter": "example.pipeline:analyze",
                        "model": "user-selected-analysis-model",
                    },
                    "notification": {"enabled": False, "provider": "none"},
                }
            ),
            encoding="utf-8",
        )
        calls = []

        def load(spec):
            if spec.endswith(":transcribe"):
                def transcribe(item, context):
                    calls.append((context["stage"], context["provider"], context["model"]))
                    return {"transcript": "本地转录结果"}

                return transcribe

            def analyze(item, context):
                calls.append((context["stage"], context["provider"], context["model"]))
                self.assertEqual(item["transcript"], "本地转录结果")
                return {
                    "tags": ["自动分析"],
                    "analysis": {
                        "content_summary": "视频讲解了公开仓库的发布流程。",
                        "value_judgment": "4/5：可以直接复用。",
                        "deep_analysis": "关键在于把发布与验证拆开。",
                        "extensions": "可结合 CI 记录证据。",
                        "action_items": "先运行单元测试。",
                        "related_knowledge": "[[发布清单]]",
                    },
                }

            return analyze

        output = StringIO()
        with patch("douyin_favorites_knowledge.cli.load_adapter", side_effect=load), redirect_stdout(output):
            returncode = main(
                [
                    "--config",
                    str(self.config),
                    "scan",
                    "--input",
                    str(FIXTURE),
                    "--review",
                    str(self.review),
                ]
            )
        self.assertEqual(returncode, 0)
        self.assertEqual(
            calls,
            [
                ("transcription", "local", "user-selected-asr"),
                ("transcription", "local", "user-selected-asr"),
                ("analysis", "minimax", "user-selected-analysis-model"),
                ("analysis", "minimax", "user-selected-analysis-model"),
            ],
        )
        review = json.loads(self.review.read_text(encoding="utf-8"))
        self.assertEqual(review["items"][0]["transcript"], "本地转录结果")
        self.assertEqual(review["items"][0]["tags"], ["自动分析"])
        self.assertIn("## 要点", review["items"][0]["note"])
        self.assertIn("## 研判", review["items"][0]["note"])
        self.assertIn("[[发布清单]]", review["items"][0]["note"])

    def test_analysis_rejects_unknown_fields(self):
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        payload["items"][0]["analysis"] = {"unsupported": "value"}
        source = self.root / "invalid-analysis.json"
        source.write_text(json.dumps(payload), encoding="utf-8")
        result = self.scan(source)
        self.assertEqual(result.returncode, 1)
        self.assertIn("analysis has unknown fields", result.stderr)

    def test_light_mode_rejects_enabled_optional_stage(self):
        self.config.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "mode": "light",
                    "knowledge_dir": "knowledge",
                    "ledger_path": "state/ledger.sqlite3",
                    "analysis": {
                        "enabled": True,
                        "provider": "adapter",
                        "adapter": "example.pipeline:analyze",
                    },
                }
            ),
            encoding="utf-8",
        )
        result = self.scan()
        self.assertEqual(result.returncode, 1)
        self.assertIn("light mode cannot enable optional stages", result.stderr)

    def test_provider_credentials_cannot_be_written_to_config(self):
        self.config.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "mode": "full",
                    "knowledge_dir": "knowledge",
                    "ledger_path": "state/ledger.sqlite3",
                    "analysis": {
                        "enabled": True,
                        "provider": "minimax",
                        "adapter": "example.pipeline:analyze",
                        "model": "example-model",
                        "options": {"api_key": "placeholder"},
                    },
                }
            ),
            encoding="utf-8",
        )
        result = self.scan()
        self.assertEqual(result.returncode, 1)
        self.assertIn("secret-like key blocked", result.stderr)

    def test_invalid_provider_type_is_reported_without_traceback(self):
        self.config.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "mode": "full",
                    "knowledge_dir": "knowledge",
                    "ledger_path": "state/ledger.sqlite3",
                    "analysis": {"enabled": True, "provider": ["minimax"]},
                }
            ),
            encoding="utf-8",
        )
        result = self.scan()
        self.assertEqual(result.returncode, 1)
        self.assertIn("unsupported analysis provider", result.stderr)

    def test_legacy_douyin_mcp_provider_is_rejected(self):
        self.config.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "mode": "full",
                    "knowledge_dir": "knowledge",
                    "ledger_path": "state/ledger.sqlite3",
                    "transcription": {"enabled": True, "provider": "douyin_mcp", "model": "legacy"},
                    "analysis": {"enabled": False, "provider": "none"},
                    "notification": {"enabled": False, "provider": "none"},
                }
            ),
            encoding="utf-8",
        )
        result = cli(self.config, "check-config")
        self.assertEqual(result.returncode, 1)
        self.assertIn("unsupported transcription provider", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_invalid_schema_version_type_is_reported_without_traceback(self):
        payload = json.loads(self.config.read_text(encoding="utf-8"))
        payload["schema_version"] = [2]
        self.config.write_text(json.dumps(payload), encoding="utf-8")
        result = self.scan()
        self.assertEqual(result.returncode, 1)
        self.assertIn("schema_version must be 1 or 2", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_adapter_runtime_error_is_redacted(self):
        token = "sk-" + "A" * 24
        output = StringIO()
        errors = StringIO()
        with patch(
            "douyin_favorites_knowledge.cli.load_adapter",
            return_value=lambda item, context: (_ for _ in ()).throw(RuntimeError(token)),
        ), redirect_stdout(output), patch("sys.stderr", errors):
            returncode = main(
                [
                    "--config",
                    str(self.config),
                    "scan",
                    "--input",
                    str(FIXTURE),
                    "--enricher",
                    "example.pipeline:enrich",
                    "--review",
                    str(self.review),
                ]
            )
        self.assertEqual(returncode, 1)
        self.assertNotIn(token, errors.getvalue())
        self.assertIn("[REDACTED]", errors.getvalue())
        self.assertFalse(self.review.exists())

    def test_configured_notifier_receives_stage_context(self):
        self.config.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "mode": "full",
                    "knowledge_dir": "knowledge",
                    "ledger_path": "state/ledger.sqlite3",
                    "notification": {
                        "enabled": True,
                        "provider": "feishu",
                        "adapter": "example.pipeline:notify",
                    },
                }
            ),
            encoding="utf-8",
        )
        self.assertEqual(self.scan().returncode, 0)
        self.assertEqual(self.approve().returncode, 0)
        seen = []

        def notifier(event, context):
            seen.append((event["promoted_count"], context))

        output = StringIO()
        with patch("douyin_favorites_knowledge.cli.load_adapter", return_value=notifier), redirect_stdout(output):
            returncode = main(
                [
                    "--config",
                    str(self.config),
                    "promote",
                    "--review",
                    str(self.review),
                    "--approval",
                    str(self.approval),
                ]
            )
        self.assertEqual(returncode, 0)
        self.assertEqual(seen[0][0], 2)
        self.assertEqual(seen[0][1]["stage"], "notification")
        self.assertEqual(seen[0][1]["provider"], "feishu")

    def test_concurrent_promotions_serialize(self):
        self.assertEqual(self.scan().returncode, 0)
        self.assertEqual(self.approve().returncode, 0)
        command = [
            sys.executable,
            "-m",
            "douyin_favorites_knowledge",
            "--config",
            str(self.config),
            "promote",
            "--review",
            str(self.review),
            "--approval",
            str(self.approval),
        ]
        env = dict(os.environ)
        env["PYTHONPATH"] = PYTHONPATH
        processes = [
            subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
            for _ in range(2)
        ]
        results = [process.communicate(timeout=30) + (process.returncode,) for process in processes]
        for stdout, stderr, returncode in results:
            self.assertEqual(returncode, 0, stdout + stderr)
        payloads = [json.loads(stdout) for stdout, _, _ in results]
        self.assertEqual(sum(item["promoted_count"] for item in payloads), 2)
        self.assertEqual(sum(item["skipped_count"] for item in payloads), 2)

    def test_sensitive_error_details_are_redacted(self):
        token = "sk-" + "A" * 24
        private_path = "/" + "Users/example/private/file"
        message = safe_error_message(ValueError(f"failed with {token} at {private_path}"))
        self.assertNotIn(token, message)
        self.assertNotIn(private_path, message)
        self.assertIn("[REDACTED]", message)
        self.assertIn("[PRIVATE_PATH]", message)
        reasoning = "<" + "think>private chain</think>"
        self.assertEqual(
            safe_error_message(ValueError(reasoning)),
            "sensitive error detail redacted",
        )


if __name__ == "__main__":
    unittest.main()
