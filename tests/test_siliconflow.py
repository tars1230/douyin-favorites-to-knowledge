import os
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from douyin_favorites_knowledge import siliconflow


class SiliconFlowTests(unittest.TestCase):
    def test_missing_key_reported_without_network(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                siliconflow.check_environment(),
                {"ready": False, "missing": ["SILICONFLOW_API_KEY"]},
            )

    def test_transcribe_downloads_with_referer_and_uploads(self):
        calls = {}

        def fake_download(url, destination, max_bytes):
            calls["url"] = url
            destination.write_bytes(b"fake-media")
            return None

        def fake_upload(path, api_key, model, endpoint):
            calls["api_key"] = api_key
            calls["model"] = model
            calls["path"] = str(path)
            return "完整语音文本"

        with patch.dict(os.environ, {"SILICONFLOW_API_KEY": "sf-key"}, clear=True), patch(
            "douyin_favorites_knowledge.siliconflow._download_media", side_effect=fake_download
        ), patch(
            "douyin_favorites_knowledge.siliconflow._extract_audio", return_value=False
        ), patch(
            "douyin_favorites_knowledge.siliconflow._upload_transcribe", side_effect=fake_upload
        ):
            result = siliconflow.transcribe(
                {"play_url": "https://v3-web.douyinvod.com/x.mp4"},
                {"model": "FunAudioLLM/SenseVoiceSmall"},
            )
        self.assertEqual(result["transcript_status"], "success")
        self.assertEqual(result["transcript"], "完整语音文本")
        self.assertEqual(result["transcript_source"], "siliconflow_sensevoice")
        self.assertIn("douyinvod", calls["url"])
        self.assertEqual(calls["api_key"], "sf-key")


class LocalWhisperRefererTests(unittest.TestCase):
    def test_download_request_includes_douyin_referer(self):
        from douyin_favorites_knowledge import local_whisper
        seen = {}

        class FakeResp:
            headers = {}
            def read(self, n=-1):
                if getattr(self, "_done", False):
                    return b""
                self._done = True
                return b"data"
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout=180):
            seen["headers"] = dict(req.headers)
            return FakeResp()

        with patch.dict(os.environ, {}, clear=True), patch(
            "douyin_favorites_knowledge.local_whisper.check_environment",
            return_value={"ready": True},
        ), patch(
            "douyin_favorites_knowledge.local_whisper.urllib.request.urlopen",
            side_effect=fake_urlopen,
        ), patch(
            "douyin_favorites_knowledge.local_whisper.subprocess.run",
            return_value=MagicMock(returncode=1),
        ):
            # will fail after download due to ffmpeg mock returncode 1
            local_whisper.transcribe({"play_url": "https://v3-web.douyinvod.com/x.mp4"}, {})
        # urllib Request lowercases header keys
        headers = {k.lower(): v for k, v in seen.get("headers", {}).items()}
        self.assertIn("referer", headers)
        self.assertIn("douyin.com", headers["referer"])
