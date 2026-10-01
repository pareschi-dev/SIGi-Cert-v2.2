from __future__ import annotations

import random
from typing import Sequence


class ProxyManager:
    """Rotates proxies and exposes a current proxy for browser sessions."""

    def __init__(self, proxies: Sequence[str] | None = None, enabled: bool = False):
        self.enabled = enabled
        self.proxies = list(proxies or [])
        self._index = 0

    def add_proxy(self, proxy: str) -> None:
        self.proxies.append(proxy)

    def next_proxy(self) -> str | None:
        if not self.enabled or not self.proxies:
            return None
        if len(self.proxies) == 1:
            return self.proxies[0]
        proxy = self.proxies[self._index]
        self._index = (self._index + 1) % len(self.proxies)
        return proxy

    def random_proxy(self) -> str | None:
        if not self.enabled or not self.proxies:
            return None
        return random.choice(self.proxies)

    @property
    def current(self) -> str | None:
        if not self.enabled or not self.proxies:
            return None
        return self.proxies[self._index]
