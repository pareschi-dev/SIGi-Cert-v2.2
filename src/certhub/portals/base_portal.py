from __future__ import annotations

from abc import ABC, abstractmethod
from time import perf_counter

from certhub.core.browser_handler import BrowserSession
from certhub.core.captcha_detector import detect_captcha_type
from certhub.core.captcha_solver import CaptchaSolver
from certhub.core.models import EmissionRequest, EmissionResult
from certhub.core.validators import guess_document_type, validate_cnpj, validate_cpf


class BasePortal(ABC):
    name: str = "base"
    url: str = ""

    def __init__(self, request: EmissionRequest | None = None):
        self.request = request or EmissionRequest(portal=self.name, document="")
        self._started_at = perf_counter()
        self.browser_session = BrowserSession(headless=self.request.headless)

    def validate(self) -> None:
        doc_type = guess_document_type(self.request.document)
        if doc_type == "cpf" and not validate_cpf(self.request.document):
            raise ValueError("CPF inválido.")
        if doc_type == "cnpj" and not validate_cnpj(self.request.document):
            raise ValueError("CNPJ inválido.")

    @abstractmethod
    def emit(self) -> EmissionResult:
        """Run the portal flow and return the result."""

    def _result(self, success: bool, message: str, pdf_path: str | None = None, attempts: int = 1,
                captcha_type: str | None = None, captcha_method: str | None = None,
                pdf_hash: str | None = None) -> EmissionResult:
        elapsed = perf_counter() - getattr(self, "_started_at", perf_counter())
        return EmissionResult(
            portal=self.name,
            document=self.request.document,
            success=success,
            message=message,
            pdf_path=pdf_path,
            pdf_hash=pdf_hash,
            attempts=attempts,
            elapsed_seconds=round(elapsed, 2),
            captcha_type=captcha_type,
            captcha_method=captcha_method,
        )

    def unimplemented_result(self) -> EmissionResult:
        """Fail closed for legacy portal wrappers that do not fetch a real authority PDF."""
        return self._result(
            False,
            "Fluxo oficial deste portal ainda não está implementado; nenhum PDF foi emitido.",
            attempts=0,
        )

    def open_browser(self):
        if self.browser_session is None:
            self.browser_session = BrowserSession(headless=self.request.headless)
        if self.browser_session.page is None:
            self.browser_session.start()
        return self.browser_session.page

    def navigate(self, url: str | None = None, wait_until: str = "domcontentloaded"):
        target_url = url or self.url
        if not target_url:
            raise ValueError("URL do portal não configurada.")
        page = self.open_browser()
        page.goto(target_url, wait_until=wait_until)
        return page

    def detect_captcha(self, content: str | None = None):
        if content is None:
            if self.browser_session is None or self.browser_session.page is None:
                return "none"
            content = self.browser_session.page.content()
        return detect_captcha_type(content)

    def solve_captcha(self, content: str | None = None):
        source = content or (
            self.browser_session.page.content() if self.browser_session is not None and self.browser_session.page is not None else ""
        )
        captcha_type = self.detect_captcha(source)
        if captcha_type == "none":
            return None
        solver = CaptchaSolver(provider="ocr" if captcha_type in {"text", "math"} else "hcaptcha")
        return solver.solve(source)

    def wait_for_selector(self, selector: str, timeout: int = 30000):
        if self.browser_session is None or self.browser_session.page is None:
            self.open_browser()
        self.browser_session.page.wait_for_selector(selector, timeout=timeout)
        return self.browser_session.page.locator(selector)

    def fill_field(self, selector: str, value: str, timeout: int = 30000):
        locator = self.wait_for_selector(selector, timeout=timeout)
        locator.fill(value)
        return locator

    def click(self, selector: str, timeout: int = 30000):
        locator = self.wait_for_selector(selector, timeout=timeout)
        locator.click()
        return locator

    def close_browser(self):
        if self.browser_session is not None:
            self.browser_session.close()

    def __enter__(self):
        self._started_at = perf_counter()
        return self

    def __exit__(self, *args):
        self.close_browser()
        return False
