import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".md", ".py", ".json", ".yml", ".yaml", ".toml", ".txt"}


class RepositoryTests(unittest.TestCase):
    def test_version_is_current_release(self):
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('version = "1.2.0"', text)
        package = (ROOT / "src" / "douyin_favorites_knowledge" / "__init__.py").read_text(encoding="utf-8")
        self.assertIn('__version__ = "1.2.0"', package)

    def test_skill_frontmatter(self):
        text = (ROOT / "skill" / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        header = text.split("---", 2)[1]
        self.assertRegex(header, r"(?m)^name:\s+douyin-favorites-to-knowledge\s*$")
        self.assertRegex(header, r"(?m)^description:\s+.+$")

    def test_no_private_paths_or_live_secrets(self):
        patterns = {
            "private path": re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+/"),
            "GitHub token": re.compile(r"gh[oprsu]_[A-Za-z0-9]{20,}"),
            "OpenAI-style key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
            "Apify token": re.compile(r"apify_api_[A-Za-z0-9_-]{20,}"),
            "Feishu user id": re.compile(r"ou_[A-Za-z0-9]{12,}"),
        }
        findings = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts or path.suffix not in TEXT_SUFFIXES:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for label, pattern in patterns.items():
                if pattern.search(text):
                    findings.append(f"{path.relative_to(ROOT)}: {label}")
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
