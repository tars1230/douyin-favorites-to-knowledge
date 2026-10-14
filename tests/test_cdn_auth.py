import unittest

from douyin_favorites_knowledge.cdn_auth import (
    clear_cdn_cookies,
    cookie_header_for,
    download_request,
    remember_cdn_cookies,
)


class CdnAuthTests(unittest.TestCase):
    def tearDown(self):
        clear_cdn_cookies()

    def test_cookie_is_not_sent_outside_its_site(self):
        remember_cdn_cookies(
            [
                {"name": "sessionid", "value": "secret-cookie", "domain": ".douyin.com"},
                {"name": "ttwid", "value": "cdn-secret", "domain": ".douyinvod.com"},
                {"name": "other", "value": "nope", "domain": "evil.example"},
            ]
        )
        self.assertEqual(cookie_header_for("https://v3-web.douyinvod.com/video.mp4"), "ttwid=cdn-secret")
        self.assertEqual(
            cookie_header_for("https://www.douyin.com/aweme/v1/play/"),
            "sessionid=secret-cookie",
        )
        foreign = download_request("https://api.siliconflow.cn/v1/audio/transcriptions")
        self.assertNotIn("cookie", {key.lower() for key, _value in foreign.header_items()})


if __name__ == "__main__":
    unittest.main()
