from __future__ import annotations

import re
from typing import Literal

CaptchaType = Literal["none", "text", "math", "hcaptcha", "recaptcha", "effecti", "comprasnet"]


def detect_captcha_type(page_html: str | None = None, element_attrs: dict | None = None) -> CaptchaType:
    source = (page_html or "").lower()
    attrs = (element_attrs or {}).get("src", "") if isinstance(element_attrs, dict) else ""

    if "h-captcha" in source or "hcaptcha" in source or "hcaptcha" in attrs:
        return "hcaptcha"
    if "g-recaptcha" in source or "recaptcha" in source:
        return "recaptcha"
    if "effecti" in source or "comprasnet" in source:
        return "effecti"
    if re.search(r"(captcha|securimage|imagem.*captcha)", source):
        return "text"
    if re.search(r"(quanto\s+e|calcule|resultado\s+de|somar|subtrair)", source):
        return "math"
    return "none"
