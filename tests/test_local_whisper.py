import unittest
from unittest.mock import patch

from douyin_favorites_knowledge import local_whisper


class LocalWhisperTests(unittest.TestCase):
    def test_missing_runtime_is_reported_without_download(self):
        with patch("douyin_favorites_knowledge.local_whisper.shutil.which", return_value=None), patch(
            "douyin_favorites_knowledge.local_whisper.importlib.util.find_spec", return_value=None
        ):
            result = local_whisper.check_environment()
        self.assertFalse(result["ready"])
        self.assertIn("ffmpeg", result["missing"])
        self.assertIn("faster-whisper (install .[local-asr])", result["missing"])

    def test_missing_play_url_is_marked_unavailable(self):
        with patch("douyin_favorites_knowledge.local_whisper.check_environment", return_value={"ready": True}):
            result = local_whisper.transcribe({"aweme_id": "7000000000000000001"}, {"model": "small"})
        self.assertEqual(result, {
            "transcript": "",
            "transcript_source": "local_whisper",
            "transcript_status": "unavailable",
        })
