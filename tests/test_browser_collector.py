import asyncio
import os
import unittest
from unittest.mock import patch


from douyin_favorites_knowledge import browser_collector


class FakeCollector:
    pages = [
        {
            "ok": True,
            "cursor": 20,
            "has_more": True,
            "items": [
                {"aweme_id": "7000000000000000001", "description": "First\nMore", "author": "A"},
                {"aweme_id": "invalid", "description": "Ignored", "author": "B"},
            ],
        },
        {
            "ok": True,
            "cursor": 40,
            "has_more": False,
            "items": [
                {"aweme_id": "7000000000000000002", "description": "Second", "author": "C"}
            ],
        },
    ]

    def __init__(self, *args, **kwargs):
        self.fetches = 0
        self.closed = False

    async def open(self, *, headless):
        self.headless = headless

    async def close(self):
        self.closed = True

    async def navigate(self):
        return None

    async def authenticated(self):
        return True

    async def fetch_page(self, *, cursor, count):
        result = self.pages[self.fetches]
        self.fetches += 1
        return result


class LoggedOutCollector(FakeCollector):
    async def authenticated(self):
        return False


class FakePage:
    def __init__(self):
        self.script = ""
        self.args = None

    async def evaluate(self, script, args):
        self.script = script
        self.args = args
        return {"ok": True, "cursor": 0, "has_more": False, "items": []}


class BrowserCollectorTests(unittest.TestCase):
    def test_default_profile_override_is_not_returned_by_status(self):
        with patch.dict(os.environ, {"DOUYIN_FAVORITES_PROFILE_DIR": "./private-browser-state"}):
            path = browser_collector.default_profile_dir()
        self.assertEqual(path.name, "private-browser-state")

    def test_source_item_keeps_only_supported_metadata(self):
        item = browser_collector._source_item(
            {
                "aweme_id": "7000000000000000001",
                "description": "Title\nDescription",
                "author": "Creator",
                "sessionid": "must-not-leak",
                "statistics": {"secret": "must-not-leak"},
            },
            "2026-07-25T00:00:00+00:00",
        )
        self.assertEqual(
            set(item),
            {"aweme_id", "title", "author", "description", "transcript", "transcript_source", "transcript_status", "tags", "observed_at", "source", "play_url"},
        )
        self.assertNotIn("must-not-leak", str(item))

    def test_source_item_preserves_positive_duration_for_budgeting(self):
        item = browser_collector._source_item(
            {"aweme_id": "7000000000000000001", "desc": "title", "duration_seconds": 12.5},
            "2026-07-30T00:00:00+00:00",
        )
        self.assertEqual(item["duration_seconds"], 12.5)

    def test_collection_paginates_and_filters_invalid_ids(self):
        with patch.object(browser_collector, "BrowserCollector", FakeCollector):
            items = asyncio.run(
                browser_collector._collect(
                    max_items=10,
                    interactive_login=False,
            headed=False,
            channel=None,
            source="collection",
        )
            )
        self.assertEqual([item["aweme_id"] for item in items], [
            "7000000000000000001",
            "7000000000000000002",
        ])
        self.assertEqual(items[0]["title"], "First")

    def test_likes_use_the_separate_endpoint_and_sec_user_id(self):
        collector = browser_collector.BrowserCollector(source="like")
        page = FakePage()
        collector._page = page
        result = asyncio.run(collector.fetch_page(cursor=20, count=10))
        self.assertTrue(result["ok"])
        self.assertEqual(page.args["apiUrl"], browser_collector.LIKES_API_URL)
        self.assertEqual(page.args["source"], "like")
        self.assertIn("sec_user_id", page.script)
        self.assertIn('([^\"]+)', page.script)
        self.assertNotIn('([^"\\\\]+)', page.script)
        self.assertIn(".join('\\n')", page.script)

    def test_invalid_item_limit_is_rejected_before_browser_start(self):
        with self.assertRaisesRegex(ValueError, "between 1 and 10000"):
            browser_collector.collect_browser_favorites(max_items=0)

    def test_expired_login_is_not_treated_as_empty_collection(self):
        with patch.object(browser_collector, "BrowserCollector", LoggedOutCollector):
            with self.assertRaisesRegex(ValueError, "login is required"):
                asyncio.run(
                    browser_collector._collect(
                        max_items=10,
                        interactive_login=False,
                headed=False,
                channel=None,
                source="collection",
            )
                )

    def test_browser_errors_are_replaced_with_stable_message(self):
        async def fail(**kwargs):
            raise RuntimeError("private profile path and session detail")

        with patch.object(browser_collector, "_status", fail):
            with self.assertRaisesRegex(ValueError, "browser status check failed") as raised:
                browser_collector.browser_status()
        self.assertNotIn("private profile", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
