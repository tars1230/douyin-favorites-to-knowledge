"""Release metadata must stay consistent across the package, skills and docs.

Offline only: reads repository files and the default config payload.
"""
import json
import re
import tempfile
import unittest
from pathlib import Path

from douyin_favorites_knowledge import config
from douyin_favorites_knowledge.cli import _config_payload
from douyin_favorites_knowledge.vision_policy import (
    MAX_DAILY_ITEMS,
    MAX_OUTPUT_TOKENS,
    OCR_MODEL,
    SCENE_MODEL,
)


ROOT = Path(__file__).resolve().parents[1]


def _frontmatter_version(text: str) -> str:
    header = text.split("---", 2)[1]
    match = re.search(r"(?m)^version:\s*(\S+)\s*$", header)
    return match.group(1) if match else ""


class ReleaseMetadataTests(unittest.TestCase):
    def test_versions_match(self):
        project = re.search(
            r'(?m)^version = "([^"]+)"$',
            (ROOT / "pyproject.toml").read_text(encoding="utf-8"),
        )
        package = re.search(
            r'(?m)^__version__ = "([^"]+)"$',
            (ROOT / "src" / "douyin_favorites_knowledge" / "__init__.py").read_text(encoding="utf-8"),
        )
        changelog = re.search(
            r"(?m)^## \[(\d+\.\d+\.\d+)\]",
            (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"),
        )
        self.assertIsNotNone(project)
        self.assertIsNotNone(package)
        self.assertIsNotNone(changelog)
        versions = {
            "pyproject.toml": project.group(1),
            "__init__.py": package.group(1),
            "SKILL.md": _frontmatter_version((ROOT / "SKILL.md").read_text(encoding="utf-8")),
            "skill/SKILL.md": _frontmatter_version((ROOT / "skill" / "SKILL.md").read_text(encoding="utf-8")),
            "CHANGELOG.md": changelog.group(1),
        }
        self.assertTrue(all(versions.values()), versions)
        self.assertEqual(len(set(versions.values())), 1, versions)

    def test_skill_copies_identical(self):
        self.assertEqual(
            (ROOT / "SKILL.md").read_bytes(),
            (ROOT / "skill" / "SKILL.md").read_bytes(),
        )

    def test_readme_documents_vision_defaults(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for needle in (
            "PaddlePaddle/PaddleOCR-VL-1.5",
            "Qwen/Qwen3-VL-32B-Instruct",
            '"vision"',
            "ocr_model",
            "scene_model",
            "max_daily_items",
        ):
            self.assertIn(needle, readme)

    def test_vision_defaults_match_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = _config_payload(Path(tmp) / "config.json", Path(tmp) / "kb", "siliconflow")
        vision = payload["transcription"]["options"]["vision"]
        self.assertIs(vision["enabled"], False)
        self.assertEqual(vision["ocr_model"], OCR_MODEL)
        self.assertEqual(vision["scene_model"], SCENE_MODEL)
        self.assertEqual(vision["max_daily_items"], MAX_DAILY_ITEMS)
        self.assertEqual(vision["max_output_length"], MAX_OUTPUT_TOKENS)

    def test_setup_siliconflow_config_loads(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            payload = _config_payload(config_path, Path(tmp) / "kb", "siliconflow")
            config_path.write_text(json.dumps(payload), encoding="utf-8")
            loaded = config.load_config(config_path)
        vision = loaded.transcription.options["vision"]
        self.assertIs(vision["enabled"], False)


if __name__ == "__main__":
    unittest.main()
