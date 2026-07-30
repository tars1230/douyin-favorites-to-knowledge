import unittest
from unittest.mock import Mock, patch

from douyin_favorites_knowledge.provider_discovery import discover


class ProviderDiscoveryTests(unittest.TestCase):
    def test_reports_ready_bailian_without_disclosing_credentials(self):
        with patch("douyin_favorites_knowledge.provider_discovery.check_bailian", return_value={"ready": True}), patch(
            "douyin_favorites_knowledge.provider_discovery.check_local_whisper", return_value={"ready": False, "missing": ["ffmpeg"]}
        ), patch("douyin_favorites_knowledge.provider_discovery.shutil.which", return_value=None):
            result = discover()
        self.assertEqual(result["bailian"], {"state": "ready"})
        self.assertEqual(result["recommended"], "bailian")
        self.assertEqual(result["minimax"]["state"], "unavailable")

    def test_mmx_tts_only_is_not_claimed_as_asr(self):
        with patch("douyin_favorites_knowledge.provider_discovery.check_bailian", return_value={"ready": False, "missing": ["DASHSCOPE_API_KEY"]}), patch(
            "douyin_favorites_knowledge.provider_discovery.check_local_whisper", return_value={"ready": True}
        ), patch("douyin_favorites_knowledge.provider_discovery.shutil.which", return_value="/usr/bin/mmx"), patch(
            "douyin_favorites_knowledge.provider_discovery.subprocess.run", return_value=Mock(stdout="synthesize generate voices", stderr="", returncode=0)
        ):
            result = discover()
        self.assertEqual(result["recommended"], "local")
        self.assertEqual(result["minimax"]["state"], "unavailable")
