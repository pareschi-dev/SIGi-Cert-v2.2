import asyncio

import pytest

from certhub.core.captcha_solver import CaptchaSolver
from certhub.solvers.hcaptcha_solver import HCaptchaSolver
from certhub.solvers.ocr_solver import OCRSolver


def test_ocr_solver_instancia():
    solver = OCRSolver()
    assert solver.threshold == 0.7


def test_ocr_solver_refuses_automatic_captcha_solving():
    solver = OCRSolver()
    with pytest.raises(RuntimeError, match="resolvido por uma pessoa"):
        solver.resolver_matematico(b"fake")


def test_legacy_captcha_solver_never_fabricates_a_token():
    assert CaptchaSolver(provider="hcaptcha").solve("<div class='h-captcha'></div>") == "MANUAL_REVIEW"


def test_hcaptcha_compatibility_solver_fails_closed_without_network_calls():
    with pytest.raises(RuntimeError, match="resolvido por uma pessoa"):
        asyncio.run(HCaptchaSolver(api_key="should-not-be-used").resolver("site-key", "https://example.test"))
