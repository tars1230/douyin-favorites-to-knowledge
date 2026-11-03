import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from douyin_favorites_knowledge.cli import _finish_understanding, _restore_saved_topic
from douyin_favorites_knowledge.config import load_config
from douyin_favorites_knowledge.topic_classify import (
    classify_item,
    load_taxonomy,
    saved_topic_fields,
    suggest_from_item,
)
from douyin_favorites_knowledge.workflow import SCHEMA_VERSION, normalize_item, render_note, validate_review


AWEME = "7000000000000000001"


def _item(**extra):
    base = {
        "aweme_id": AWEME,
        "title": "周末厨房",
        "author": "",
        "description": "周末厨房",
        "transcript": "",
        "transcript_source": "none",
        "transcript_status": "not_requested",
        "tags": [],
        "observed_at": "2026-11-03T00:00:00+00:00",
        "source": "collection",
        "media_kind": "video",
    }
    base.update(extra)
    return base


class TopicHeuristicTests(unittest.TestCase):
    def test_disabled_classifier_returns_nothing(self):
        item = _item(title="演示 #刀工", tags=["肩颈"])
        self.assertEqual(classify_item(item, {"enabled": False, "mode": "assign"}), {})
        self.assertEqual(classify_item(item, None), {})

    def test_suggest_uses_tags_hashtags_and_brackets_only(self):
        item = _item(title="演示 #刀工", description="【家常菜】步骤", tags=["肩颈"], media_kind="image")
        self.assertEqual(suggest_from_item(item), ["肩颈", "刀工", "家常菜"])
        result = classify_item(item, {"enabled": True, "mode": "suggest"})
        self.assertNotIn("topic", result)
        self.assertEqual(result["topic_suggestions"], ["肩颈", "刀工", "家常菜"])
        self.assertNotIn("image", result["topic_suggestions"])
        self.assertNotIn("video", result["topic_suggestions"])

    def test_plain_title_is_not_a_category(self):
        result = classify_item(_item(title="今天拍的一段视频", media_kind="video"), {"enabled": True, "mode": "suggest"})
        self.assertEqual(result, {})

    def test_assign_uses_only_the_supplied_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "labels.json"
            path.write_text(json.dumps({"labels": ["家常菜", "肩颈拉伸"]}), encoding="utf-8")
            hit = classify_item(
                _item(title="周末学做家常菜", description="不提别的"),
                {"enabled": True, "mode": "assign", "taxonomy_file": str(path)},
            )
            miss = classify_item(
                _item(title="今天只是随便看看"),
                {"enabled": True, "mode": "assign", "taxonomy_file": str(path)},
            )
        self.assertEqual(hit["topic"], "家常菜")
        self.assertNotIn("topic", miss)
        self.assertNotIn("肩颈拉伸", json.dumps(hit, ensure_ascii=False) + json.dumps(miss, ensure_ascii=False))

    def test_suggest_mode_does_not_assign_even_when_a_label_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "labels.json"
            path.write_text(json.dumps(["家常菜"]), encoding="utf-8")
            result = classify_item(
                _item(title="家常菜教程"),
                {"enabled": True, "mode": "suggest", "taxonomy_file": str(path)},
            )
        self.assertNotIn("topic", result)
        self.assertEqual(result["topic_suggestions"], ["家常菜"])

    def test_a_tag_match_wins_over_a_weaker_title_hit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "labels.json"
            path.write_text(json.dumps(["周末", "家常菜"]), encoding="utf-8")
            result = classify_item(
                _item(title="周末学做家常菜", tags=["家常菜"]),
                {"enabled": True, "mode": "assign", "taxonomy_file": str(path)},
            )
        self.assertEqual(result["topic"], "家常菜")
        self.assertEqual(result["topic_suggestions"], ["周末"])

    def test_tie_does_not_assign_a_topic(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "labels.txt"
            path.write_text("# 这是注释，不是分类\n家常菜\n教程\n", encoding="utf-8")
            result = classify_item(
                _item(title="家常菜教程"),
                {"enabled": True, "mode": "assign", "taxonomy_file": str(path)},
            )
        self.assertNotIn("topic", result)
        self.assertEqual(result["topic_suggestions"], ["家常菜", "教程"])

    def test_bad_taxonomy_does_not_raise_or_clear_item_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.json"
            path.write_text("{", encoding="utf-8")
            item = _item(title="演示 #刀工", transcript="口播还在", transcript_status="success")
            result = classify_item(item, {"enabled": True, "mode": "assign", "taxonomy_file": str(path)})
            missing = classify_item(
                item,
                {"enabled": True, "mode": "assign", "taxonomy_file": str(Path(tmp) / "missing.json")},
            )
        self.assertEqual(result["topic_suggestions"], ["刀工"])
        self.assertNotIn("topic", result)
        self.assertEqual(missing["topic_suggestions"], ["刀工"])
        self.assertEqual(item["transcript"], "口播还在")

    def test_classifier_bug_returns_nothing(self):
        with patch("douyin_favorites_knowledge.topic_classify.suggest_from_item", side_effect=RuntimeError("boom")):
            result = classify_item(_item(title="#刀工"), {"enabled": True, "mode": "suggest"})
        self.assertEqual(result, {})

    def test_non_string_taxonomy_is_a_load_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "labels.json"
            path.write_text(json.dumps({"labels": ["家常菜", 1]}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_taxonomy(path)


class TopicNoteTests(unittest.TestCase):
    def test_topic_round_trips_without_becoming_media_kind(self):
        raw = _item(
            transcript="口播正文",
            transcript_status="success",
            transcript_source="siliconflow_sensevoice",
            topic="家常菜",
            topic_suggestions=["刀工"],
        )
        item = normalize_item(raw)
        self.assertNotIn("media_kind", item)
        self.assertNotIn("media_kind", item["note"])
        self.assertIn('topic: "家常菜"', item["note"])
        self.assertIn("主题：家常菜", item["note"])
        self.assertIn("主题建议：刀工", item["note"])
        again = normalize_item({**_item(transcript="口播正文", transcript_status="success", transcript_source="siliconflow_sensevoice"), **saved_topic_fields(item["note"])})
        self.assertEqual(again["content_sha256"], item["content_sha256"])
        validate_review({"schema_version": SCHEMA_VERSION, "items": [item]})

    def test_scene_disclaimer_still_splits_as_screen_text(self):
        from douyin_favorites_knowledge.cli import _saved_screen_fields

        note = render_note({
            "aweme_id": AWEME,
            "title": "无口播",
            "author": "",
            "description": "无口播",
            "transcript": "画面里有人在切葱",
            "transcript_source": "siliconflow_qwen3_vl_32b",
            "transcript_status": "screen_text",
            "tags": [],
            "observed_at": "2026-11-03T00:00:00+00:00",
            "source_url": f"https://www.douyin.com/video/{AWEME}",
            "source": "collection",
        })
        self.assertIn("一两句画面说明", note)
        fields = _saved_screen_fields(note, "无口播")
        self.assertEqual(fields["transcript"], "画面里有人在切葱")


class TopicConfigTests(unittest.TestCase):
    def _write(self, root: Path, payload: dict) -> Path:
        path = root / "config.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _base(self, root: Path, **extra) -> dict:
        payload = {
            "schema_version": 2,
            "mode": "light",
            "knowledge_dir": str(root / "kb"),
            "ledger_path": str(root / "ledger.sqlite3"),
            "transcription": {"enabled": False, "provider": "none"},
            "analysis": {"enabled": False, "provider": "none"},
            "notification": {"enabled": False, "provider": "none"},
        }
        payload.update(extra)
        return payload

    def test_missing_block_stays_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            loaded = load_config(self._write(root, self._base(root)))
        self.assertEqual(loaded.topic_classify, {"enabled": False, "mode": "suggest", "taxonomy_file": ""})

    def test_bad_mode_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = self._base(root, topic_classify={"enabled": True, "mode": "locked"})
            with self.assertRaises(ValueError) as caught:
                load_config(self._write(root, payload))
        self.assertIn("suggest or assign", str(caught.exception))

    def test_relative_taxonomy_path_resolves_beside_the_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "mine.txt").write_text("家常菜\n", encoding="utf-8")
            payload = self._base(root, topic_classify={"enabled": True, "mode": "assign", "taxonomy_file": "mine.txt"})
            loaded = load_config(self._write(root, payload))
            result = classify_item(_item(title="家常菜"), loaded.topic_classify)
        self.assertEqual(result["topic"], "家常菜")
        self.assertTrue(loaded.topic_classify["taxonomy_file"].endswith("mine.txt"))


class UnderstandingOrderTests(unittest.TestCase):
    def _config(self, root: Path, *, topic: bool) -> object:
        (root / "kb").mkdir()
        payload = {
            "schema_version": 2,
            "mode": "full",
            "knowledge_dir": str(root / "kb"),
            "ledger_path": str(root / "ledger.sqlite3"),
            "transcription": {
                "enabled": True,
                "provider": "siliconflow",
                "model": "FunAudioLLM/SenseVoiceSmall",
                "options": {"vision": {"enabled": False, "silent_video": True}},
            },
            "analysis": {"enabled": False, "provider": "none"},
            "notification": {"enabled": False, "provider": "none"},
            "topic_classify": {"enabled": topic, "mode": "suggest", "taxonomy_file": ""},
        }
        path = root / "config.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return load_config(path)

    def test_screen_text_is_kept_when_classification_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(Path(tmp), topic=True)
            item = {"aweme_id": AWEME, "source": "collection", "title": "无口播", "transcript_status": "failed", "transcript": ""}

            def fake_read(raw, options, **kwargs):
                return {
                    **raw,
                    "transcript": "步骤写在画面上 #刀工",
                    "transcript_source": "siliconflow_paddleocr",
                    "transcript_status": "screen_text",
                }

            with patch("douyin_favorites_knowledge.cli.read_screen", side_effect=fake_read), patch(
                "douyin_favorites_knowledge.cli.classify_item", side_effect=RuntimeError("boom")
            ):
                updated = _finish_understanding([item], config)
        self.assertEqual(updated[0]["transcript_status"], "screen_text")
        self.assertIn("刀工", updated[0]["transcript"])
        self.assertNotIn("topic", updated[0])
        self.assertNotIn("topic_suggestions", updated[0])

    def test_screen_text_hashtag_can_become_a_suggestion(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(Path(tmp), topic=True)
            item = {"aweme_id": AWEME, "source": "collection", "title": "无口播", "transcript_status": "failed", "transcript": ""}

            def fake_read(raw, options, **kwargs):
                return {
                    **raw,
                    "transcript": "步骤写在画面上 #刀工",
                    "transcript_source": "siliconflow_paddleocr",
                    "transcript_status": "screen_text",
                }

            with patch("douyin_favorites_knowledge.cli.read_screen", side_effect=fake_read):
                updated = _finish_understanding([item], config)
        self.assertEqual(updated[0]["transcript_status"], "screen_text")
        self.assertEqual(updated[0]["topic_suggestions"], ["刀工"])
        self.assertNotIn("topic", updated[0])

    def test_known_note_is_not_reclassified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = self._config(root, topic=True)
            stored = normalize_item(_item(title="旧标题", topic="旧类", topic_suggestions=["旧建议"]))
            (root / "kb" / f"collection-{AWEME}.md").write_text(stored["note"], encoding="utf-8")
            incoming = _item(title="新标题 #新类", transcript_status="success", transcript="已经入库的口播正文足够长，不应该改主题。")
            with patch("douyin_favorites_knowledge.cli._known_aweme_ids", return_value={AWEME}):
                updated = _finish_understanding([incoming], config)
        self.assertEqual(updated[0]["topic"], "旧类")
        self.assertEqual(updated[0]["topic_suggestions"], ["旧建议"])
        self.assertNotIn("新类", updated[0]["topic_suggestions"])

    def test_known_note_without_a_topic_stays_unclassified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = self._config(root, topic=True)
            stored = normalize_item(_item(title="旧标题"))
            (root / "kb" / f"collection-{AWEME}.md").write_text(stored["note"], encoding="utf-8")
            incoming = _item(title="旧标题 #新类")
            with patch("douyin_favorites_knowledge.cli._known_aweme_ids", return_value={AWEME}):
                updated = _finish_understanding([incoming], config)
        self.assertNotIn("topic", updated[0])
        self.assertNotIn("topic_suggestions", updated[0])

    def test_saved_topic_restores_when_classify_is_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = self._config(root, topic=False)
            stored = normalize_item(_item(topic="家常菜", topic_suggestions=["刀工"]))
            (root / "kb" / f"collection-{AWEME}.md").write_text(stored["note"], encoding="utf-8")
            incoming = _item()
            with patch("douyin_favorites_knowledge.cli._known_aweme_ids", return_value={AWEME}):
                updated = _restore_saved_topic([incoming], config)
        self.assertEqual(updated[0]["topic"], "家常菜")
        self.assertEqual(updated[0]["topic_suggestions"], ["刀工"])


if __name__ == "__main__":
    unittest.main()
