import unittest
from unittest.mock import Mock, patch

from douyin_favorites_knowledge.provider_discovery import discover


class ProviderDiscoveryTests(unittest.TestCase):
    def test_recommends_siliconflow_when_ready(self):
        with patch(
            "douyin_favorites_knowledge.provider_discovery.check_siliconflow",
            return_value={"ready": True},
        ), patch(
            "douyin_favorites_knowledge.provider_discovery.check_bailian",
            return_value={"ready": True},
        ), patch(
            "douyin_favorites_knowledge.provider_discovery.check_local_whisper",
            return_value={"ready": False, "missing": ["ffmpeg"]},
        ), patch("douyin_favorites_knowledge.provider_discovery.shutil.which", return_value=None):
            result = discover()
        self.assertEqual(result["siliconflow"], {
            "state": "ready",
            "note": "Douyin CDN 推荐主路径：本机 Referer 下载后上传 SenseVoice",
        })
        self.assertEqual(result["recommended"], "siliconflow")

    def test_falls_back_recommendation_order(self):
        with patch(
            "douyin_favorites_knowledge.provider_discovery.check_siliconflow",
            return_value={"ready": False, "missing": ["SILICONFLOW_API_KEY"]},
        ), patch(
            "douyin_favorites_knowledge.provider_discovery.check_bailian",
            return_value={"ready": False, "missing": ["DASHSCOPE_API_KEY"]},
        ), patch(
            "douyin_favorites_knowledge.provider_discovery.check_local_whisper",
            return_value={"ready": True},
        ), patch("douyin_favorites_knowledge.provider_discovery.shutil.which", return_value=None):
            result = discover()
        self.assertEqual(result["recommended"], "local")

    def test_mmx_tts_only_is_not_claimed_as_asr(self):
        with patch(
            "douyin_favorites_knowledge.provider_discovery.check_siliconflow",
            return_value={"ready": False, "missing": ["SILICONFLOW_API_KEY"]},
        ), patch(
            "douyin_favorites_knowledge.provider_discovery.check_bailian",
            return_value={"ready": False, "missing": ["DASHSCOPE_API_KEY"]},
        ), patch(
            "douyin_favorites_knowledge.provider_discovery.check_local_whisper",
            return_value={"ready": True},
        ), patch(
            "douyin_favorites_knowledge.provider_discovery.shutil.which",
            return_value="/usr/bin/mmx",
        ), patch(
            "douyin_favorites_knowledge.provider_discovery.subprocess.run",
            return_value=Mock(stdout="synthesize generate voices", stderr="", returncode=0),
        ):
            result = discover()
        self.assertEqual(result["recommended"], "local")
        self.assertEqual(result["minimax"]["state"], "unavailable")


    def test_siliconflow_is_default_recommendation(self) -> None:
        from douyin_favorites_knowledge.provider_discovery import discover
        d = discover()
        self.assertEqual(d["recommended"], "siliconflow")
        self.assertIn("SenseVoice", d["siliconflow"]["note"])
