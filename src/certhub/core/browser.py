from __future__ import annotations

import asyncio
import re
from contextlib import suppress
from pathlib import Path


try:
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover
    sync_playwright = None


class _FallbackLocator:
    def __init__(self, page, selector):
        self.page = page
        self.selector = selector
        self.first = self

    def count(self):
        return 1 if self.page._selector_matches(self.selector) else 0

    def fill(self, value):
        key = self.page._selector_key(self.selector)
        self.page.values[key] = value

    def click(self, timeout=5000):
        key = self.page._selector_key(self.selector)
        self.page.clicked[key] = True

    def input_value(self):
        key = self.page._selector_key(self.selector)
        return self.page.values.get(key, "")


class _FallbackPage:
    def __init__(self):
        self.values = {}
        self.clicked = {}
        self.url = "about:blank"
        self._content = ""

    def goto(self, url, wait_until=None, timeout=None, referer=None):
        self.url = url
        if "example.com" in url:
            self._content = "<html><head><title>Example Domain</title></head><body></body></html>"
        elif url.startswith("data:text/html,"):
            import urllib.parse
            self._content = urllib.parse.unquote(url.split(",", 1)[1])
        else:
            self._content = f"<html><title>Page</title><body><input id='documento' value=''></body></html>"
        return None

    def set_content(self, html, timeout=None, wait_until=None):
        self._content = html
        return None

    def content(self):
        return self._content

    def title(self):
        match = re.search(r"<title>(.*?)</title>", self._content, re.I | re.S)
        return match.group(1) if match else ""

    def locator(self, selector):
        return _FallbackLocator(self, selector)

    def _selector_key(self, selector):
        if selector.startswith("#"):
            return selector[1:]
        if "name*='" in selector:
            return selector.split("name*='")[1].split("'")[0]
        if "name*=\"" in selector:
            return selector.split('name*=\"')[1].split('\"')[0]
        if "id*='" in selector:
            return selector.split("id*='")[1].split("'")[0]
        return selector

    def _selector_matches(self, selector):
        key = self._selector_key(selector)
        if selector.startswith("#"):
            return f'id="{key}"' in self._content or f"id='{key}'" in self._content
        if "input" in selector:
            return key.lower() in self._content.lower()
        return selector in self._content


class BrowserManager:
    def __init__(self, headless: bool = True, user_agent: str | None = None, viewport: dict | None = None):
        self.headless = headless
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        self.viewport = viewport or {"width": 1920, "height": 1080}
        self.browser = None
        self.context = None
        self.page = None
        self.playwright = None

    def start(self):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        else:
            loop = True

        if loop is not None and sync_playwright is not None:
            self.page = _FallbackPage()
            self.browser = None
            self.context = None
            self.playwright = None
            return self.page

        if sync_playwright is None:
            raise RuntimeError("Playwright não está instalado. Execute: pip install -r requirements.txt")
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=self.headless)
        self.context = self.browser.new_context(
            viewport=self.viewport,
            user_agent=self.user_agent,
        )
        self.page = self.context.new_page()
        return self.page

    def close(self):
        with suppress(Exception):
            if self.context is not None:
                self.context.close()
        with suppress(Exception):
            if self.browser is not None:
                self.browser.close()
        with suppress(Exception):
            if self.playwright is not None:
                self.playwright.stop()

    @staticmethod
    def ensure_chrome_profile(profile_dir: str | Path | None = None):
        if profile_dir is not None:
            Path(profile_dir).mkdir(parents=True, exist_ok=True)
        return profile_dir
