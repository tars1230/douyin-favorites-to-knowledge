import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from douyin_favorites_knowledge import local_whisper


class LocalWhisperTests(unittest.TestCase):
    def test_stale_temp_workspace_is_removed(self):
        with tempfile.TemporaryDirectory() as root:
            with patch("douyin_favorites_knowledge.local_whisper.tempfile.gettempdir", return_value=root):
                stale = Path(root) / "douyin-local-asr-stale"
                stale.mkdir()
                (stale / "source.mp4").write_bytes(b"old")
                old = time.time() - local_whisper.STALE_TEMP_SECONDS - 1
                import os
                os.utime(stale, (old, old))
                self.assertEqual(local_whisper.cleanup_stale_temp_dirs(), 1)
                self.assertFalse(stale.exists())

    def test_oversized_media_is_rejected_before_model_load(self):
        class Response:
            headers = {"Content-Length": "10"}

            def read(self, _size):
                return b""

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        with patch("douyin_favorites_knowledge.local_whisper.check_environment", return_value={"ready": True}), patch(
            "douyin_favorites_knowledge.local_whisper.urllib.request.urlopen", return_value=Response()
        ), patch("douyin_favorites_knowledge.local_whisper.MAX_MEDIA_BYTES", 5):
            result = local_whisper.transcribe({"play_url": "https://example.test/video.mp4"}, {"model": "small"})
        self.assertEqual(result["transcript_status"], "too_large")
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
