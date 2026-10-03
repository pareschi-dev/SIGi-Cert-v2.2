from __future__ import annotations

from .captcha_detector import detect_captcha_type


class CaptchaSolver:
    def __init__(self, provider: str = "ocr"):
        self.provider = provider

    def solve(self, image_or_html: str) -> str:
        # CAPTCHA challenges must be completed by a person; never fabricate a token.
        detect_captcha_type(image_or_html)
        return "MANUAL_REVIEW"
