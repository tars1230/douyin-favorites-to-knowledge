from __future__ import annotations

import asyncio
import os
import platform
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


COLLECTION_PAGE_URL = "https://www.douyin.com/user/self?showTab=favorite_collection"
COLLECTION_API_URL = "https://www.douyin.com/aweme/v1/web/aweme/listcollection/"
LIKES_PAGE_URL = "https://www.douyin.com/user/self?showTab=like"
LIKES_API_URL = "https://www.douyin.com/aweme/v1/web/aweme/favorite/"
SOURCES = frozenset({"collection", "like"})
SESSION_COOKIE_NAMES = frozenset({"sessionid", "sessionid_ss", "sid_guard"})
AWEME_ID = re.compile(r"^[0-9]{6,30}$")


def default_profile_dir() -> Path:
    override = os.environ.get("DOUYIN_FAVORITES_PROFILE_DIR")
    if override:
        return Path(override).expanduser().resolve()
    system = platform.system()
    if system == "Darwin":
        root = Path.home() / "Library" / "Application Support"
    elif system == "Windows":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        root = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return root / "douyin-favorites-to-knowledge" / "browser-profile"


def _source_item(raw: dict[str, Any], observed_at: str, source: str = "collection") -> dict[str, Any] | None:
    aweme_id = str(raw.get("aweme_id") or "").strip()
    if not AWEME_ID.fullmatch(aweme_id):
        return None
    description = str(raw.get("description") or raw.get("desc") or "").strip()
    title = description.splitlines()[0].strip() if description else ""
    if not title:
        title = f"Douyin favorite {aweme_id}"
    item = {
        "aweme_id": aweme_id,
        "title": title,
        "author": str(raw.get("author") or "").strip(),
        "description": description,
        "transcript": "",
        "transcript_source": "none",
        "transcript_status": "not_requested",
        "tags": [],
        "observed_at": observed_at,
        "source": source,
        "play_url": str(raw.get("play_url") or "").strip(),
    }
    try:
        duration = float(raw.get("duration_seconds") or 0)
    except (TypeError, ValueError):
        duration = 0
    if duration > 0:
        item["duration_seconds"] = duration
    return item


class BrowserCollector:
    def __init__(self, profile_dir: Path | None = None, channel: str | None = None, source: str = "collection"):
        if source not in SOURCES:
            raise ValueError("source must be collection or like")
        self.profile_dir = (profile_dir or default_profile_dir()).expanduser().resolve()
        self.channel = channel
        self.source = source
        self._playwright = None
        self._context = None
        self._page = None

    async def open(self, *, headless: bool) -> None:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise ValueError(
                "browser support is not installed; install the package with its browser dependencies"
            ) from exc

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()
        channels = [self.channel] if self.channel else ["chrome", "msedge", None]
        for channel in channels:
            kwargs: dict[str, Any] = {
                "user_data_dir": str(self.profile_dir),
                "headless": headless,
                "viewport": {"width": 1280, "height": 800},
                "locale": "zh-CN",
            }
            if channel:
                kwargs["channel"] = channel
            try:
                self._context = await self._playwright.chromium.launch_persistent_context(**kwargs)
                break
            except Exception:
                self._context = None
        if self._context is None:
            await self._playwright.stop()
            self._playwright = None
            raise ValueError(
                "no supported browser is available; install Chrome, Edge, or Playwright Chromium"
            )
        self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()

    async def close(self) -> None:
        if self._context is not None:
            await self._context.close()
        if self._playwright is not None:
            await self._playwright.stop()
        self._context = None
        self._playwright = None
        self._page = None

    async def navigate(self) -> None:
        if self._page is None:
            raise ValueError("browser is not open")
        target = COLLECTION_PAGE_URL if self.source == "collection" else LIKES_PAGE_URL
        await self._page.goto(target, wait_until="domcontentloaded", timeout=45_000)

    async def authenticated(self) -> bool:
        if self._context is None:
            return False
        cookies = await self._context.cookies("https://www.douyin.com")
        return any(cookie.get("name") in SESSION_COOKIE_NAMES and cookie.get("value") for cookie in cookies)

    async def clear_session(self) -> None:
        if self._context is None:
            raise ValueError("browser is not open")
        await self._context.clear_cookies()
        for page in self._context.pages:
            try:
                await page.evaluate("localStorage.clear(); sessionStorage.clear()")
            except Exception:
                continue

    async def fetch_page(self, *, cursor: int, count: int) -> dict[str, Any]:
        if self._page is None:
            raise ValueError("browser is not open")
        result = await self._page.evaluate(
            r"""async ({apiUrl, cursor, count, source}) => {
                const params = new URLSearchParams({
                    device_platform: 'webapp',
                    aid: '6383',
                    channel: 'channel_pc_web',
                    cookie_enabled: String(navigator.cookieEnabled),
                    browser_language: navigator.language || 'zh-CN',
                    browser_platform: navigator.platform || '',
                    browser_name: 'Chrome',
                });
                let response;
                if (source === 'collection') {
                    const body = new URLSearchParams({count: String(count), cursor: String(cursor)});
                    response = await fetch(apiUrl + '?' + params.toString(), {
                        method: 'POST', credentials: 'include',
                        headers: {'Content-Type': 'application/x-www-form-urlencoded'}, body: body.toString(),
                    });
                } else {
                    const scripts = [...document.scripts].map(node => node.textContent || '').join('\n');
                    const match = scripts.match(/"sec_user_id"\s*:\s*"([^"]+)"/) || scripts.match(/sec_user_id=([^&"\s]+)/);
                    if (!match) return {ok: false, error: 'sec_user_id_missing'};
                    params.set('sec_user_id', match[1]);
                    params.set('max_cursor', String(cursor));
                    params.set('count', String(count));
                    response = await fetch(apiUrl + '?' + params.toString(), {credentials: 'include'});
                }
                if (!response.ok) {
                    return {ok: false, http_status: response.status};
                }
                const data = await response.json();
                return {
                    ok: data.status_code === 0,
                    status_code: data.status_code,
                    cursor: Number(source === 'collection' ? data.cursor || 0 : data.max_cursor || 0),
                    has_more: Boolean(data.has_more),
                    items: (data.aweme_list || []).map(item => ({
                        aweme_id: String(item.aweme_id || ''),
                        description: item.desc || '',
                        author: item.author ? item.author.nickname || '' : '',
                        play_url: item.video && item.video.play_addr && item.video.play_addr.url_list ? item.video.play_addr.url_list[0] || '' : '',
                        // Prefer original-sound style audio only. Commercial BGM music.play_url is often not speech.
                        audio_url: (function () {
                          const music = item.music || {};
                          const original = Boolean(music.is_original_sound || music.is_original || music.owner_handle || music.owner_nickname);
                          const list = (music.play_url && music.play_url.url_list) || (item.video && item.video.audio && item.video.audio.url_list) || [];
                          if (!original && !(item.video && item.video.audio && item.video.audio.url_list)) return '';
                          return list[0] || '';
                        })(),
                        duration_seconds: Number(item.video && item.video.duration || 0) / 1000,
                    })),
                };
            }""",
            {"apiUrl": self.source == "collection" and COLLECTION_API_URL or LIKES_API_URL, "cursor": cursor, "count": count, "source": self.source},
        )
        if not isinstance(result, dict):
            raise ValueError("Douyin returned an invalid collection response")
        return result


async def _login(*, timeout_seconds: int, channel: str | None, source: str = "collection") -> dict[str, Any]:
    collector = BrowserCollector(channel=channel, source=source)
    await collector.open(headless=False)
    try:
        await collector.navigate()
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        while asyncio.get_running_loop().time() < deadline:
            if await collector.authenticated():
                result = await collector.fetch_page(cursor=0, count=1)
                if result.get("ok"):
                    return {"status": "authenticated"}
            await asyncio.sleep(2)
        raise ValueError("login was not completed before the timeout")
    finally:
        await collector.close()


def login_browser(*, timeout_seconds: int = 300, channel: str | None = None, source: str = "collection") -> dict[str, Any]:
    if timeout_seconds < 10:
        raise ValueError("login timeout must be at least 10 seconds")
    try:
        return asyncio.run(_login(timeout_seconds=timeout_seconds, channel=channel, source=source))
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("browser login failed; close the login window and retry") from exc


async def _status(*, channel: str | None) -> dict[str, Any]:
    collector = BrowserCollector(channel=channel)
    await collector.open(headless=True)
    try:
        await collector.navigate()
        if not await collector.authenticated():
            return {"status": "login_required"}
        result = await collector.fetch_page(cursor=0, count=1)
        return {"status": "authenticated" if result.get("ok") else "login_required"}
    finally:
        await collector.close()


def browser_status(*, channel: str | None = None) -> dict[str, Any]:
    try:
        return asyncio.run(_status(channel=channel))
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("browser status check failed; close other sync processes and retry") from exc


async def _logout(*, channel: str | None) -> dict[str, Any]:
    collector = BrowserCollector(channel=channel)
    await collector.open(headless=True)
    try:
        await collector.clear_session()
        return {"status": "logged_out"}
    finally:
        await collector.close()


def logout_browser(*, channel: str | None = None) -> dict[str, Any]:
    try:
        return asyncio.run(_logout(channel=channel))
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("browser logout failed; close other sync processes and retry") from exc


async def _collect(
    *,
    max_items: int,
    interactive_login: bool,
    headed: bool,
    channel: str | None,
    source: str = "collection",
) -> list[dict[str, Any]]:
    collector = BrowserCollector(channel=channel, source=source)
    await collector.open(headless=not headed)
    try:
        await collector.navigate()
        if not await collector.authenticated():
            await collector.close()
            if not interactive_login:
                raise ValueError("Douyin login is required; run the login command first")
            await _login(timeout_seconds=300, channel=channel, source=source)
            collector = BrowserCollector(channel=channel, source=source)
            await collector.open(headless=not headed)
            await collector.navigate()

        observed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        collected: dict[str, dict[str, Any]] = {}
        cursor = 0
        seen_cursors: set[int] = set()
        while len(collected) < max_items:
            page_size = min(20, max_items - len(collected))
            result = await collector.fetch_page(cursor=cursor, count=page_size)
            if not result.get("ok"):
                raise ValueError("Douyin collection access failed; login again and retry")
            items = result.get("items")
            if not isinstance(items, list):
                raise ValueError("Douyin returned an invalid collection item list")
            for raw in items:
                if not isinstance(raw, dict):
                    continue
                item = _source_item(raw, observed_at, source)
                if item is not None:
                    collected[item["aweme_id"]] = item
                    if len(collected) >= max_items:
                        break
            if not result.get("has_more") or not items:
                break
            next_cursor = int(result.get("cursor") or 0)
            if next_cursor in seen_cursors or next_cursor == cursor:
                raise ValueError("Douyin collection pagination stopped advancing")
            seen_cursors.add(cursor)
            cursor = next_cursor
            await asyncio.sleep(0.5)
        return list(collected.values())
    finally:
        await collector.close()


def collect_browser_favorites(
    *,
    max_items: int = 200,
    interactive_login: bool = True,
    headed: bool = False,
    channel: str | None = None,
    source: str = "collection",
) -> list[dict[str, Any]]:
    if max_items < 1 or max_items > 10_000:
        raise ValueError("max_items must be between 1 and 10000")
    if source not in SOURCES:
        raise ValueError("source must be collection or like")
    try:
        return asyncio.run(
            _collect(
                max_items=max_items,
                interactive_login=interactive_login,
                headed=headed,
                channel=channel,
                source=source,
            )
        )
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("browser collection failed; close other sync processes and retry") from exc
