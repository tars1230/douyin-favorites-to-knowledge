import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from douyin_favorites_knowledge import bailian


class BailianTests(unittest.TestCase):
    def test_missing_key_and_sdk_are_reported_without_calling_service(self):
        with patch.dict(os.environ, {}, clear=True), patch(
            "douyin_favorites_knowledge.bailian.importlib.util.find_spec", return_value=None
        ):
            self.assertEqual(bailian.check_environment(), {
                "ready": False,
                "missing": ["DASHSCOPE_API_KEY", "dashscope (install .[bailian-asr])"],
            })

    def test_transcribes_play_url_without_local_download(self):
        response = SimpleNamespace(output=SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=[{"text": "完整语音文本"}])
        )]))
        dashscope = SimpleNamespace(MultiModalConversation=SimpleNamespace(call=lambda **_kwargs: response))
        with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "test-key"}, clear=True), patch(
            "douyin_favorites_knowledge.bailian.check_environment", return_value={"ready": True}
        ), patch.dict("sys.modules", {"dashscope": dashscope}):
            result = bailian.transcribe({"play_url": "https://example.test/authorized.mp4"}, {})
        self.assertEqual(result, {
            "transcript": "完整语音文本",
            "transcript_source": "bailian_qwen3_asr_flash",
            "transcript_status": "success",
        })
