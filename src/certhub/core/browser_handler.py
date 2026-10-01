from __future__ import annotations

from certhub.core.browser import BrowserManager


class BrowserSession(BrowserManager):
    """Compatibility wrapper for browser automation sessions."""

    def close(self):
        super().close()
        self.context = None
        self.browser = None
        self.playwright = None
        self.page = None


__all__ = ["BrowserManager", "BrowserSession"]
