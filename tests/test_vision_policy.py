import json
import os
import unittest
from unittest.mock import patch

from douyin_favorites_knowledge.siliconflow_vision import read_screen
from douyin_favorites_knowledge.vision_policy import (
    OCR_MODEL,
    SCENE_MODEL,
    clean_ocr_text,
    estimate_scene_call_usd,
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
