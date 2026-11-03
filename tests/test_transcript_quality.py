import json
import tempfile
import unittest
from pathlib import Path

from douyin_favorites_knowledge.config import load_config
from douyin_favorites_knowledge.transcript_quality import (
    assess_transcript,
    batch_report,
    layer_counts,
    saved_quality,
)
from douyin_favorites_knowledge.workflow import SCHEMA_VERSION, normalize_item, render_note, validate_review


AWEME = "7000000000000000001"
LONG = (
    "这是一段把步骤说清楚的口播，先热锅再下油，炒到变色再出锅，最后撒上葱花就完成了。"
    "读者可以照着做，不必再猜画面里没说出来的火候和顺序。"
)


def _note_item(**extra):
    item = {
        "aweme_id": AWEME,
        "title": "周末厨房",
        "author": "",
        "description": "周末厨房",
        "transcript": LONG,
        "transcript_source": "siliconflow_sensevoice",
        "transcript_status": "success",
        "tags": [],
        "observed_at": "2026-11-03T00:00:00+00:00",
        "source_url": f"https://www.douyin.com/video/{AWEME}",
        "source": "collection",
    }
    item.update(extra)
    return item


class QualityGateTests(unittest.TestCase):
    def test_gate_off_does_not_score(self):
        self.assertEqual(assess_transcript({"transcript_status": "success", "transcript": "嗯"}, {"enabled": False}), {})
        self.assertEqual(assess_transcript({"transcript_status": "success", "transcript": "嗯"}, None), {})

    def test_short_fragment_and_low_cjk_are_low(self):
        settings = {"enabled": True, "lyric_conflict": False}
        self.assertEqual(assess_transcript({"transcript_status": "success", "transcript": "嗯嗯"}, settings)["transcript_quality"], "low")
        noisy = {"transcript_status": "success", "transcript": "啊。" * 30}
        self.assertGreaterEqual(len(noisy["transcript"]), 40)
        self.assertEqual(assess_transcript(noisy, settings)["transcript_quality"], "low")
        english = {"transcript_status": "success", "transcript": "this is a long english caption with no chinese characters in it at all"}
        self.assertEqual(assess_transcript(english, settings)["transcript_quality"], "low")

    def test_clear_chinese_speech_is_usable(self):
        result = assess_transcript(
            {"transcript_status": "success", "transcript": LONG, "description": "周末厨房"},
            {"enabled": True},
        )
        self.assertIn(result["transcript_quality"], {"medium", "high"})

    def test_screen_text_is_not_scored_as_speech(self):
        self.assertEqual(
            assess_transcript(
                {"transcript_status": "screen_text", "transcript": "画面上的步骤写得很清楚，足够长。"},
                {"enabled": True},
            ),
            {},
        )

    def test_music_mark_without_overlap_is_not_speech(self):
        conflict = assess_transcript(
            {
                "transcript_status": "success",
                "transcript": LONG,
                "description": "🎼 背景音乐",
            },
            {"enabled": True, "lyric_conflict": True},
        )
        self.assertEqual(conflict["transcript_quality"], "lyric_conflict")
        shared = assess_transcript(
            {
                "transcript_status": "success",
                "transcript": "先热锅再下油，炒到变色再出锅。" + LONG,
                "description": "🎼 先热锅再下油",
            },
            {"enabled": True, "lyric_conflict": True},
        )
        self.assertNotEqual(shared["transcript_quality"], "lyric_conflict")
        unmarked = assess_transcript(
            {"transcript_status": "success", "transcript": LONG, "description": "今天的日常"},
            {"enabled": True, "lyric_conflict": True},
        )
        self.assertNotEqual(unmarked["transcript_quality"], "lyric_conflict")

    def test_lyric_check_can_be_turned_off(self):
        result = assess_transcript(
            {"transcript_status": "success", "transcript": LONG, "description": "🎼 背景音乐"},
            {"enabled": True, "lyric_conflict": False},
        )
        self.assertNotEqual(result["transcript_quality"], "lyric_conflict")


class NoteLayerTests(unittest.TestCase):
    def test_caption_is_a_side_note_and_speech_is_labeled(self):
        note = render_note(_note_item())
        self.assertLess(note.index("### 口播"), note.index("## 旁注"))
        self.assertIn("这是口播转写，不是简介。", note)
        self.assertIn("这是简介，不是口播。", note)
        speech = note.split("### 口播", 1)[1].split("## 旁注", 1)[0]
        self.assertIn(LONG, speech)
        self.assertNotIn("周末厨房", speech)

    def test_low_quality_and_lyrics_are_not_presented_as_speech(self):
        low = render_note(_note_item(transcript_quality="low", transcript="啊。" * 10))
        self.assertNotIn("### 口播", low)
        self.assertIn("### 未看懂", low)
        self.assertIn("不能当成已经看懂", low)
        lyric = render_note(_note_item(transcript_quality="lyric_conflict", description="🎼 背景音乐"))
        self.assertNotIn("### 口播", lyric)
        self.assertIn("不把下面的字当作口播", lyric)
        self.assertIn("这是简介，不是口播。", lyric)

    def test_screen_beats_a_missing_speech_layer_and_caption_stays_aside(self):
        note = render_note(_note_item(
            transcript="画面上的步骤和用量",
            transcript_status="screen_text",
            transcript_source="siliconflow_paddleocr",
            description="封面标题",
        ))
        self.assertIn("### 画面上的字", note)
        self.assertNotIn("### 口播", note)
        self.assertLess(note.index("### 画面上的字"), note.index("## 旁注"))
        self.assertIn("这是简介，不是口播。", note)

    def test_caption_only_is_explicitly_not_understood(self):
        note = render_note(_note_item(
            transcript="",
            transcript_status="not_requested",
            transcript_source="none",
            description="只有简介 #刀工",
        ))
        self.assertIn("### 未看懂", note)
        self.assertNotIn("### 口播", note)
        self.assertIn("简介不是口播", note)
        self.assertIn("只有简介 #刀工", note.split("## 旁注", 1)[1])

    def test_quality_round_trips_in_the_hash(self):
        raw = {
            "aweme_id": AWEME,
            "title": "周末厨房",
            "description": "周末厨房",
            "transcript": LONG,
            "transcript_status": "success",
            "transcript_source": "siliconflow_sensevoice",
            "tags": [],
            "source": "collection",
            "transcript_quality": "high",
        }
        item = normalize_item(raw)
        self.assertIn('transcript_quality: "high"', item["note"])
        again = normalize_item({**raw, **saved_quality(item["note"])})
        self.assertEqual(again["content_sha256"], item["content_sha256"])
        validate_review({"schema_version": SCHEMA_VERSION, "items": [item]})


class BatchAndCountTests(unittest.TestCase):
    def test_counts_skip_chat_and_comments(self):
        counts = layer_counts([
            _note_item(),
            _note_item(transcript_status="screen_text", transcript="画面文字足够说明步骤", transcript_source="siliconflow_paddleocr"),
            _note_item(transcript="", transcript_status="not_requested", description="只有简介"),
        ])
        self.assertEqual(set(counts), {"caption", "speech", "screen"})
        self.assertEqual(counts["caption"], 3)
        self.assertEqual(counts["speech"], 1)
        self.assertEqual(counts["screen"], 1)

    def test_batch_warns_without_rejecting_or_using_a_category_name(self):
        items = [_note_item(transcript_quality="low") for _ in range(4)]
        items.append(_note_item(transcript_quality="high", topic="家常菜"))
        report = batch_report(
            items,
            {"enabled": True, "max_missing_topic_ratio": 0.5, "max_low_quality_ratio": 0.5},
            topic_enabled=True,
        )
        self.assertEqual(report["status"], "warn")
        self.assertTrue(report["warn_only"])
        self.assertNotIn("rejected", report["status"])
        blob = json.dumps(report, ensure_ascii=False)
        self.assertNotIn("其他", blob)
        quiet = batch_report(items, {"enabled": False}, topic_enabled=True)
        self.assertIsNone(quiet)
        skipped = batch_report(items, {"enabled": True, "max_missing_topic_ratio": 0.2}, topic_enabled=False)
        self.assertNotIn("missing_topic_ratio", skipped)

    def test_bad_ratio_is_rejected_by_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "config.json"
            path.write_text(json.dumps({
                "schema_version": 2,
                "mode": "light",
                "knowledge_dir": str(root / "kb"),
                "ledger_path": str(root / "ledger.sqlite3"),
                "transcription": {"enabled": False, "provider": "none"},
                "analysis": {"enabled": False, "provider": "none"},
                "notification": {"enabled": False, "provider": "none"},
                "transcript_quality": {"enabled": True, "min_cjk_ratio": 2},
            }), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_config(path)
            plain = root / "plain.json"
            plain.write_text(json.dumps({
                "schema_version": 2,
                "mode": "light",
                "knowledge_dir": str(root / "kb"),
                "ledger_path": str(root / "ledger.sqlite3"),
                "transcription": {"enabled": False, "provider": "none"},
                "analysis": {"enabled": False, "provider": "none"},
                "notification": {"enabled": False, "provider": "none"},
            }), encoding="utf-8")
            loaded = load_config(plain)
        self.assertIs(loaded.transcript_quality["enabled"], False)
        self.assertIs(loaded.batch_quality["enabled"], False)
        self.assertIs(loaded.batch_quality["warn_only"], True)
