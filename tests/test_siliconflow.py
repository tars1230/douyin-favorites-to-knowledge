import os
import tempfile
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


class SiliconFlowAudioFirstTests(unittest.TestCase):
    def test_prefers_audio_url_before_play_url(self):
        order = []

        def fake_download(url, destination, max_bytes):
            order.append(url)
            destination.write_bytes(b"fake-media")
            return None

        def fake_upload(path, api_key, model, endpoint):
            # succeed only for audio candidate path content after extract skip
            return "来自音频轨"

        with patch.dict(os.environ, {"SILICONFLOW_API_KEY": "sf-key", "DOUYIN_ASR_AUDIO_BITRATE": "48k"}, clear=True), patch(
            "douyin_favorites_knowledge.siliconflow._download_media", side_effect=fake_download
        ), patch(
            "douyin_favorites_knowledge.siliconflow._extract_audio", return_value=False
        ), patch(
            "douyin_favorites_knowledge.siliconflow._upload_transcribe", side_effect=fake_upload
        ):
            result = siliconflow.transcribe(
                {
                    "audio_url": "https://cdn.example/a.m4a",
                    "play_url": "https://v3-web.douyinvod.com/big.mp4",
                },
                {},
            )
        self.assertEqual(result["transcript_status"], "success")
        self.assertEqual(order[0], "https://cdn.example/a.m4a")
        self.assertEqual(result.get("media_kind_used"), "audio")

    def test_falls_back_to_play_url_when_audio_fails(self):
        def fake_download(url, destination, max_bytes):
            if url.endswith(".m4a"):
                return "failed"
            destination.write_bytes(b"video-bytes")
            return None

        with patch.dict(os.environ, {"SILICONFLOW_API_KEY": "sf-key"}, clear=True), patch(
            "douyin_favorites_knowledge.siliconflow._download_media", side_effect=fake_download
        ), patch(
            "douyin_favorites_knowledge.siliconflow._extract_audio", return_value=False
        ), patch(
            "douyin_favorites_knowledge.siliconflow._upload_transcribe", return_value="视频回退成功"
        ):
            result = siliconflow.transcribe(
                {
                    "audio_url": "https://cdn.example/a.m4a",
                    "play_url": "https://v3-web.douyinvod.com/big.mp4",
                },
                {},
            )
        self.assertEqual(result["transcript_status"], "success")
        self.assertEqual(result["transcript"], "视频回退成功")
        self.assertEqual(result.get("media_kind_used"), "play")

    def test_bitrate_env_passed_to_ffmpeg(self):
        seen = {}

        def fake_run(cmd, **kwargs):
            seen["cmd"] = cmd
            # create output path (last arg)
            Path(cmd[-1]).write_bytes(b"x")
            return MagicMock(returncode=0)

        src = Path("/tmp/douyin-sf-src-test.bin")
        # unit the helper directly
        with patch.dict(os.environ, {"DOUYIN_ASR_AUDIO_BITRATE": "32k", "DOUYIN_ASR_SAMPLE_RATE": "16000"}, clear=False), patch(
            "douyin_favorites_knowledge.siliconflow.shutil.which", return_value="/usr/bin/ffmpeg"
        ), patch(
            "douyin_favorites_knowledge.siliconflow.subprocess.run", side_effect=fake_run
        ):
            with tempfile.TemporaryDirectory() as td:
                source = Path(td) / "source.mp4"
                audio = Path(td) / "audio.mp3"
                source.write_bytes(b"abc")
                ok = siliconflow._extract_audio(source, audio)
        self.assertTrue(ok)
        self.assertIn("-b:a", seen["cmd"])
        self.assertIn("32k", seen["cmd"])
