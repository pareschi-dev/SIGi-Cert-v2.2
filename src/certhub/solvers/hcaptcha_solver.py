from __future__ import annotations

class HCaptchaSolver:
    """Compatibility shim: CAPTCHA solving is deliberately human-only."""

    def __init__(self, api_key: str | None = None, timeout: int = 120, polling: int = 5):
        self.api_key = api_key
        self.timeout = timeout
        self.polling = polling

    async def resolver(self, sitekey: str, pageurl: str) -> str:
        raise RuntimeError("CAPTCHA deve ser resolvido por uma pessoa no portal oficial; nenhum token foi gerado.")
