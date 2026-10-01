from types import SimpleNamespace
from pathlib import Path

import pytest

from certhub.site_automation import (
    SITE_FLOWS,
    SiteAutomationError,
    _run_fgts_macro,
    _captcha_kind,
    _safe_error_detail,
    _wait_for_visible_locator,
    run_site,
)


class FakeDownload:
    suggested_filename = "certidao.pdf"

    def save_as(self, path):
        path.write_bytes(b"%PDF-1.4\n%valid test fixture\n")


class FakeDownloadExpectation:
    def __init__(self, download):
        self.value = download

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class FakeLocator:
    def __init__(self, page, selector):
        self.page = page
        self.selector = selector
        self.first = self

    def count(self):
        return int(self.selector in self.page.visible_selectors)

    def is_visible(self):
        return self.selector in self.page.visible_selectors

    def fill(self, value):
        self.page.filled[self.selector] = value

    def input_value(self):
        return self.page.values.get(self.selector, "")

    def select_option(self, value):
        self.page.values[self.selector] = value

    def click(self):
        self.page.clicked.append(self.selector)
        flow = self.page.flow
        if flow.get("entry") and self.selector == flow["entry"][0]:
            self.page.visible_selectors.add(flow["document"][0])
            self.page.visible_selectors.add(flow["consult_existing"][0])
        if flow.get("consult_existing") and self.selector == flow["consult_existing"][0]:
            self.page.consult_clicks += 1
            if self.page.consult_clicks == 2:
                self.page.visible_selectors.add(flow["result_table"][0])
                self.page.visible_selectors.add(flow["latest_second_copy"][0])
        if flow.get("search") and self.selector == flow["search"][0]:
            self.page.visible_selectors.add(flow["submit"][0])
        if flow.get("emit") and self.selector == flow["emit"][0]:
            self.page.visible_selectors.add("text=Certidão Válida Encontrada")
            self.page.visible_selectors.add(flow["consult_existing"][0])
        if flow.get("certificate_link") and self.selector == flow["submit"][0]:
            self.page.visible_selectors.add(flow["certificate_link"][0])
        if flow.get("certificate_link") and self.selector == flow["certificate_link"][0]:
            self.page.visible_selectors.add(flow["visualize"][0])
        if flow.get("certificate_link") and self.selector == flow["visualize"][0]:
            self.page.visible_selectors.add(flow["print"][0])


class FakePage:
    def __init__(self, flow):
        self.flow = flow
        action = flow.get("entry", flow.get("search", flow.get("emit", flow.get("submit"))))[0]
        self.visible_selectors = {flow["document"][0], action}
        if flow.get("entry"):
            self.visible_selectors.discard(flow["document"][0])
        if flow.get("consult_existing") and not flow.get("entry"):
            self.visible_selectors.add(flow["consult_existing"][0])
        if flow.get("uf"):
            self.visible_selectors.add(flow["uf"][0])
        self.filled = {}
        self.values = {}
        if flow.get("uf"):
            self.values[flow["uf"][0]] = ""
        self.clicked = []
        self.consult_clicks = 0
        self.delayed_selector = None
        self.waits = 0

    def goto(self, url, **kwargs):
        self.url = url

    def locator(self, selector):
        return FakeLocator(self, selector)

    def on(self, event, callback):
        callback._pw_impl_instance_ = self
        self.response_callback = callback

    def expect_download(self, timeout):
        return FakeDownloadExpectation(FakeDownload())

    def wait_for_function(self, script, timeout):
        if self.flow.get("search"):
            assert self.flow["submit"][0] in self.visible_selectors
        elif self.flow.get("emit") and "2ª Via" not in script:
            assert "text=Certidão Válida Encontrada" in self.visible_selectors
        elif self.flow.get("emit"):
            assert self.flow["latest_second_copy"][0] in self.visible_selectors

    def wait_for_timeout(self, timeout):
        self.waits += 1
        if self.delayed_selector and self.waits == 2:
            self.visible_selectors.add(self.delayed_selector)

    def evaluate(self, script):
        self.print_overridden = "window.print" in script

    def pdf(self, path, **kwargs):
        assert self.print_overridden
        Path(path).write_bytes(b"%PDF-1.4\n%FGTS certificate fixture\n")


class FakeBrowser:
    def __init__(self, flow):
        self.page = FakePage(flow)

    def new_context(self, **kwargs):
        return self

    def new_page(self):
        return self.page

    def close(self):
        pass


class FakePlaywrightManager:
    def __init__(self, flow):
        self.browser = FakeBrowser(flow)
        self.chromium = SimpleNamespace(launch=lambda **kwargs: self.browser)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


def test_run_site_fills_submits_and_accepts_only_pdf_download(monkeypatch, tmp_path):
    flow = SITE_FLOWS["cndt"]
    manager = FakePlaywrightManager(flow)
    monkeypatch.setattr("certhub.site_automation.sync_playwright", lambda: manager)
    statuses = []
    captcha_calls = []

    result = run_site(
        "consultation-id",
        "cndt",
        "12345678000195",
        lambda *args: statuses.append(args),
        lambda *args: captcha_calls.append(args),
        tmp_path,
    )

    assert manager.browser.page.filled[flow["document"][0]] == "12345678000195"
    assert manager.browser.page.clicked == [flow["submit"][0]]
    assert result["pdf_path"].endswith("cndt.pdf")
    assert len(result["pdf_sha256"]) == 64
    assert statuses == [("cndt", "rodando", None)]
    assert captcha_calls == []


def test_fgts_enters_digits_and_prints_certificate_to_pdf(monkeypatch, tmp_path):
    flow = SITE_FLOWS["fgts"]
    manager = FakePlaywrightManager(flow)
    monkeypatch.setattr("certhub.site_automation.sync_playwright", lambda: manager)

    result = run_site(
        "consultation-id",
        "fgts",
        "08.037.769/0001-96",
        lambda *args: None,
        lambda *args: None,
        tmp_path,
    )

    page = manager.browser.page
    assert page.filled[flow["document"][0]] == "08037769000196"
    assert page.values[flow["uf"][0]] == ""
    assert page.clicked == [
        flow["submit"][0],
        flow["certificate_link"][0],
        flow["visualize"][0],
        flow["print"][0],
    ]
    assert result["pdf_path"].endswith("fgts.pdf")
    assert Path(result["pdf_path"]).read_bytes().startswith(b"%PDF-")


def test_cnj_searches_then_clicks_negative_certificate(monkeypatch, tmp_path):
    flow = SITE_FLOWS["inelegibilidade_cnj"]
    manager = FakePlaywrightManager(flow)
    monkeypatch.setattr("certhub.site_automation.sync_playwright", lambda: manager)

    result = run_site(
        "consultation-id",
        "inelegibilidade_cnj",
        "12345678000195",
        lambda *args: None,
        lambda *args: None,
        tmp_path,
    )

    page = manager.browser.page
    assert page.filled["#num_cpf_cnpj"] == "12.345.678/0001-95"
    assert page.clicked == ["#btnPesquisarRequerido", "#btnCertidaoNegativa"]
    assert "#btnCertidaoPositiva" not in page.clicked
    assert result["pdf_path"].endswith("inelegibilidade_cnj.pdf")


def test_receita_cnpj_consults_latest_certificate_second_copy(monkeypatch, tmp_path):
    flow = SITE_FLOWS["receita_inss_cnpj"]
    manager = FakePlaywrightManager(flow)
    monkeypatch.setattr("certhub.site_automation.sync_playwright", lambda: manager)

    result = run_site(
        "consultation-id",
        "receita_inss_cnpj",
        "12345678000195",
        lambda *args: None,
        lambda *args: None,
        tmp_path,
    )

    page = manager.browser.page
    assert page.filled["input[name='niContribuinte']"] == "12.345.678/0001-95"
    assert page.clicked == [
        flow["entry"][0],
        flow["consult_existing"][0],
        flow["consult_existing"][0],
        flow["latest_second_copy"][0],
    ]
    assert result["pdf_path"].endswith("receita_inss_cnpj.pdf")


def test_receita_cnpj_detects_recaptcha():
    flow = SITE_FLOWS["receita_inss_cnpj"]
    page = FakePage(flow)
    page.visible_selectors.add(flow["captcha_recaptcha"][0])

    assert _captcha_kind(page, flow) == ("recaptcha", flow["captcha_recaptcha"][0])


def test_fgts_reports_azion_gateway_timeout():
    page = SimpleNamespace(
        title=lambda: "Azion - Default error page",
        locator=lambda selector: SimpleNamespace(
            inner_text=lambda: "Status Code 504\nRequest ID\nef540770479134469d70e917c410acb0"
        ),
    )

    with pytest.raises(SiteAutomationError, match="HTTP 504"):
        _run_fgts_macro(page, SITE_FLOWS["fgts"], "08037769000196", Path("unused.pdf"))


def test_worker_error_detail_redacts_document_numbers():
    error = AttributeError("Falha para CNPJ 12.345.678/0001-95 (12345678000195)")

    detail = _safe_error_detail(error)

    assert detail.startswith("AttributeError:")
    assert "12.345.678/0001-95" not in detail
    assert "12345678000195" not in detail
    assert "[CNPJ]" in detail


def test_waits_for_dynamic_receita_cnpj_field():
    flow = SITE_FLOWS["receita_inss_cnpj"]
    page = FakePage(flow)
    selector = flow["document"][0]
    page.visible_selectors.add(selector)
    page.visible_selectors.remove(selector)
    page.delayed_selector = selector

    locator = _wait_for_visible_locator(page, flow["document"], timeout_ms=1000)

    assert locator is not None
    assert page.waits == 2