import json
import os
import unittest
from unittest.mock import patch

from douyin_favorites_knowledge.siliconflow_vision import (
    VIDEO_SCENE_PROMPT,
    ffmpeg_frame_command,
    read_screen,
    _extract_video_frames,
)
from douyin_favorites_knowledge.vision_policy import (
    OCR_MODEL,
    SCENE_MODEL,
    clean_ocr_text,
    estimate_scene_call_usd,
    is_useful_screen_text,
    needs_screen_read,
    vision_enabled,
)


class VisionPolicyTests(unittest.TestCase):
    def test_long_speech_does_not_spend_a_vision_call(self):
        item = {"transcript": "这是一段足够长的口播，不应该再花钱看画面。", "transcript_status": "success"}
        self.assertFalse(needs_screen_read(item))

    def test_image_post_needs_screen_read(self):
        item = {"media_kind": "image", "transcript_status": "skipped_image", "image_urls": ["https://example.com/a.jpg"]}
        self.assertTrue(needs_screen_read(item))

    def test_download_failure_is_not_sent_to_vision(self):
        item = {"transcript_status": "failed", "play_url": "https://example.com/v.mp4"}
        self.assertFalse(needs_screen_read(item))

    def test_silent_video_flag_opens_the_screen_path_only_when_speech_is_missing(self):
        failed = {"transcript_status": "failed", "transcript": "", "play_url": "https://example.com/v.mp4"}
        empty = {"transcript_status": "unavailable", "transcript": "", "transcript_error": "empty_transcript"}
        short = {"transcript_status": "success", "transcript": "嗯", "media_kind": "video"}
        spoken = {
            "transcript": "这是一段足够长的口播，不应该再花钱看画面。口播已经把事情说完了，所以不用再抽帧看画面上的字。",
            "transcript_status": "success",
            "play_url": "https://example.com/v.mp4",
        }
        options = {"vision": {"silent_video": True}}
        self.assertTrue(needs_screen_read(failed, options))
        self.assertTrue(needs_screen_read(empty, options))
        self.assertTrue(needs_screen_read(short, options))
        self.assertFalse(needs_screen_read(spoken, options))
        self.assertFalse(needs_screen_read(failed, {"vision": {"enabled": True}}))
        self.assertFalse(needs_screen_read({"transcript_status": "too_large", "play_url": "https://example.com/v.mp4"}, options))
        self.assertFalse(needs_screen_read({"transcript_status": "budget_exceeded"}, options))
        self.assertFalse(needs_screen_read({"transcript_status": "not_requested", "media_kind": "video"}, options))

    def test_placeholder_screen_text_is_not_useful(self):
        self.assertFalse(is_useful_screen_text("无"))
        self.assertFalse(is_useful_screen_text("没有文字"))
        self.assertFalse(is_useful_screen_text("<|LOC_1|>无"))
        self.assertTrue(is_useful_screen_text("画面上的产品参数和价格说明"))

    def test_missing_vision_config_is_off(self):
        self.assertFalse(vision_enabled({"max_media_bytes": 1}))
        self.assertTrue(vision_enabled({"vision": {"enabled": True}}))

    def test_location_tokens_do_not_count_as_words(self):
        self.assertEqual(clean_ocr_text("<|LOC_12|>\n<|LOC_99|>"), "")
        self.assertEqual(clean_ocr_text("<|LOC_1|>产品参数表和价格说明"), "产品参数表和价格说明")
        self.assertLess(estimate_scene_call_usd(images=1, output_tokens=400), 0.001)
        self.assertLess(estimate_scene_call_usd(images=2, output_tokens=400), 0.001)


class ScreenReadTests(unittest.TestCase):
    def setUp(self):
        self._env = patch.dict(os.environ, {"SILICONFLOW_API_KEY": "test-key"})
        self._env.start()

    def tearDown(self):
        self._env.stop()

    def test_ocr_hit_does_not_call_the_paid_model(self):
        calls = []

        def urlopen(request, timeout):
            body = request.data.decode()
            calls.append(body)
            text = "画面上的产品参数和价格说明"
            payload = {"choices": [{"message": {"content": text}}]}
            return _Response(payload)

        with patch("douyin_favorites_knowledge.siliconflow_vision._load_images", return_value=[b"img"]):
            item = read_screen(
                {"aweme_id": "1", "media_kind": "image", "transcript_status": "skipped_image", "image_urls": ["https://example.com/a.jpg"]},
                {"vision": {"enabled": True}},
                urlopen=urlopen,
            )
        self.assertEqual(item["transcript_status"], "screen_text")
        self.assertEqual(item["transcript_source"], "siliconflow_paddleocr")
        self.assertEqual(len(calls), 1)
        self.assertNotIn(SCENE_MODEL, calls[0])

    def test_short_ocr_falls_back_to_one_32b_call(self):
        calls = []

        def urlopen(request, timeout):
            body = request.data.decode()
            calls.append(body)
            text = "无" if len(calls) == 1 else "画面是一张参数表，字很少。"
            return _Response({"choices": [{"message": {"content": text}}]})

        with patch("douyin_favorites_knowledge.siliconflow_vision._load_images", return_value=[b"img"]):
            item = read_screen(
                {"media_kind": "image", "transcript_status": "skipped_image", "image_urls": ["https://example.com/a.jpg"]},
                {"vision": {"enabled": True}},
                urlopen=urlopen,
            )
        self.assertEqual(len(calls), 2)
        self.assertIn(SCENE_MODEL, calls[1])
        self.assertEqual(item["transcript_source"], "siliconflow_qwen3_vl_32b")

    def test_daily_cap_skips_the_paid_call_but_keeps_free_ocr(self):
        calls = []

        def urlopen(request, timeout):
            calls.append(request.data.decode())
            return _Response({"choices": [{"message": {"content": "画面上的产品参数和价格说明"}}]})

        item = {"media_kind": "image", "transcript_status": "skipped_image", "image_urls": ["https://example.com/a.jpg"]}
        with patch("douyin_favorites_knowledge.siliconflow_vision._load_images", return_value=[b"img"]):
            updated = read_screen(item, {"vision": {"enabled": True, "max_daily_items": 1}}, urlopen=urlopen, daily_used=1)
        self.assertEqual(len(calls), 1)
        self.assertIn(OCR_MODEL, calls[0])
        self.assertNotIn(SCENE_MODEL, calls[0])
        self.assertEqual(updated["transcript_source"], "siliconflow_paddleocr")

    def test_paid_model_stays_off_unless_allowed(self):
        calls = []

        def urlopen(request, timeout):
            calls.append(request.data.decode())
            return _Response({"choices": [{"message": {"content": "短"}}]})

        with patch("douyin_favorites_knowledge.siliconflow_vision._load_images", return_value=[b"img"]):
            item = read_screen(
                {"media_kind": "image", "transcript_status": "skipped_image", "image_urls": ["https://example.com/a.jpg"]},
                {},
                urlopen=urlopen,
                allow_paid=False,
            )
        self.assertEqual(len(calls), 1)
        self.assertNotIn(SCENE_MODEL, calls[0])
        self.assertEqual(item["transcript"], "短")

    def test_custom_ocr_model_is_sent(self):
        calls = []

        def urlopen(request, timeout):
            calls.append(request.data.decode())
            return _Response({"choices": [{"message": {"content": "画面上的产品参数和价格说明"}}]})

        with patch("douyin_favorites_knowledge.siliconflow_vision._load_images", return_value=[b"img"]):
            read_screen(
                {"media_kind": "image", "transcript_status": "skipped_image", "image_urls": ["https://example.com/a.jpg"]},
                {"vision": {"enabled": True, "ocr_model": "my-org/my-ocr"}},
                urlopen=urlopen,
            )
        self.assertEqual(len(calls), 1)
        self.assertIn("my-org/my-ocr", calls[0])
        self.assertNotIn(OCR_MODEL, calls[0])

    def test_custom_output_length_is_sent(self):
        calls = []

        def urlopen(request, timeout):
            calls.append(request.data.decode())
            return _Response({"choices": [{"message": {"content": "画面上的产品参数和价格说明"}}]})

        with patch("douyin_favorites_knowledge.siliconflow_vision._load_images", return_value=[b"img"]):
            read_screen(
                {"media_kind": "image", "transcript_status": "skipped_image", "image_urls": ["https://example.com/a.jpg"]},
                {"vision": {"enabled": True, "max_output_length": 123}},
                urlopen=urlopen,
            )
        self.assertEqual(len(calls), 1)
        self.assertEqual(json.loads(calls[0])["max_tokens"], 123)

    def test_webp_bytes_are_not_labeled_jpeg(self):
        calls = []

        def urlopen(request, timeout):
            calls.append(request.data.decode())
            return _Response({"choices": [{"message": {"content": "画面上的产品参数和价格说明"}}]})

        webp = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"payload"
        with patch("douyin_favorites_knowledge.siliconflow_vision._load_images", return_value=[webp]):
            read_screen(
                {"media_kind": "image", "transcript_status": "skipped_image", "image_urls": ["https://example.com/a.webp"]},
                {"vision": {"enabled": True}},
                urlopen=urlopen,
            )
        self.assertIn("data:image/webp;base64,", calls[0])
        self.assertNotIn("data:image/jpeg;base64,", calls[0])

    def test_failed_video_stays_off_the_screen_path_by_default(self):
        def urlopen(request, timeout):
            raise AssertionError("vision should not run")

        with patch("douyin_favorites_knowledge.siliconflow_vision._extract_video_frames") as frames:
            item = read_screen(
                {"transcript_status": "failed", "play_url": "https://example.com/v.mp4"},
                {"vision": {"enabled": True}},
                urlopen=urlopen,
            )
        frames.assert_not_called()
        self.assertEqual(item["transcript_status"], "failed")

    def test_silent_video_ocr_becomes_screen_text_without_the_paid_model(self):
        calls = []

        def urlopen(request, timeout):
            calls.append(request.data.decode())
            return _Response({"choices": [{"message": {"content": "画面上的步骤：先热锅，再下葱姜"}}]})

        with patch("douyin_favorites_knowledge.siliconflow_vision._extract_video_frames", return_value=[b"\xff\xd8\xffframe"]):
            item = read_screen(
                {"transcript_status": "unavailable", "transcript": "", "play_url": "https://example.com/v.mp4", "media_kind": "video"},
                {"vision": {"silent_video": True, "enabled": False}},
                urlopen=urlopen,
                allow_paid=False,
            )
        self.assertEqual(len(calls), 1)
        self.assertIn(OCR_MODEL, calls[0])
        self.assertNotIn(SCENE_MODEL, calls[0])
        self.assertEqual(item["transcript_status"], "screen_text")
        self.assertEqual(item["transcript_source"], "siliconflow_paddleocr")
        self.assertIn("先热锅", item["transcript"])

    def test_long_asr_still_skips_frames_when_silent_video_is_on(self):
        def urlopen(request, timeout):
            raise AssertionError("vision should not run")

        spoken = "这是一段足够长的口播，不应该再花钱看画面。口播已经把事情说完了，所以不用再抽帧看画面上的字。"
        with patch("douyin_favorites_knowledge.siliconflow_vision._extract_video_frames") as frames:
            item = read_screen(
                {"transcript": spoken, "transcript_status": "success", "play_url": "https://example.com/v.mp4"},
                {"vision": {"silent_video": True, "enabled": True}},
                urlopen=urlopen,
            )
        frames.assert_not_called()
        self.assertEqual(item["transcript"], spoken)
        self.assertEqual(item["transcript_status"], "success")

    def test_placeholder_ocr_does_not_become_the_video_note(self):
        calls = []

        def urlopen(request, timeout):
            calls.append(request.data.decode())
            return _Response({"choices": [{"message": {"content": "没有文字"}}]})

        with patch("douyin_favorites_knowledge.siliconflow_vision._extract_video_frames", return_value=[b"\xff\xd8\xffframe"]):
            item = read_screen(
                {"transcript_status": "failed", "transcript": "", "play_url": "https://example.com/v.mp4"},
                {"vision": {"silent_video": True}},
                urlopen=urlopen,
                allow_paid=False,
            )
        self.assertEqual(len(calls), 1)
        self.assertEqual(item["transcript_status"], "failed")
        self.assertEqual(item["transcript"], "")

    def test_short_video_ocr_can_fall_back_to_one_scene_call(self):
        calls = []

        def urlopen(request, timeout):
            calls.append(request.data.decode())
            text = "无" if len(calls) == 1 else "画面里有人在切葱，案板上放着姜。"
            return _Response({"choices": [{"message": {"content": text}}]})

        with patch("douyin_favorites_knowledge.siliconflow_vision._extract_video_frames", return_value=[b"\xff\xd8\xffframe"]):
            item = read_screen(
                {"transcript_status": "failed", "play_url": "https://example.com/v.mp4", "media_kind": "video"},
                {"vision": {"silent_video": True, "enabled": True}},
                urlopen=urlopen,
            )
        self.assertEqual(len(calls), 2)
        self.assertIn(SCENE_MODEL, calls[1])
        scene_text = json.loads(calls[1])["messages"][0]["content"][1]["text"]
        self.assertEqual(scene_text, VIDEO_SCENE_PROMPT)
        self.assertEqual(item["transcript_source"], "siliconflow_qwen3_vl_32b")
        self.assertIn("切葱", item["transcript"])

    def test_useless_scene_reply_does_not_replace_a_failed_transcript(self):
        calls = []

        def urlopen(request, timeout):
            calls.append(request.data.decode())
            text = "无" if len(calls) == 1 else "没有文字"
            return _Response({"choices": [{"message": {"content": text}}]})

        with patch("douyin_favorites_knowledge.siliconflow_vision._extract_video_frames", return_value=[b"\xff\xd8\xffframe"]):
            item = read_screen(
                {"transcript_status": "failed", "transcript": "", "play_url": "https://example.com/v.mp4"},
                {"vision": {"silent_video": True, "enabled": True}},
                urlopen=urlopen,
            )
        self.assertEqual(len(calls), 2)
        self.assertEqual(item["transcript_status"], "failed")
        self.assertEqual(item.get("_vision_paid"), 1)
        self.assertEqual(item["transcript"], "")

    def test_cover_is_the_fallback_when_frames_cannot_be_cut(self):
        calls = []

        def urlopen(request, timeout):
            calls.append(request.data.decode())
            return _Response({"choices": [{"message": {"content": "封面上的菜名和用量"}}]})

        with patch("douyin_favorites_knowledge.siliconflow_vision._extract_video_frames", return_value=[]), patch(
            "douyin_favorites_knowledge.siliconflow_vision._load_images", return_value=[b"img"]
        ) as load:
            item = read_screen(
                {
                    "transcript_status": "unavailable",
                    "transcript": "",
                    "play_url": "https://example.com/v.mp4",
                    "cover_url": "https://example.com/cover.jpg",
                },
                {"vision": {"silent_video": True}},
                urlopen=urlopen,
                allow_paid=False,
            )
        self.assertEqual(load.call_args.args[0], ["https://example.com/cover.jpg"])
        self.assertEqual(item["transcript_status"], "screen_text")
        self.assertIn("菜名", item["transcript"])

    def test_no_frame_and_no_cover_leaves_the_asr_failure(self):
        def urlopen(request, timeout):
            raise AssertionError("vision should not run")

        with patch("douyin_favorites_knowledge.siliconflow_vision._extract_video_frames", return_value=[]):
            item = read_screen(
                {"transcript_status": "failed", "play_url": "https://example.com/v.mp4"},
                {"vision": {"silent_video": True}},
                urlopen=urlopen,
            )
        self.assertEqual(item["transcript_status"], "failed")


class FrameExtractTests(unittest.TestCase):
    def test_ffmpeg_command_reads_a_local_file(self):
        from pathlib import Path

        command = ffmpeg_frame_command(Path("/tmp/source.mp4"), Path("/tmp/shot-%02d.jpg"), 3)
        self.assertEqual(command[0], "ffmpeg")
        self.assertIn("/tmp/source.mp4", command)
        self.assertNotIn("https://", " ".join(command))
        self.assertIn("fps=1/4,scale='min(768,iw)':-2", command)
        self.assertEqual(command[command.index("-frames:v") + 1], "3")

    def test_extract_downloads_then_cuts_local_frames(self):
        from pathlib import Path
        import subprocess
        import tempfile

        seen = {}

        def fake_download(url, dest, max_bytes):
            seen["url"] = url
            dest.write_bytes(b"video-bytes")
            return None

        def fake_run(cmd, **kwargs):
            seen["cmd"] = cmd
            Path(cmd[-1]).with_name("shot-01.jpg").write_bytes(b"\xff\xd8\xffframe")
            return subprocess.CompletedProcess(cmd, 0)

        with tempfile.TemporaryDirectory() as tmp, patch(
            "douyin_favorites_knowledge.siliconflow_vision.shutil.which", return_value="/usr/bin/ffmpeg"
        ), patch(
            "douyin_favorites_knowledge.siliconflow_vision._download_media", side_effect=fake_download
        ), patch(
            "douyin_favorites_knowledge.siliconflow_vision.subprocess.run", side_effect=fake_run
        ):
            frames = _extract_video_frames(
                {"play_url": "https://v.douyinvod.com/play.mp4"},
                Path(tmp),
                {"vision": {"frame_count": 3}},
                max_bytes=1024,
            )
        self.assertEqual(frames, [b"\xff\xd8\xffframe"])
        self.assertEqual(seen["url"], "https://v.douyinvod.com/play.mp4")
        self.assertNotIn("https://", " ".join(seen["cmd"]))
        self.assertTrue(seen["cmd"][seen["cmd"].index("-i") + 1].endswith(".mp4"))


class _Response:
    def __init__(self, payload):
        import json
        self._raw = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self._raw


if __name__ == "__main__":
    unittest.main()
