import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "favorites.json"
PYTHONPATH = str(ROOT / "src")
sys.path.insert(0, PYTHONPATH)

from douyin_favorites_knowledge.security import safe_error_message  # noqa: E402


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

    def test_secret_like_config_key_is_rejected(self):
        payload = json.loads(self.config.read_text(encoding="utf-8"))
        payload["api_key"] = "placeholder"
        self.config.write_text(json.dumps(payload), encoding="utf-8")
        result = self.scan()
        self.assertEqual(result.returncode, 1)
        self.assertIn("secret-like key blocked", result.stderr)

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
