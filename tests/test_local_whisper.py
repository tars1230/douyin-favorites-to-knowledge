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

    def test_image_post_skips_whisper_and_is_not_retryable(self):
        with patch("douyin_favorites_knowledge.local_whisper._download") as download:
            result = local_whisper.transcribe(
                {"media_kind": "image", "play_url": "https://example.test/slideshow.mp4"},
                {"model": "small"},
            )
        download.assert_not_called()
        self.assertEqual(result["transcript_status"], "skipped_image")
        self.assertEqual(result["transcript"], "")

    def test_http_403_tries_the_next_play_url(self):
        import urllib.error
        from email.message import Message

        seen = []

        class Response:
            headers = {}

            def read(self, _size):
                if getattr(self, "_done", False):
                    return b""
                self._done = True
                return b"media"

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        def urlopen(request, timeout=180):
            seen.append((request.full_url, dict(request.header_items())))
            if len(seen) == 1:
                raise urllib.error.HTTPError(request.full_url, 403, "forbidden", Message(), None)
            return Response()

        class Segment:
            text = "口播正文"

        class Model:
            def transcribe(self, *_args, **_kwargs):
                return [Segment()], None

        def fake_run(cmd, **_kwargs):
            Path(cmd[-1]).write_bytes(b"wav")
            return type("R", (), {"returncode": 0})()

        from douyin_favorites_knowledge.cdn_auth import clear_cdn_cookies, remember_cdn_cookies

        remember_cdn_cookies([{"name": "ttwid", "value": "cdn-secret", "domain": ".douyinvod.com"}])
        try:
            with patch("douyin_favorites_knowledge.local_whisper.check_environment", return_value={"ready": True}), patch(
                "douyin_favorites_knowledge.local_whisper.urllib.request.urlopen", side_effect=urlopen
            ), patch(
                "douyin_favorites_knowledge.local_whisper.subprocess.run", side_effect=fake_run
            ), patch(
                "douyin_favorites_knowledge.local_whisper._load_model", return_value=Model()
            ):
                result = local_whisper.transcribe(
                    {
                        "play_url": "https://v3-web.douyinvod.com/a.mp4",
                        "play_urls": [
                            "https://v3-web.douyinvod.com/a.mp4",
                            "https://v11-web.douyinvod.com/b.mp4",
                        ],
                    },
                    {"model": "small"},
                )
        finally:
            clear_cdn_cookies()
        self.assertEqual(result["transcript"], "口播正文")
        self.assertEqual(result["transcript_status"], "success")
        self.assertEqual([url for url, _headers in seen], [
            "https://v3-web.douyinvod.com/a.mp4",
            "https://v11-web.douyinvod.com/b.mp4",
        ])
        cookie = {key.lower(): value for key, value in seen[1][1].items()}.get("cookie", "")
        self.assertIn("ttwid=cdn-secret", cookie)
