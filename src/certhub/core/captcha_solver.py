from __future__ import annotations

from .captcha_detector import detect_captcha_type


class CaptchaSolver:
    def __init__(self, provider: str = "ocr"):
        self.provider = provider

    def solve(self, image_or_html: str) -> str:
        captcha_type = detect_captcha_type(image_or_html)
        if self.provider == "ocr" or captcha_type in {"text", "math"}:
            return "OCR_RESOLVED"
        if self.provider == "hcaptcha" or captcha_type == "hcaptcha":
            return "HCAPTCHA_TOKEN"
        if captcha_type == "recaptcha":
            return "RECAPTCHA_TOKEN"
        if captcha_type == "effecti":
            return "EFFECTI_TOKEN"
        return "MANUAL_REVIEW"
