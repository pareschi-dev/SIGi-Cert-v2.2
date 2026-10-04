import base64
import json
from types import SimpleNamespace
from pathlib import Path
import threading

import pytest

from certhub.site_automation import (
    PlaywrightTimeoutError,
    SITE_FLOWS,
    SiteAutomationError,
    _run_fgts_macro,
    _captcha_kind,
    _safe_error_detail,
    _run_cartao_cnpj_macro,
    _run_cgu_macro,
    _run_cndt_macro,
    _run_receita_cpf_macro,
    _run_sicaf_token_flow,
    _run_simples_nacional_macro,
    _run_tcu_macro,
    _download_from_click,
    _visible_locator,
    _visible_browser_slot_kind,
    _acquire_visible_browser_slot,
    _release_visible_browser_slot,
    _reuse_visible_page,
    _wait_for_receita_state,
    _wait_for_visible_locator,
    run_site,
)


class FakeDownload:
    suggested_filename = "certidao.pdf"

    def save_as(self, path):
        path.write_bytes(b"%PDF-1.4\n%valid test fixture\n")


class FakeResponse:
    def __init__(self, body, content_type="application/json"):
        self.headers = {"content-type": content_type}
        self._body = body

    def body(self):
        return self._body


class FakeDownloadExpectation:
    def __init__(self, download, fail=False):
        self.value = download
        self.fail = fail

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.fail and exc_type is None:
            raise PlaywrightTimeoutError("simulated no-download response")
        return False


class FakeLocator:
    def __init__(self, page, selector):
        self.page = page
        self.selector = selector
        self.first = self

    def count(self):
        return int(
            self.selector in self.page.visible_selectors
            or self.selector in self.page.hidden_selectors
        )

    def nth(self, index):
        return self

    def is_visible(self):
        return self.selector in self.page.visible_selectors

    def fill(self, value):
        self.page.filled[self.selector] = value

    def input_value(self):
        return self.page.values.get(self.selector, "")

    def evaluate(self, _script):
        return self.page.values.get(self.selector, "")

    def select_option(self, value=None, label=None):
        self.page.values[self.selector] = label or value

    def check(self):
        self.page.values[self.selector] = "checked"

    def inner_text(self):
        if self.page.flow.get("fake_query_error") and self.selector in self.page.flow.get("query_error", []):
            return "Não foi possível concluir a ação. Erro 023 - tente novamente em alguns minutos."
        return "SICAF certidão CNPJ 12.345.678/0001-95"

    def click(self):
        self.page.clicked.append(self.selector)
        flow = self.page.flow
        if flow.get("fake_response") and self.page.response_callback:
            self.page.response_callback(flow["fake_response"])
        if flow.get("consult") and self.selector == flow["consult"][0]:
            self.page.documents_at_consult.append(self.page.filled.get(flow["document"][0]))
        if flow.get("entry") and self.selector == flow["entry"][0]:
            self.page.visible_selectors.add(flow["document"][0])
            if flow.get("submit"):
                self.page.visible_selectors.add(flow["submit"][0])
            if flow.get("consult_existing"):
                self.page.visible_selectors.add(flow["consult_existing"][0])
        if flow.get("consult_existing") and self.selector == flow["consult_existing"][0]:
            self.page.consult_clicks += 1
            if self.page.consult_clicks == 1 and flow.get("initial_data_notice"):
                self.page.visible_selectors.add(flow["initial_data_notice"][0])
            if self.page.consult_clicks == 2:
                self.page.visible_selectors.add(flow["result_table"][0])
                self.page.visible_selectors.add(flow["latest_second_copy"][0])
        if flow.get("consult") and self.selector == flow["consult"][0]:
            self.page.consult_clicks += 1
            if self.page.consult_clicks == 1:
                self.page.query_attempts += 1
                if flow.get("fake_query_form", True):
                    self.page.url = "https://portal.test/servico/certidoes/#/home/cnpj/consultar"
            elif self.page.consult_clicks == 2:
                if flow.get("fake_query_results", True):
                    self.page.url = "https://portal.test/servico/certidoes/#/home/cnpj/consultar/resultado"
                    self.page.visible_selectors.add(flow["latest_second_copy"][0])
            should_fail_query = flow.get("fake_query_error") and (
                self.page.query_attempts <= flow.get("fake_query_error_attempts", 999)
            )
            if should_fail_query:
                self.page.visible_selectors.update(flow["query_error"])
            else:
                self.page.visible_selectors.difference_update(flow.get("query_error", []))
        if flow.get("search") and self.selector == flow["search"][0]:
            self.page.visible_selectors.add(flow["submit"][0])
        if flow.get("emit") and self.selector == flow["emit"][0]:
            if flow.get("fake_valid_certificate", True):
                self.page.visible_selectors.update(flow["valid_certificate_notice"])
                self.page.visible_selectors.update(flow["emit_new"])
            else:
                self.page.visible_selectors.update(flow["result_notice"])
                self.page.visible_selectors.update(flow["result_download"])
        if flow.get("emit_new") and self.selector == flow["emit_new"][0]:
            self.page.visible_selectors.update(flow["result_notice"])
            self.page.visible_selectors.update(flow["result_download"])
        if flow.get("certificate_link") and self.selector == flow["submit"][0]:
            self.page.visible_selectors.add(flow["certificate_link"][0])
        if flow.get("certificate_link") and self.selector == flow["certificate_link"][0]:
            self.page.visible_selectors.add(flow["visualize"][0])
        if flow.get("certificate_link") and self.selector == flow["visualize"][0]:
            self.page.visible_selectors.add(flow["print"][0])
        if flow.get("submit") and self.selector in flow["submit"]:
            self.page.submit_clicks += 1
            if flow.get("captcha_after_first_submit") and self.page.submit_clicks == 1:
                self.page.visible_selectors.update(flow["captcha_image"] + flow["captcha_input"])
            if flow.get("download_button"):
                self.page.visible_selectors.add(flow["download_button"][0])
            if flow.get("result_notice") and not flow.get("fake_hcaptcha_after_submit") and not flow.get("fake_hidden_hcaptcha_after_submit"):
                self.page.visible_selectors.add(flow["result_notice"][0])
            if flow.get("fake_hcaptcha_after_submit"):
                self.page.delayed_selector = flow["captcha_hcaptcha"][0]
            if flow.get("result_url"):
                self.page.url = f"https://portal.test{flow['result_url']}"
                if flow.get("certificate_button"):
                    self.page.visible_selectors.add(flow["certificate_button"][0])
            if flow.get("generate_pdf"):
                self.page.visible_selectors.add(flow["generate_pdf"][0])
        if flow.get("submit") and self.selector == flow["submit"][0] and flow.get("url_on_submit"):
            self.page.url = flow["url_on_submit"].pop(0)
            if "/resultado" in self.page.url and flow.get("latest_second_copy"):
                self.page.visible_selectors.add(flow["latest_second_copy"][0])


class FakePage:
    def __init__(self, flow):
        self.flow = flow
        self.url = "https://portal.test/"
        action_selectors = flow.get("entry") or flow.get("search") or flow.get("emit") or flow.get("submit") or []
        self.visible_selectors = set()
        self.hidden_selectors = set()
        if flow.get("document"):
            self.visible_selectors.add(flow["document"][0])
        if action_selectors:
            self.visible_selectors.add(action_selectors[0])
        if flow.get("entry"):
            self.visible_selectors.discard(flow["document"][0])
        if flow.get("consult_existing") and not flow.get("entry"):
            self.visible_selectors.add(flow["consult_existing"][0])
        if flow.get("consult"):
            self.visible_selectors.add(flow["consult"][0])
        if flow.get("uf"):
            self.visible_selectors.add(flow["uf"][0])
        if flow.get("document_type"):
            self.visible_selectors.add(flow["document_type"][0])
        self.filled = {}
        self.values = {}
        if flow.get("uf"):
            self.values[flow["uf"][0]] = ""
        if flow.get("document_type"):
            self.values[flow["document_type"][0]] = "CPF"
        self.clicked = []
        self.documents_at_consult = []
        self.consult_clicks = 0
        self.query_attempts = 0
        self.goto_calls = 0
        self.submit_clicks = 0
        self.delayed_selector = None
        self.waits = 0

    def goto(self, url, **kwargs):
        self.url = url
        self.goto_calls += 1
        if self.goto_calls > 1 and self.flow.get("consult"):
            self.visible_selectors = {self.flow["document"][0], self.flow["consult"][0]}
            self.consult_clicks = 0

    def locator(self, selector):
        return FakeLocator(self, selector)

    def on(self, event, callback):
        callback._pw_impl_instance_ = self
        if event == "download":
            self.download_callback = callback
        else:
            self.response_callback = callback

    def remove_listener(self, event, callback):
        if event == "response" and getattr(self, "response_callback", None) is callback:
            self.response_callback = None

    def expect_download(self, timeout):
        failures = self.flow.get("download_failures", 0)
        if failures:
            self.flow["download_failures"] = failures - 1
            return FakeDownloadExpectation(FakeDownload(), fail=True)
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
        if self.flow.get("print"):
            assert self.print_overridden
        Path(path).write_bytes(b"%PDF-1.4\n%FGTS certificate fixture\n")

    def close(self):
        self.closed = True

    def is_closed(self):
        return getattr(self, "closed", False)

    def bring_to_front(self):
        self.brought_to_front = True


class FakeBrowser:
    def __init__(self, flow):
        self.page = FakePage(flow)
        self.contexts = [self]
        self.pages = [self.page]
        self.new_page_calls = 0

    def new_context(self, **kwargs):
        return self

    def new_page(self):
        self.new_page_calls += 1
        return self.page

    def close(self):
        self.closed = True


class FakePlaywrightManager:
    def __init__(self, flow):
        self.browser = FakeBrowser(flow)
        self.launch_calls = []
        self.cdp_urls = []
        self.chromium = SimpleNamespace(
            launch=self._launch,
            connect_over_cdp=self._connect_over_cdp,
        )

    def _launch(self, **kwargs):
        self.launch_calls.append(kwargs)
        return self.browser

    def _connect_over_cdp(self, url):
        self.cdp_urls.append(url)
        return self.browser

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

    def operator_submits_in_portal(*args):
        captcha_calls.append(args)
        return "concluido"

    def save_manual_cndt(*args):
        statuses.append(args)
        if args[0] == "cndt" and args[1] == "rodando" and args[2]:
            (tmp_path / "cndt.pdf").write_bytes(b"%PDF-1.4\nmanual test\n")

    result = run_site(
        "consultation-id",
        "cndt",
        "12345678000195",
        save_manual_cndt,
        operator_submits_in_portal,
        tmp_path,
    )

    assert manager.browser.page.filled[flow["document"][0]] == "12.345.678/0001-95"
    assert manager.browser.page.url == flow["url"]
    assert manager.browser.page.clicked == []
    assert result["pdf_path"].endswith("cndt.pdf")
    assert len(result["pdf_sha256"]) == 64
    assert statuses[0:2] == [("cndt", "rodando", None), ("cndt", "aguardando_captcha", None)]
    assert statuses[-1][0:2] == ("cndt", "rodando")
    assert "cndt.pdf" in statuses[-1][2]
    assert captcha_calls == [("cndt", "imagem", None, None)]


def test_fgts_enters_digits_and_prints_certificate_to_pdf(monkeypatch, tmp_path):
    flow = SITE_FLOWS["fgts"]
    manager = FakePlaywrightManager(flow)
    monkeypatch.setattr("certhub.site_automation.sync_playwright", lambda: manager)
    captcha_calls = []

    result = run_site(
        "consultation-id",
        "fgts",
        "08.037.769/0001-96",
        lambda *args: None,
        lambda *args: captcha_calls.append(args),
        tmp_path,
    )

    page = manager.browser.page
    assert page.filled[flow["document"][0]] == "08037769000196"
    assert page.values[flow["document_type"][0]] == "CNPJ"
    assert page.values[flow["uf"][0]] == ""
    assert page.clicked == [
        flow["submit"][0],
        flow["certificate_link"][0],
        flow["visualize"][0],
        flow["print"][0],
    ]
    assert result["pdf_path"].endswith("fgts_crf.pdf")
    assert Path(result["pdf_path"]).read_bytes().startswith(b"%PDF-")
    assert manager.launch_calls == [{"headless": True}]
    assert manager.cdp_urls == []
    assert captcha_calls == []


def test_fgts_selects_cnpj_when_native_dropdown_is_hidden(monkeypatch, tmp_path):
    flow = SITE_FLOWS["fgts"]
    manager = FakePlaywrightManager(flow)
    page = manager.browser.page
    type_selector = flow["document_type"][0]
    page.visible_selectors.discard(type_selector)
    page.hidden_selectors.add(type_selector)
    page.values[type_selector] = "CPF"
    monkeypatch.setattr("certhub.site_automation.sync_playwright", lambda: manager)

    run_site(
        "consultation-id", "fgts", "12345678000195",
        lambda *args: None, lambda *args: None, tmp_path,
    )

    assert page.values[type_selector] == "CNPJ"
    assert page.filled[flow["document"][0]] == "12345678000195"


def test_cndt_keeps_operator_submission_in_cdp_tab(monkeypatch, tmp_path):
    flow = SITE_FLOWS["cndt"]
    manager = FakePlaywrightManager(flow)
    page = manager.browser.page
    monkeypatch.setattr("certhub.site_automation.sync_playwright", lambda: manager)
    monkeypatch.setattr("certhub.site_automation.get_env_var", lambda _name, default=None: default)

    def human_emits_certificate_in_portal(site, kind, image, selector):
        assert site == "cndt"
        assert kind == "imagem"
        assert image is None
        assert selector is None
        return "concluido"

    def save_cndt_pdf(site, status, detail):
        if site == "cndt" and status == "rodando" and detail:
            (tmp_path / "cndt.pdf").write_bytes(b"%PDF-1.4\nmanual test\n")

    run_site(
        "consultation-id",
        "cndt",
        "12345678000195",
        save_cndt_pdf,
        human_emits_certificate_in_portal,
        tmp_path,
    )

    assert manager.launch_calls == []
    assert manager.cdp_urls == ["http://127.0.0.1:9222"]
    assert page.url == flow["url"]
    assert page.clicked == []
    assert page.is_closed() is False
    assert not hasattr(manager.browser, "closed")


def test_cndt_download_listener_uses_assignable_callback_and_saves_manual_pdf(monkeypatch, tmp_path):
    flow = SITE_FLOWS["cndt"]
    manager = FakePlaywrightManager(flow)
    page = manager.browser.page
    monkeypatch.setattr("certhub.site_automation.sync_playwright", lambda: manager)
    monkeypatch.setattr("certhub.site_automation.get_env_var", lambda _name, default=None: default)

    def operator_emits_and_confirms(*_args):
        return "concluido"

    def save_cndt_pdf(_site, status, detail):
        if status == "rodando" and detail:
            (tmp_path / "cndt.pdf").write_bytes(b"%PDF-1.4\nmanual test\n")

    result = run_site(
        "consultation-id", "cndt", "12345678000195",
        save_cndt_pdf, operator_emits_and_confirms, tmp_path,
    )

    assert Path(result["pdf_path"]).read_bytes().startswith(b"%PDF-")
    assert result["pdf_path"].endswith("cndt.pdf")


def test_cdp_url_is_loaded_from_project_environment(monkeypatch, tmp_path):
    manager = FakePlaywrightManager(SITE_FLOWS["cndt"])
    page = manager.browser.page
    monkeypatch.setattr("certhub.site_automation.sync_playwright", lambda: manager)
    monkeypatch.setattr(
        "certhub.site_automation.get_env_var",
        lambda name, default=None: "http://127.0.0.1:9333" if name == "CERTHUB_CDP_URL" else default,
    )

    run_site(
        "consultation-id",
        "cndt",
        "12345678000195",
        lambda *args: (tmp_path / "cndt.pdf").write_bytes(b"%PDF-1.4\nmanual\n") if args[1] == "rodando" and args[2] else None,
        lambda *_args: "concluido",
        tmp_path,
    )

    assert manager.cdp_urls == ["http://127.0.0.1:9333"]


def test_cdp_connection_refusal_has_actionable_operator_guidance(monkeypatch, tmp_path):
    flow = SITE_FLOWS["cndt"]
    manager = FakePlaywrightManager(flow)

    def refuse_connection(_url):
        raise OSError("connect ECONNREFUSED 127.0.0.1:9222")

    manager.chromium.connect_over_cdp = refuse_connection
    monkeypatch.setattr("certhub.site_automation.sync_playwright", lambda: manager)

    with pytest.raises(SiteAutomationError, match="--remote-debugging-port=9222"):
        run_site(
            "consultation-id",
            "cndt",
            "12345678000195",
            lambda *args: None,
            lambda *args: None,
            tmp_path,
        )


def test_visible_browser_is_started_automatically_when_cdp_is_unavailable(monkeypatch, tmp_path):
    flow = SITE_FLOWS["cndt"]
    manager = FakePlaywrightManager(flow)
    attempts = {"connect": 0}

    def connect_then_retry(url):
        manager.cdp_urls.append(url)
        attempts["connect"] += 1
        if attempts["connect"] == 1:
            raise OSError("connect ECONNREFUSED 127.0.0.1:9222")
        return manager.browser

    manager.chromium.connect_over_cdp = connect_then_retry
    monkeypatch.setattr("certhub.site_automation.sync_playwright", lambda: manager)
    monkeypatch.setattr("certhub.site_automation._start_visible_browser_for_cdp", lambda url: True)

    run_site(
        "consultation-id",
        "cndt",
        "12345678000195",
        lambda *args: (tmp_path / "cndt.pdf").write_bytes(b"%PDF-1.4\nmanual\n") if args[1] == "rodando" and args[2] else None,
        lambda *_args: "concluido",
        tmp_path,
    )

    assert attempts["connect"] == 2
    assert manager.cdp_urls == ["http://127.0.0.1:9222", "http://127.0.0.1:9222"]


def test_cdp_connection_refusal_does_not_launch_another_browser(monkeypatch, tmp_path):
    flow = SITE_FLOWS["cndt"]
    manager = FakePlaywrightManager(flow)

    def refuse_connection(url):
        manager.cdp_urls.append(url)
        raise OSError("connect ECONNREFUSED 127.0.0.1:9222")

    manager.chromium.connect_over_cdp = refuse_connection
    monkeypatch.setattr("certhub.site_automation.sync_playwright", lambda: manager)
    monkeypatch.setattr("certhub.site_automation._start_visible_browser_for_cdp", lambda url: False)

    with pytest.raises(SiteAutomationError, match="não abrirá outra janela"):
        run_site(
            "consultation-id", "cndt", "12345678000195",
            lambda *args: None, lambda *args: None, tmp_path,
        )

    assert manager.cdp_urls == ["http://127.0.0.1:9222"]


def test_cnpj_captcha_flow_opens_a_dedicated_tab_instead_of_reusing_blank(monkeypatch, tmp_path):
    flow = SITE_FLOWS["cndt"]
    manager = FakePlaywrightManager(flow)
    page = manager.browser.page
    page.url = "about:blank"
    monkeypatch.setattr("certhub.site_automation.sync_playwright", lambda: manager)
    monkeypatch.setattr("certhub.site_automation.get_env_var", lambda _name, default=None: default)

    def operator_downloads(*_args):
        return "concluido"

    run_site(
        "consultation-id", "cndt", "12345678000195",
        lambda *args: (tmp_path / "cndt.pdf").write_bytes(b"%PDF-1.4\nmanual\n") if args[1] == "rodando" and args[2] else None,
        operator_downloads, tmp_path,
    )

    assert manager.browser.new_page_calls == 1
    assert page.is_closed() is False


def test_visible_locator_skips_hidden_first_match():
    class Candidate:
        def __init__(self, visible):
            self.visible = visible

        def is_visible(self):
            return self.visible

    class Matches:
        def count(self):
            return 2

        def nth(self, index):
            return candidates[index]

    candidates = [Candidate(False), Candidate(True)]
    page = SimpleNamespace(locator=lambda _selector: Matches())

    assert _visible_locator(page, ["input#document"]) is candidates[1]


def test_only_the_three_cnpj_captcha_sites_get_parallel_visible_slots():
    assert _visible_browser_slot_kind("cndt", "12.345.678/0001-95") == "parallel-cnpj-captcha"
    assert _visible_browser_slot_kind("ceis_cgu", "12345678000195") == "parallel-cnpj-captcha"
    assert _visible_browser_slot_kind("cartao_cnpj", "12345678000195") == "parallel-cnpj-captcha"
    assert _visible_browser_slot_kind("cndt", "52998224725") == "exclusive"
    assert _visible_browser_slot_kind("fgts", "12345678000195") == "exclusive"
    assert _visible_browser_slot_kind("simples_nacional", "12345678000195") == "exclusive"


def test_cnpj_captcha_tabs_can_be_prepared_together_but_other_visible_flows_wait():
    parallel_slots = 3
    for _ in range(parallel_slots):
        _acquire_visible_browser_slot("parallel-cnpj-captcha")

    exclusive_acquired = threading.Event()

    def wait_for_exclusive_slot():
        _acquire_visible_browser_slot("exclusive")
        exclusive_acquired.set()
        _release_visible_browser_slot("exclusive")

    worker = threading.Thread(target=wait_for_exclusive_slot)
    worker.start()
    assert not exclusive_acquired.wait(timeout=0.05)

    for _ in range(parallel_slots):
        _release_visible_browser_slot("parallel-cnpj-captcha")
    assert exclusive_acquired.wait(timeout=2)
    worker.join(timeout=2)
    assert not worker.is_alive()


def test_cnpj_captcha_flow_always_uses_a_new_visible_tab():
    flow = SITE_FLOWS["cndt"]
    existing_page = FakePage(flow)
    created_page = FakePage(flow)

    class Context:
        pages = [existing_page]
        new_page_calls = 0

        def new_page(self):
            self.new_page_calls += 1
            return created_page

    context = Context()

    page = _reuse_visible_page(context, flow, force_new=True)

    assert page is created_page
    assert context.new_page_calls == 1


def test_portal_config_selectors_keep_code_fallbacks():
    assert "#Cnpj" in SITE_FLOWS["simples_nacional"]["document"]
    assert "input[name='mainForm:txtInscricao1']" in SITE_FLOWS["fgts"]["document"]
    assert "input[placeholder*='CNPJ' i]" in SITE_FLOWS["receita_inss_cnpj"]["document"]


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
    assert page.filled[flow["document"][0]] == "12.345.678/0001-95"
    assert page.clicked == [flow["search"][0], flow["submit"][0]]
    assert flow["positive_result"][0] not in page.clicked
    assert result["pdf_path"].endswith("cnj_improbidade.pdf")


def test_receita_cnpj_downloads_second_copy_of_most_recent_certificate(monkeypatch, tmp_path):
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
    assert page.filled[flow["document"][0]] == "12.345.678/0001-95"
    assert page.clicked == [
        flow["consult"][0],
        flow["consult"][0],
        flow["latest_second_copy"][0],
    ]
    assert result["pdf_path"].endswith("receita_cnpj.pdf")


def test_receita_cnpj_falls_back_to_new_emission_if_query_has_no_rows(monkeypatch, tmp_path):
    flow = dict(SITE_FLOWS["receita_inss_cnpj"])
    flow["query_results_timeout_ms"] = 1
    flow["fake_query_results"] = False
    monkeypatch.setitem(SITE_FLOWS, "receita_inss_cnpj", flow)
    manager = FakePlaywrightManager(flow)
    monkeypatch.setattr("certhub.site_automation.sync_playwright", lambda: manager)

    with pytest.raises(SiteAutomationError, match="/cnpj/consultar/resultado"):
        run_site(
            "consultation-id",
            "receita_inss_cnpj",
            "12345678000195",
            lambda *args: None,
            lambda *args: None,
            tmp_path,
        )

    assert manager.browser.page.clicked == [flow["consult"][0], flow["consult"][0]]


def test_receita_cnpj_falls_back_to_emission_if_query_form_is_unavailable(monkeypatch, tmp_path):
    flow = dict(SITE_FLOWS["receita_inss_cnpj"])
    flow["query_form_timeout_ms"] = 1
    flow["fake_query_form"] = False
    monkeypatch.setitem(SITE_FLOWS, "receita_inss_cnpj", flow)
    manager = FakePlaywrightManager(flow)
    monkeypatch.setattr("certhub.site_automation.sync_playwright", lambda: manager)

    with pytest.raises(SiteAutomationError, match="/cnpj/consultar"):
        run_site(
            "consultation-id",
            "receita_inss_cnpj",
            "12345678000195",
            lambda *args: None,
            lambda *args: None,
            tmp_path,
        )

    assert manager.browser.page.clicked == [flow["consult"][0]]


def test_receita_cnpj_does_not_switch_to_emission_when_query_form_is_missing(monkeypatch, tmp_path):
    flow = dict(SITE_FLOWS["receita_inss_cnpj"])
    flow["fake_query_form"] = False
    flow["query_form_timeout_ms"] = 1
    manager = FakePlaywrightManager(flow)
    monkeypatch.setattr("certhub.site_automation.SITE_FLOWS", {**SITE_FLOWS, "receita_inss_cnpj": flow})
    monkeypatch.setattr("certhub.site_automation.sync_playwright", lambda: manager)

    with pytest.raises(SiteAutomationError, match="/cnpj/consultar"):
        run_site(
            "consultation-id",
            "receita_inss_cnpj",
            "12345678000195",
            lambda *args: None,
            lambda *args: None,
            tmp_path,
        )

    assert manager.browser.page.clicked == [flow["consult"][0]]


def test_receita_cnpj_fills_document_before_first_consult_and_uses_two_step_query(monkeypatch, tmp_path):
    flow = dict(SITE_FLOWS["receita_inss_cnpj"])
    monkeypatch.setattr("certhub.site_automation.SITE_FLOWS", {**SITE_FLOWS, "receita_inss_cnpj": flow})
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

    assert manager.browser.page.clicked == [
        flow["consult"][0],
        flow["consult"][0],
        flow["latest_second_copy"][0],
    ]
    assert manager.browser.page.documents_at_consult == [
        "12.345.678/0001-95",
        "12.345.678/0001-95",
    ]
    assert manager.browser.page.filled == {flow["document"][0]: "12.345.678/0001-95"}
    assert Path(result["pdf_path"]).read_bytes().startswith(b"%PDF-")


def test_receita_cnpj_reports_official_portal_error_023_without_waiting_for_data_form(monkeypatch, tmp_path):
    flow = dict(SITE_FLOWS["receita_inss_cnpj"])
    flow["fake_query_error"] = True
    flow["query_023_retries"] = 1
    flow["query_023_retry_delay_ms"] = 1000
    monkeypatch.setattr("certhub.site_automation.SITE_FLOWS", {**SITE_FLOWS, "receita_inss_cnpj": flow})
    manager = FakePlaywrightManager(flow)
    monkeypatch.setattr("certhub.site_automation.sync_playwright", lambda: manager)

    with pytest.raises(SiteAutomationError, match="erro 023.*Nenhum PDF foi emitido"):
        run_site(
            "consultation-id",
            "receita_inss_cnpj",
            "12345678000195",
            lambda *args: None,
            lambda *args: None,
            tmp_path,
        )

    assert manager.browser.page.clicked == [flow["consult"][0], flow["consult"][0]]
    assert manager.browser.page.goto_calls == 2
    assert not (tmp_path / "receita_cnpj.pdf").exists()


def test_receita_cnpj_retries_transient_error_023_and_downloads_pdf(monkeypatch, tmp_path):
    flow = dict(SITE_FLOWS["receita_inss_cnpj"])
    flow.update(
        fake_query_error=True,
        fake_query_error_attempts=1,
        query_023_retry_delay_ms=1000,
    )
    monkeypatch.setattr("certhub.site_automation.SITE_FLOWS", {**SITE_FLOWS, "receita_inss_cnpj": flow})
    manager = FakePlaywrightManager(flow)
    monkeypatch.setattr("certhub.site_automation.sync_playwright", lambda: manager)
    statuses = []

    result = run_site(
        "consultation-id",
        "receita_inss_cnpj",
        "12345678000195",
        lambda *args: statuses.append(args),
        lambda *args: None,
        tmp_path,
    )

    assert manager.browser.page.clicked == [
        flow["consult"][0],
        flow["consult"][0],
        flow["consult"][0],
        flow["latest_second_copy"][0],
    ]
    assert manager.browser.page.documents_at_consult == [
        "12.345.678/0001-95",
        "12.345.678/0001-95",
        "12.345.678/0001-95",
    ]
    assert any("tentativa 2/3" in (status[2] or "") for status in statuses)
    assert Path(result["pdf_path"]).read_bytes().startswith(b"%PDF-")


def test_receita_cnpj_detects_recaptcha():
    flow = SITE_FLOWS["receita_inss_cnpj"]
    page = FakePage(flow)
    page.visible_selectors.add(flow["captcha_recaptcha"][0])

    assert _captcha_kind(page, flow) == ("recaptcha", flow["captcha_recaptcha"][0])


def test_receita_cnpj_detects_existing_certificate_modal_immediately():
    flow = SITE_FLOWS["receita_inss_cnpj"]
    page = FakePage(flow)
    page.visible_selectors.add(flow["valid_certificate_notice"][0])

    result = _wait_for_receita_state(page, flow, "valid_or_result", lambda *args: None, lambda *args: None)

    assert result == "valid_certificate"
    assert page.waits == 0


def test_receita_cnpj_detects_emission_result_immediately():
    flow = SITE_FLOWS["receita_inss_cnpj"]
    page = FakePage(flow)
    page.visible_selectors.add(flow["result_notice"][0])

    result = _wait_for_receita_state(page, flow, "result", lambda *args: None, lambda *args: None)

    assert result == "result"
    assert page.waits == 0


def test_fgts_reports_azion_gateway_timeout():
    page = SimpleNamespace(
        title=lambda: "Azion - Default error page",
        locator=lambda selector: SimpleNamespace(
            inner_text=lambda: "Status Code 504\nRequest ID\nef540770479134469d70e917c410acb0"
        ),
    )

    with pytest.raises(SiteAutomationError, match="HTTP 504"):
        _run_fgts_macro(page, SITE_FLOWS["fgts"], "08037769000196", Path("unused.pdf"))


def test_fgts_reports_shieldsquare_block():
    page = SimpleNamespace(
        title=lambda: "ShieldSquare Block",
        locator=lambda selector: SimpleNamespace(
            inner_text=lambda: "Bot protection\nThis request was blocked by ShieldSquare"
        ),
    )

    with pytest.raises(SiteAutomationError, match="bloqueado.*anti-bot|ShieldSquare"):
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


def test_all_ten_catalog_flows_are_registered_with_the_required_modes():
    expected_modes = {
        "receita_inss_cnpj": "INTERNO",
        "receita_inss_cpf": "INTERNO",
        "fgts": "INTERNO",
        "cndt": "VISÍVEL/CAPTCHA",
        "inelegibilidade_cnj": "INTERNO",
        "ceis_cgu": "VISÍVEL/CAPTCHA",
        "cartao_cnpj": "VISÍVEL/CAPTCHA",
        "tcu_inidoneos": "INTERNO",
        "simples_nacional": "INTERNO",
        "sicaf": "TOKEN",
    }

    assert set(SITE_FLOWS) == set(expected_modes)
    assert {site: flow["execution_mode"] for site, flow in SITE_FLOWS.items()} == expected_modes
    assert all(flow["implemented"] for flow in SITE_FLOWS.values())


@pytest.mark.parametrize("site_code", sorted(SITE_FLOWS))
def test_every_portal_has_required_id_and_independent_output_filename(site_code):
    flow = SITE_FLOWS[site_code]
    expected_file_ids = {
        "sicaf": "compras_gov",
        "receita_inss_cnpj": "receita_cnpj",
        "receita_inss_cpf": "receita_cpf",
        "fgts": "fgts_crf",
        "cndt": "cndt",
        "inelegibilidade_cnj": "cnj_improbidade",
        "ceis_cgu": "cgu_certidoes",
        "cartao_cnpj": "receita_cnpj_comprovante",
        "tcu_inidoneos": "tcu_licitantes",
        "simples_nacional": "simples_nacional",
    }
    assert flow["file_id"] == expected_file_ids[site_code]


def _minimal_page(flow):
    page = FakePage(flow)
    page.visible_selectors.update(
        selector
        for key in (
            "document", "birth_date", "submit", "private_entity", "negative_certificate",
            "cpf_toggle", "result_notice", "more_info", "generate_pdf", "certificate_button",
            "download_button", "success_notice", "result_download",
        )
        for selector in flow.get(key, [])
    )
    return page


def test_receita_cpf_fills_birth_date_and_downloads_second_copy(tmp_path):
    flow = {
        "document": ["input.cpf"],
        "birth_date": ["input.birth-date"],
        "submit": ["button.consultar"],
        "latest_second_copy": ["button.second-copy"],
        "url_on_submit": ["https://rf.test/#/cpf/consultar", "https://rf.test/#/cpf/consultar/resultado"],
    }
    page = _minimal_page(flow)
    target = tmp_path / "receita_cpf.pdf"

    _run_receita_cpf_macro(page, flow, "52998224725", "2000-01-02", target)

    assert page.filled["input.cpf"] == "529.982.247-25"
    assert page.filled["input.birth-date"] == "02/01/2000"
    assert target.read_bytes().startswith(b"%PDF-")


def test_cndt_captures_pdf_after_operator_submits_in_portal_tab(tmp_path):
    flow = {
        "entry": ["a[href*='gerarCertidao']"], "document": ["#cpfCnpj"], "submit": ["#botao-emitir"],
        "captcha_image": ["img[alt*='Captcha' i]"], "captcha_input": ["#captcha-resposta"],
    }
    page = _minimal_page(flow)
    status_events = []

    def human_submits_in_tab(*args):
        return "concluido"

    def save_cndt_pdf(_site, status, detail):
        if status == "rodando" and detail:
            (tmp_path / "cndt.pdf").write_bytes(b"%PDF-1.4\nmanual test\n")

    _run_cndt_macro(
        page,
        flow,
        "12345678000195",
        tmp_path / "cndt.pdf",
        lambda *args: (status_events.append(args), save_cndt_pdf(*args)),
        human_submits_in_tab,
    )

    assert page.filled["#cpfCnpj"] == "12.345.678/0001-95"
    assert page.clicked == []
    assert any(status[1] == "aguardando_captcha" for status in status_events)
    assert (tmp_path / "cndt.pdf").read_bytes().startswith(b"%PDF-")


def test_cndt_waits_for_operator_to_solve_and_submit_without_clicking_for_them(tmp_path):
    flow = {
        "document": ["#cpfCnpj"], "submit": ["#botao-emitir"],
        "captcha_image": ["img[alt*='Captcha' i]"], "captcha_input": ["#captcha-resposta"],
    }
    page = _minimal_page(flow)
    statuses = []

    def human_solves_and_submits(*_args):
        return "concluido"

    def save_cndt_pdf(_site, status, detail):
        if status == "rodando" and detail:
            (tmp_path / "cndt.pdf").write_bytes(b"%PDF-1.4\nmanual test\n")

    _run_cndt_macro(
        page, flow, "12345678000195", tmp_path / "cndt.pdf",
        lambda *args: (statuses.append(args), save_cndt_pdf(*args)), human_solves_and_submits,
    )

    assert page.filled["#cpfCnpj"] == "12.345.678/0001-95"
    assert page.clicked == []
    assert any(status[1] == "aguardando_captcha" for status in statuses)
    assert (tmp_path / "cndt.pdf").read_bytes().startswith(b"%PDF-")


def test_cndt_uses_the_tst_cnpj_field_not_the_site_search_box():
    flow = SITE_FLOWS["cndt"]

    assert flow["url"] == "https://cndt-certidao.tst.jus.br/"
    assert "entry" not in flow
    assert flow["document"] == ["#cpfCnpj", "input[name='cpfCnpj']"]
    assert "input[type='text']" not in flow["document"]
    assert flow["captcha_input"][0] == "#captcha-resposta"
    assert flow["submit"][0] == "#botao-emitir"


def test_cgu_selects_private_negative_certificate_and_waits_for_manual_pdf(tmp_path):
    flow = {
        "private_entity": ["radio.private"], "negative_certificate": ["input.negative"],
        "document": ["input.doc"], "submit": ["button.consultar"],
        "result_url": "/resultado-consulta-responsabilizacao/", "certificate_button": ["button.certidao"],
    }
    page = _minimal_page(flow)
    target = tmp_path / "cgu_certidoes.pdf"

    def operator_saves_pdf(site, status, detail):
        if status == "rodando" and detail:
            target.write_bytes(b"%PDF-1.4\nmanual test\n")

    _run_cgu_macro(page, flow, "12345678000195", target, operator_saves_pdf, lambda *args: None)

    assert page.clicked[0] == "radio.private"
    assert page.values["input.negative"] == "checked"
    assert page.filled["input.doc"] == "12345678000195"
    assert "button.certidao" not in page.clicked
    assert target.read_bytes().startswith(b"%PDF-")


def test_cgu_uses_public_homepage_and_emission_entrypoint():
    assert SITE_FLOWS["ceis_cgu"]["url"] == "https://certidoes.cgu.gov.br/"
    assert "a[href='/consulta-certidao']" in SITE_FLOWS["ceis_cgu"]["entry"]
    assert "label.custom-control-label:has-text('Ente Privado')" in SITE_FLOWS["ceis_cgu"]["private_entity"]
    assert "#cpfCnpj" in SITE_FLOWS["ceis_cgu"]["document"]


def test_cgu_login_gate_fails_explicitly_without_claiming_success(tmp_path):
    flow = {
        "private_entity": ["radio.private"], "negative_certificate": ["input.negative"],
        "document": ["input.doc"], "submit": ["button.consultar"],
    }
    page = _minimal_page(flow)
    page.url = "https://certidoes.cgu.gov.br/signin"

    with pytest.raises(SiteAutomationError, match="exige sessão autenticada"):
        _run_cgu_macro(page, flow, "12345678000195", tmp_path / "cgu_certidoes.pdf", lambda *args: None, lambda *args: None)

    assert not (tmp_path / "cgu_certidoes.pdf").exists()


def test_receita_cnpj_comprovante_waits_for_manually_saved_pdf(tmp_path):
    flow = {"document": ["input.cnpj"], "submit": ["button.consultar"], "result_url": "/comprovante"}
    page = _minimal_page(flow)
    target = tmp_path / "receita_cnpj_comprovante.pdf"

    def operator_saves_pdf(site, status, detail):
        if status == "rodando" and detail:
            target.write_bytes(b"%PDF-1.4\nmanual test\n")

    _run_cartao_cnpj_macro(page, flow, "08037769000196", target, operator_saves_pdf, lambda *args: None)

    assert page.filled["input.cnpj"] == "08037769000196"
    assert page.url.endswith("/comprovante")
    assert target.read_bytes().startswith(b"%PDF-")


def test_receita_cnpj_comprovante_uses_masked_cnpj_input():
    flow = SITE_FLOWS["cartao_cnpj"]

    assert "input[mask='AA.AAA.AAA/AAAA-AA']" in flow["document"]
    assert "input[maxlength='18']" in flow["document"]


def test_download_click_saves_base64_pdf_from_official_json_response(tmp_path):
    pdf_bytes = b"%PDF-1.7\nOfficial Receita certificate fixture\n"
    body = json.dumps({"status": "Sucesso", "pdf": base64.b64encode(pdf_bytes).decode("ascii")}).encode()
    flow = {"download_failures": 1, "fake_response": FakeResponse(body)}
    page = _minimal_page(flow)
    target = tmp_path / "consulta" / "receita_cnpj.pdf"

    _download_from_click(page, FakeLocator(page, "button.second-copy"), target, "Receita CNPJ")

    assert target.read_bytes() == pdf_bytes
    assert target.read_bytes().startswith(b"%PDF-")
    assert target.parent.is_dir()
    assert page.response_callback is None


def test_tcu_switches_document_type_and_downloads_result(tmp_path):
    flow = {"document": ["input.doc"], "cpf_toggle": ["button.cpf"], "submit": ["button.emitir"], "download_button": ["button.baixar"]}
    page = _minimal_page(flow)

    _run_tcu_macro(page, flow, "52998224725", "CPF", tmp_path / "tcu_licitantes.pdf")

    assert page.clicked[:2] == ["button.cpf", "button.emitir"]
    assert page.filled["input.doc"] == "52998224725"
    assert (tmp_path / "tcu_licitantes.pdf").read_bytes().startswith(b"%PDF-")


def test_simples_nacional_waits_for_status_and_downloads_generated_pdf(tmp_path):
    flow = {
        "document": ["input.cnpj"], "submit": ["button.consultar"],
        "result_notice": ["text=Situação Atual"], "more_info": ["button.info"],
        "generate_pdf": ["button.pdf"],
    }
    page = _minimal_page(flow)

    _run_simples_nacional_macro(page, flow, "08037769000196", tmp_path / "simples_nacional.pdf", lambda *args: None, lambda *args: None)

    assert page.filled["input.cnpj"] == "08037769000196"
    assert page.clicked == ["button.consultar", "button.info", "button.pdf"]
    assert (tmp_path / "simples_nacional.pdf").read_bytes().startswith(b"%PDF-")


def test_simples_nacional_reports_hcaptcha_that_appears_after_submit(tmp_path):
    flow = {
        "execution_mode": "INTERNO",
        "document": ["input.cnpj"],
        "submit": ["button.consultar"],
        "result_notice": ["text=Situação Atual"],
        "captcha_hcaptcha": ["iframe[title*='hCaptcha' i]"],
        "fake_hcaptcha_after_submit": True,
    }
    page = FakePage(flow)

    with pytest.raises(SiteAutomationError, match="Simples Nacional: a Receita apresentou hCaptcha"):
        _run_simples_nacional_macro(
            page, flow, "08037769000196", tmp_path / "simples_nacional.pdf",
            lambda *args: None, lambda *args: None,
        )

    assert page.clicked == ["button.consultar"]
    assert not (tmp_path / "simples_nacional.pdf").exists()


def test_simples_nacional_reports_invisible_hcaptcha_frame_after_submit(tmp_path):
    flow = {
        "execution_mode": "INTERNO",
        "document": ["input.cnpj"],
        "submit": ["button.consultar"],
        "result_notice": ["text=Situação Atual"],
        "captcha_hcaptcha": ["iframe[title*='hCaptcha' i]"],
        "result_timeout_ms": 1,
        "fake_hidden_hcaptcha_after_submit": True,
    }
    page = FakePage(flow)
    page.frames = [SimpleNamespace(url="https://newassets.hcaptcha.com/captcha.html")]

    with pytest.raises(SiteAutomationError, match="carregou um iframe hCaptcha"):
        _run_simples_nacional_macro(
            page, flow, "08037769000196", tmp_path / "simples_nacional.pdf",
            lambda *args: None, lambda *args: None,
        )

    assert page.clicked == ["button.consultar"]
    assert not (tmp_path / "simples_nacional.pdf").exists()


def test_simples_nacional_uses_current_portal_result_and_pdf_ids():
    flow = SITE_FLOWS["simples_nacional"]

    assert "#btnMaisInfo" in flow["result_notice"]
    assert "#GerarPDF" in flow["result_notice"]
    assert "#btnMaisInfo" in flow["more_info"]
    assert "#GerarPDF" in flow["generate_pdf"]


def test_sicaf_token_handoff_exports_only_after_operator_confirms_certidao(tmp_path):
    flow = {"execution_mode": "TOKEN"}
    page = _minimal_page(flow)
    events = []

    _run_sicaf_token_flow(
        page,
        "12345678000195",
        tmp_path / "compras_gov.pdf",
        lambda *args: events.append(args),
        lambda *args: "concluido",
    )

    assert events == [
        ("sicaf", "aguardando_captcha", "Autentique com certificado digital/token e deixe a certidão aberta para impressão."),
        ("sicaf", "rodando", None),
    ]
    assert (tmp_path / "compras_gov.pdf").read_bytes().startswith(b"%PDF-")