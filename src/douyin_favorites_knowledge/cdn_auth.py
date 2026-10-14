"""In-memory Douyin CDN cookies for the current sync. Never write or log them."""
from __future__ import annotations

import urllib.request
from urllib.parse import urlparse

_ALLOWED_SUFFIXES = (
    "douyin.com",
    "douyinvod.com",
    "douyinpic.com",
    "byteimg.com",
    "bytecdn.cn",
    "ibytedtos.com",
    "snssdk.com",
    "amemv.com",
)
_cookies: list[dict[str, str]] = []


def _host_allowed(host: str) -> bool:
    host = host.lower().rstrip(".")
    return any(host == suffix or host.endswith("." + suffix) for suffix in _ALLOWED_SUFFIXES)


def remember_cdn_cookies(cookies: list[dict]) -> None:
    """Keep only CDN-relevant cookies. Other sites never receive them."""
    kept: list[dict[str, str]] = []
    for cookie in cookies or []:
        if not isinstance(cookie, dict):
            continue
        name = str(cookie.get("name") or "").strip()
        value = str(cookie.get("value") or "")
        domain = str(cookie.get("domain") or "").lstrip(".").lower()
        if not name or not value or not _host_allowed(domain):
            continue
        kept.append({"name": name, "value": value, "domain": domain})
    global _cookies
    _cookies = kept


def clear_cdn_cookies() -> None:
    global _cookies
    _cookies = []


def cookie_header_for(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if not _host_allowed(host):
        return ""
    parts = []
    for cookie in _cookies:
        domain = cookie["domain"]
        if host == domain or host.endswith("." + domain):
            parts.append(f"{cookie['name']}={cookie['value']}")
    return "; ".join(parts)


def download_request(url: str) -> urllib.request.Request:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.douyin.com/",
        "Origin": "https://www.douyin.com",
        "Accept": "*/*",
    }
    cookie = cookie_header_for(url)
    if cookie:
        headers["Cookie"] = cookie
    return urllib.request.Request(url, headers=headers)
