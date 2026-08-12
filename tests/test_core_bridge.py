from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from douyin_favorites_knowledge.browser_collector import register_browser_profile
from douyin_favorites_knowledge.core_bridge import (
    CORE_VERSION,
    REQUIRED_CORE_VERSION,
    ProfileRegistry,
    atomic_write_json,
    canonical_json,
    file_sha256,
    sha256_bytes,
)
from douyin_favorites_knowledge.workflow import sha256_bytes as workflow_sha256


class CoreBridgeTests(unittest.TestCase):
    def test_pinned_core_version(self) -> None:
        self.assertEqual(CORE_VERSION, REQUIRED_CORE_VERSION)
        self.assertEqual(CORE_VERSION, "0.2.0")

    def test_canonical_json_and_hash_stable(self) -> None:
        payload = {"b": 2, "a": 1}
        digest = sha256_bytes(canonical_json(payload))
        self.assertEqual(digest, sha256_bytes(canonical_json({"a": 1, "b": 2})))
        self.assertEqual(workflow_sha256(canonical_json(payload)), digest)

    def test_atomic_write_json_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "item.json"
            atomic_write_json(path, {"z": 1, "a": "中文"})
            text = path.read_text(encoding="utf-8")
            self.assertIn('"a": "中文"', text)
            self.assertTrue(text.endswith("\n"))
            self.assertEqual(file_sha256(path), sha256_bytes(path.read_bytes()))

    def test_register_browser_profile_is_path_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp) / "browser-profile"
            profile.mkdir()
            registry_path = Path(tmp) / "profiles.json"
            # Use isolated registry via monkeypatch of default path through explicit registry.
            registry = ProfileRegistry(registry_path)
            record = registry.register_existing_profile(
                profile, platform_name="douyin", origin="favorites"
            )
            self.assertTrue(record.profile_id.startswith("prof1:"))
            self.assertEqual(record.origin, "favorites")
            self.assertEqual(record.profile_path, str(profile.resolve()))
            again = registry.register_existing_profile(
                profile, platform_name="douyin", origin="favorites"
            )
            self.assertEqual(again.profile_id, record.profile_id)
            loaded = registry.load()
            self.assertEqual(len(loaded), 1)

    def test_register_helper_uses_favorites_origin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            homeish = Path(tmp)
            profile = homeish / "prof"
            # register_browser_profile uses default registry path under real home;
            # call ProfileRegistry path-only API through helper after isolating is hard.
            # Validate helper creates dir and returns record against default registry
            # would pollute user state — so only test the pure registry path above
            # and that helper is importable/callable with temp dir + patched registry.
            from unittest.mock import patch

            with patch(
                "douyin_favorites_knowledge.browser_collector.ProfileRegistry"
            ) as mocked:
                instance = mocked.return_value
                instance.register_existing_profile.return_value = "ok"
                result = register_browser_profile(profile)
                self.assertEqual(result, "ok")
                kwargs = instance.register_existing_profile.call_args.kwargs
                self.assertEqual(kwargs["origin"], "favorites")
                self.assertEqual(kwargs["platform_name"], "douyin")
                self.assertTrue(profile.is_dir())


if __name__ == "__main__":
    unittest.main()
