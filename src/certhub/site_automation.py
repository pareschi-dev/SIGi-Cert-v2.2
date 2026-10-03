from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import threading
import time
from urllib import request as urllib_request
from datetime import datetime
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from certhub.config import create_consultation_directory, get_env_var, load_certidoes_config, resolve_project_path

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright

    _PLAYWRIGHT_IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - depends on host OS security policy
    PlaywrightTimeoutError = TimeoutError
    sync_playwright = None
    _PLAYWRIGHT_IMPORT_ERROR = exc


_SITE_FLOW_ALIASES = {
    "compras_gov": "sicaf",
    "receita_cnpj": "receita_inss_cnpj",
    "receita_cpf": "receita_inss_cpf",
    "fgts_crf": "fgts",
    "cnj_improbidade": "inelegibilidade_cnj",
    "cgu_certidoes": "ceis_cgu",
    "receita_cnpj_comprovante": "cartao_cnpj",
    "tcu_licitantes": "tcu_inidoneos",
}


SITE_FLOWS = {
    "sicaf": {
            "execution_mode": "TOKEN",
            "file_id": "compras_gov",
            "url": "https://www3.comprasnet.gov.br/sicaf-web/index.jsf",
    },
    "receita_inss_cnpj": {
        "execution_mode": "INTERNO",
        "file_id": "receita_cnpj",
        "url": "https://servicos.receitafederal.gov.br/servico/certidoes/#/home/cnpj#",
        "document": ["input[placeholder*='CNPJ' i]", "input[name='niContribuinte']"],
        "consult": ["button:has-text('Consultar Certidão')"],
        "query_form": ["input[placeholder='Selecione a data']", "text=Data Inicial"],
        "query_error": [
            "text=Não foi possível concluir a ação",
            "text=023 -",
        ],
        "query_submit": ["button:has-text('Consultar Certidão')"],
        "query_results": [
            "text=Relação das certidões emitidas",
            "datatable-body-row",
            "table tbody tr",
        ],
        "latest_second_copy": [
            "datatable-body-row:first-child button[title='Segunda via']",
            "table tbody tr:first-child button[title='Segunda via']",
        ],
        "emit": ["button:has-text('Emitir Certidão')"],
        "valid_certificate_notice": [
            "heading:has-text('Certidão Válida Encontrada')",
            "text=Certidão Válida Encontrada",
        ],
        "emit_new": ["button:has-text('Emitir Nova Certidão')"],
        "result_notice": ["text=A certidão foi emitida com sucesso"],
        "result_download": [
            "a[download^='Certidao-']",
            "a:has-text('download do documento PDF da certidão')",
        ],
        "format_document": True,
        "captcha_recaptcha": ["div.g-recaptcha", "iframe[src*='recaptcha']"],
        "captcha_hcaptcha": ["div.h-captcha", "iframe[src*='hcaptcha']"],
    },
    "receita_inss_cpf": {
        "execution_mode": "INTERNO",
        "file_id": "receita_cpf",
        "url": "https://servicos.receitafederal.gov.br/servico/certidoes/#/home/cpf#",
        "document": ["input[placeholder*='CPF' i]", "input[name='cpf']", "input[id*='cpf' i]"],
        "birth_date": ["input[placeholder*='Nascimento' i]", "input[name*='nascimento' i]", "input[id*='nascimento' i]"],
        "submit": ["button:has-text('Consultar Certidão')"],
        "result_table": ["table:has-text('Relação das certidões emitidas')", "table tbody tr"],
        "latest_second_copy": ["table tbody tr:first-child td:last-child button", "table tbody tr:first-child td:last-child a"],
        "captcha_recaptcha": ["div.g-recaptcha", "iframe[src*='recaptcha']"],
    },
    "fgts": {
        "execution_mode": "VISÍVEL",
        "file_id": "fgts_crf",
        "url": "https://consulta-crf.caixa.gov.br/consultacrf/pages/consultaEmpregador.jsf",
        "document_type": ["select[id='mainForm:tipoEstabelecimento']", "select[name='mainForm:tipoEstabelecimento']"],
        "document": ["input[name='mainForm:txtInscricao1']", "input[id='mainForm:txtInscricao1']"],
        "uf": ["select[name='mainForm:uf']", "select[id='mainForm:uf']"],
        "submit": ["input[name='mainForm:btnConsultar']", "input[id='mainForm:btnConsultar']"],
        "certificate_link": ["a:has-text('Certificado de Regularidade do FGTS - CRF')"],
        "visualize": ["input[type='button'][value='Visualizar']", "button:has-text('Visualizar')"],
        "print": ["input[value='Imprimir']", "button:has-text('Imprimir')"],
        "digits_only": True,
    },
    "cndt": {
        "execution_mode": "VISÍVEL/CAPTCHA",
        "file_id": "cndt",
        "url": "https://cndt-certidao.tst.jus.br/",
        "document": ["#cpfCnpj", "input[name='cpfCnpj']"],
        "submit": ["#botao-emitir", "input[type='submit'][value='Emitir Certidão']"],
        "success_notice": ["text=Certidão EMITIDA com sucesso", "text=Certidão emitida com sucesso"],
        "captcha_image": ["img[alt*='Captcha' i]", "img#captchaImg"],
        "captcha_input": ["#captcha-resposta", "input[name='resposta']"],
        "result_download": ["a:has-text('Baixar Certidão')", "a[href$='.pdf']", "button:has-text('Baixar Certidão')"],
    },
    "inelegibilidade_cnj": {
        "execution_mode": "INTERNO",
        "file_id": "cnj_improbidade",
        "url": "https://www.cnj.jus.br/improbidade_adm/consultar_requerido.php?validar=form",
        "document": ["#num_cpf_cnpj"],
        "search": ["#btnPesquisarRequerido"],
        "submit": ["#btnCertidaoNegativa"],
        "positive_result": ["#btnCertidaoPositiva"],
        "format_document": True,
        "captcha_image": ["img[src*='captcha' i]"],
        "captcha_input": ["input[name='captcha']"],
    },
    "ceis_cgu": {
        "execution_mode": "VISÍVEL/CAPTCHA",
        "file_id": "cgu_certidoes",
        "url": "https://certidoes.cgu.gov.br/",
        "entry": ["a[href='/consulta-certidao']"],
        "private_entity": ["label.custom-control-label:has-text('Ente Privado')", "input[type='radio'][value='0']"],
        "negative_certificate": ["input[type='checkbox'][value='8']", "input[type='checkbox']"],
        "document": ["#cpfCnpj", "input[id*='cpf' i]", "input[id*='cnpj' i]", "input[name='cpfCnpj']"],
        "submit": ["button:has-text('Consultar')"],
        "captcha_recaptcha": ["iframe[src*='recaptcha']", "div.g-recaptcha"],
        "result_url": "/resultado-consulta-responsabilizacao/",
        "certificate_button": ["button:has-text('Certidão')"],
    },
    "cartao_cnpj": {
        "execution_mode": "VISÍVEL/CAPTCHA",
        "file_id": "receita_cnpj_comprovante",
        "url": "https://solucoes.receita.fazenda.gov.br/Servicos/cnpjreva/",
        "document": ["input[mask='AA.AAA.AAA/AAAA-AA']", "input[maxlength='18']", "input[id*='cnpj' i]", "input[name='cnpj']"],
        "submit": ["input[value='CONSULTAR']", "button:has-text('CONSULTAR')"],
        "captcha_hcaptcha": ["iframe[title*='hCaptcha' i]", "iframe[src*='hcaptcha' i]"],
        "result_url": "/comprovante",
    },
    "tcu_inidoneos": {
        "execution_mode": "INTERNO",
        "file_id": "tcu_licitantes",
        "url": "https://certidoes.apps.tcu.gov.br/emitir-certidao-inidoneos",
        "document": ["input[type='text']", "input[name='cpfCnpj']", "input[id*='cpfCnpj' i]"],
        "cpf_toggle": ["button[aria-label='Alternar consulta por CPF']", "button:has-text('CPF')"],
        "submit": ["button:has-text('Emitir certidão')"],
        "download_button": ["button:has-text('Baixar Certidão')"],
    },
    "simples_nacional": {
        "execution_mode": "VISÍVEL",
        "file_id": "simples_nacional",
        "url": "https://www8.receita.fazenda.gov.br/simplesnacional/aplicacoes.aspx?id=21",
        "document": ["#Cnpj", "input[name='Cnpj']", "input[id*='cnpj' i]", "input[name*='cnpj' i]"],
        "submit": ["input[value='Consultar']", "button:has-text('Consultar')"],
        "result_notice": ["#btnMaisInfo", "#GerarPDF", "text=Situação Atual"],
        "more_info": ["#btnMaisInfo", "button:has-text('Mais informações')", "a:has-text('Mais informações')"],
        "generate_pdf": ["#GerarPDF", "button:has-text('Gerar PDF')", "a:has-text('Gerar PDF')"],
        "captcha_hcaptcha": ["iframe[title*='hCaptcha' i]", "iframe[src*='hcaptcha' i]"],
    },
}


_PARALLEL_CNPJ_CAPTCHA_SITES = frozenset({"cndt", "ceis_cgu", "cartao_cnpj"})


def _apply_certidoes_rules(flows: dict[str, dict]) -> dict[str, dict]:
    configured = load_certidoes_config().get("portais", [])
    if not isinstance(configured, list):
        return flows
    for portal in configured:
        if not isinstance(portal, dict):
            continue
        flow_code = _SITE_FLOW_ALIASES.get(portal.get("id"), portal.get("id"))
        flow = flows.get(flow_code)
        if flow is None:
            continue
        execution_mode = portal.get("modo")
        if execution_mode in {"INTERNO", "VISÍVEL", "VISÍVEL/CAPTCHA", "TOKEN"}:
            flow["execution_mode"] = execution_mode
        flow["implemented"] = portal.get("implementado") is True
        url = portal.get("url_inicial")
        if isinstance(url, str) and url:
            flow["url"] = url
        selectors = portal.get("seletores")
        if not isinstance(selectors, dict):
            continue
        selector_map = {
            "link_pessoa_juridica": "entry",
            "campo_cnpj": "document",
            "campo_cpf": "document",
            "campo_documento": "document",
            "campo_inscricao": "document",
            "tipo_inscricao": "document_type",
            "campo_uf": "uf",
            "campo_data_nascimento": "birth_date",
            "link_emitir": "entry",
            "botao_emitir": "submit",
            "botao_emitir_certidao": "emit",
            "botao_emitir_nova_certidao": "emit_new",
            "botao_consultar_certidao": "consult",
            "botao_consultar_periodo": "query_submit",
            "formulario_consulta": "query_form",
            "resultados_consulta": "query_results",
            "segunda_via_mais_recente": "latest_second_copy",
            "segunda_via": "latest_second_copy",
            "resultado_emissao": "result_notice",
            "download_pdf": "result_download",
            "botao_pesquisar": "search",
            "botao_certidao_negativa": "submit",
            "botao_consultar": "submit",
            "link_crf": "certificate_link",
            "botao_visualizar": "visualize",
            "botao_imprimir": "print",
            "radio_privado": "private_entity",
            "link_emitir_publico": "entry",
            "checkbox_cert": "negative_certificate",
            "iframe_captcha": "captcha_recaptcha",
            "iframe_hcaptcha": "captcha_hcaptcha",
            "botao_toggle_cpf": "cpf_toggle",
            "botao_baixar": "download_button",
            "botao_mais_info": "more_info",
            "botao_gerar_pdf": "generate_pdf",
            "marcador_resultado": "result_notice",
        }
        for config_key, flow_key in selector_map.items():
            selector = selectors.get(config_key)
            if isinstance(selector, str) and selector:
                configured_selectors = [part.strip() for part in selector.split(",") if part.strip()]
                flow[flow_key] = list(dict.fromkeys([*configured_selectors, *flow.get(flow_key, [])]))
    return flows


SITE_FLOWS = _apply_certidoes_rules(SITE_FLOWS)
_VISIBLE_BROWSER_CONDITION = threading.Condition()
_VISIBLE_BROWSER_EXCLUSIVE = False
_VISIBLE_CNPJ_CAPTCHA_TABS = 0

CaptchaHandler = Callable[..., str | None]
StatusHandler = Callable[[str, str, str | None], None]


class SiteAutomationError(RuntimeError):
    pass


def _safe_error_detail(error: Exception) -> str:
    detail = str(error)
    detail = re.sub(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", "[CNPJ]", detail)
    detail = re.sub(r"\d{3}\.\d{3}\.\d{3}-\d{2}", "[CPF]", detail)
    detail = re.sub(r"(?<!\d)\d{11,14}(?!\d)", "[documento]", detail)
    return f"{type(error).__name__}: {detail}"[:400]


def _is_cdp_available(cdp_url: str) -> bool:
    endpoint = cdp_url.rstrip("/") + "/json/version"
    try:
        with urllib_request.urlopen(endpoint, timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def _candidate_browser_paths() -> list[str]:
    explicit_path = get_env_var("CERTHUB_BROWSER_PATH", "").strip()
    candidates: list[str] = []
    if explicit_path:
        candidates.append(explicit_path)

    if os.name == "nt":
        names = [
            "msedge.exe", "microsoft-edge", "msedge",
            "chrome.exe", "google-chrome", "chrome",
            "chromium.exe", "chromium",
        ]
        prefixes = [
            os.environ.get("LOCALAPPDATA"),
            os.environ.get("PROGRAMFILES"),
            os.environ.get("PROGRAMFILES(X86)"),
        ]
        for prefix in prefixes:
            if prefix:
                candidates.extend(
                    [
                        str(Path(prefix) / "Microsoft" / "Edge" / "Application" / name)
                        for name in ("msedge.exe",)
                    ]
                )
                candidates.extend(
                    [
                        str(Path(prefix) / "Google" / "Chrome" / "Application" / name)
                        for name in ("chrome.exe",)
                    ]
                )
                candidates.extend(
                    [
                        str(Path(prefix) / "Chromium" / "Application" / name)
                        for name in ("chrome.exe",)
                    ]
                )
    else:
        names = [
            "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
            "microsoft-edge", "msedge",
        ]
    for name in names:
        resolved = shutil.which(name)
        if resolved:
            candidates.append(resolved)
    return list(dict.fromkeys(candidates))


def _start_visible_browser_for_cdp(cdp_url: str) -> bool:
    if _is_cdp_available(cdp_url):
        return True

    if get_env_var("CERTHUB_AUTO_START_BROWSER", "true").strip().lower() not in {"1", "true", "yes", "on"}:
        return False

    browser_candidates = _candidate_browser_paths()
    if not browser_candidates:
        return False

    port = urlparse(cdp_url).port or 9222
    profile_dir = resolve_project_path("data/browser-profiles/sigi-visible")
    profile_dir.mkdir(parents=True, exist_ok=True)

    launched = False
    for browser_path in browser_candidates:
        command = [
            browser_path,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_dir}",
            "--profile-directory=Profile 1",
            "--new-window",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-notifications",
        ]
        try:
            subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                close_fds=True,
            )
            launched = True
            break
        except OSError:
            continue

    if not launched:
        return False

    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        if _is_cdp_available(cdp_url):
            return True
        time.sleep(0.5)
    return False


def _connect_with_cdp_fallback(playwright, cdp_url: str):
    try:
        return playwright.chromium.connect_over_cdp(cdp_url)
    except Exception as error:
        if "ECONNREFUSED" in str(error).upper():
            if _start_visible_browser_for_cdp(cdp_url):
                try:
                    return playwright.chromium.connect_over_cdp(cdp_url)
                except Exception:
                    pass
            raise SiteAutomationError(
                "O navegador visível não está conectado via CDP. Inicie o Edge/Chrome existente "
                "com --remote-debugging-port=9222; o SIGi não abrirá outra janela automaticamente."
            ) from error
        raise


def _reuse_visible_page(context, flow: dict, force_new: bool = False):
    if force_new:
        return context.new_page()
    pages = [page for page in context.pages if not page.is_closed()]
    blank_page = next((page for page in reversed(pages) if page.url == "about:blank"), None)
    if blank_page is not None:
        return blank_page
    portal_hosts = {urlparse(item["url"]).netloc for item in SITE_FLOWS.values() if item.get("url")}
    portal_page = next(
        (page for page in reversed(pages) if urlparse(page.url).netloc in portal_hosts),
        None,
    )
    return portal_page or context.new_page()


def _visible_browser_slot_kind(site_code: str, document: str) -> str:
    document_digits = re.sub(r"\D", "", document)
    if site_code in _PARALLEL_CNPJ_CAPTCHA_SITES and len(document_digits) == 14:
        return "parallel-cnpj-captcha"
    return "exclusive"


def _acquire_visible_browser_slot(slot_kind: str) -> None:
    global _VISIBLE_BROWSER_EXCLUSIVE, _VISIBLE_CNPJ_CAPTCHA_TABS
    with _VISIBLE_BROWSER_CONDITION:
        if slot_kind == "parallel-cnpj-captcha":
            while _VISIBLE_BROWSER_EXCLUSIVE:
                _VISIBLE_BROWSER_CONDITION.wait()
            _VISIBLE_CNPJ_CAPTCHA_TABS += 1
            return
        while _VISIBLE_BROWSER_EXCLUSIVE or _VISIBLE_CNPJ_CAPTCHA_TABS:
            _VISIBLE_BROWSER_CONDITION.wait()
        _VISIBLE_BROWSER_EXCLUSIVE = True


def _release_visible_browser_slot(slot_kind: str) -> None:
    global _VISIBLE_BROWSER_EXCLUSIVE, _VISIBLE_CNPJ_CAPTCHA_TABS
    with _VISIBLE_BROWSER_CONDITION:
        if slot_kind == "parallel-cnpj-captcha":
            _VISIBLE_CNPJ_CAPTCHA_TABS = max(0, _VISIBLE_CNPJ_CAPTCHA_TABS - 1)
        else:
            _VISIBLE_BROWSER_EXCLUSIVE = False
        _VISIBLE_BROWSER_CONDITION.notify_all()


def _visible_locator(page, selectors: list[str]):
    scopes = [page]
    try:
        scopes.extend(frame for frame in page.frames if frame != page.main_frame)
    except Exception:
        pass
    for scope in scopes:
        for selector in selectors:
            locator = scope.locator(selector)
            try:
                for index in range(locator.count()):
                    candidate = locator.nth(index)
                    if candidate.is_visible():
                        return candidate
            except Exception:
                continue
    return None


def _wait_for_visible_locator(page, selectors: list[str], timeout_ms: int = 15000):
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        locator = _visible_locator(page, selectors)
        if locator is not None:
            return locator
        page.wait_for_timeout(250)
    return None


def _captcha_kind(page, flow: dict) -> tuple[str, str] | None:
    for kind, key in (("imagem", "captcha_image"), ("recaptcha", "captcha_recaptcha"), ("hcaptcha", "captcha_hcaptcha")):
        selectors = flow.get(key, [])
        locator = _visible_locator(page, selectors) if selectors else None
        if locator is not None:
            return kind, selectors[0]
    return None


def _formatted_document(document: str) -> str:
    if len(document) == 14:
        return f"{document[:2]}.{document[2:5]}.{document[5:8]}/{document[8:12]}-{document[12:]}"
    if len(document) == 11:
        return f"{document[:3]}.{document[3:6]}.{document[6:9]}-{document[9:]}"
    return document


def _wait_for_receita_state(
    page,
    flow: dict,
    expected: str,
    on_status: StatusHandler,
    on_captcha: CaptchaHandler,
    timeout_ms: int = 60000,
) -> str:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        if expected == "valid_or_result":
            if _visible_locator(page, flow["valid_certificate_notice"]) is not None:
                return "valid_certificate"
            if _visible_locator(page, flow["result_notice"]) is not None:
                return "result"
        else:
            selectors = flow["result_notice"]
            if _visible_locator(page, selectors) is not None:
                return "result"
        captcha = _captcha_kind(page, flow)
        if captcha is not None:
            if flow.get("execution_mode") == "INTERNO":
                raise SiteAutomationError(
                    "Desafio inesperado em portal INTERNO; consulta interrompida sem abrir janela nem contornar CAPTCHA."
                )
            on_status("receita_inss_cnpj", "aguardando_captcha", None)
            _handle_human_captcha(page, "receita_inss_cnpj", flow, captcha, on_captcha)
            on_status("receita_inss_cnpj", "rodando", None)
        page.wait_for_timeout(200)
    if expected == "valid_or_result":
        raise SiteAutomationError(
            f"A Receita não mostrou o aviso de certidão válida nem o resultado em {timeout_ms // 1000}s."
        )
    raise SiteAutomationError(
        f"A Receita não confirmou a emissão da certidão em {timeout_ms // 1000}s."
    )


def _prepare_site_entry(page, flow: dict) -> None:
    entry_selectors = flow.get("entry", [])
    if not entry_selectors:
        return
    entry_locator = _visible_locator(page, entry_selectors)
    if entry_locator is not None:
        entry_locator.click()
        page.wait_for_timeout(250)


def _dismiss_cookie_consent(page) -> None:
    consent = _visible_locator(
        page,
        [
            "[role='dialog'] button:has-text('Aceitar')",
            "[role='dialog'] a:has-text('Aceitar')",
            "button:has-text('Aceitar cookies')",
            "a:has-text('Aceitar cookies')",
        ],
    )
    if consent is not None:
        consent.click()


def _run_fgts_macro(page, flow: dict, document: str, target: Path) -> None:
    portal_error = _fgts_portal_error(page)
    if portal_error:
        raise SiteAutomationError(portal_error)

    # Caixa may render the JSF select as a visually hidden native control behind
    # its accessible custom dropdown. Inspect it directly; visibility is not
    # required to read/select the native control.
    type_locator = None
    scopes = [page]
    try:
        scopes.extend(frame for frame in page.frames if frame != page.main_frame)
    except Exception:
        pass
    for scope in scopes:
        for selector in flow.get("document_type", []):
            matches = scope.locator(selector)
            try:
                for index in range(matches.count()):
                    candidate = matches.nth(index)
                    selected_label = candidate.evaluate(
                        "element => element.options?.[element.selectedIndex]?.textContent?.trim() || ''"
                    )
                    if str(selected_label).strip().casefold() != "cnpj":
                        candidate.select_option(label="CNPJ")
                        selected_label = candidate.evaluate(
                            "element => element.options?.[element.selectedIndex]?.textContent?.trim() || ''"
                        )
                    if str(selected_label).strip().casefold() == "cnpj":
                        type_locator = candidate
                        break
            except Exception:
                continue
            if type_locator is not None:
                break
        if type_locator is not None:
            break
    if type_locator is None:
        raise SiteAutomationError("Lista para selecionar CNPJ no FGTS não localizada.")

    document_locator = _wait_for_visible_locator(page, flow["document"])
    if document_locator is None:
        raise SiteAutomationError("Campo Inscrição do FGTS não localizado.")
    document_locator.fill(re.sub(r"\D", "", document))

    uf_locator = _visible_locator(page, flow["uf"])
    if uf_locator is not None and uf_locator.input_value():
        uf_locator.select_option("")

    consult_button = _visible_locator(page, flow["submit"])
    if consult_button is None:
        raise SiteAutomationError("Botão Consultar do FGTS não localizado.")
    consult_button.click()

    deadline = time.monotonic() + 25000 / 1000
    certificate_link = None
    while time.monotonic() < deadline:
        certificate_link = _visible_locator(page, flow["certificate_link"])
        if certificate_link is not None:
            break
        portal_error = _fgts_portal_error(page)
        if portal_error:
            raise SiteAutomationError(portal_error)
        page.wait_for_timeout(250)
    if certificate_link is None:
        raise SiteAutomationError("O FGTS não apresentou link para o Certificado de Regularidade.")
    certificate_link.click()

    visualize_button = _wait_for_visible_locator(page, flow["visualize"], timeout_ms=10000)
    if visualize_button is None:
        raise SiteAutomationError("Botão Visualizar do certificado FGTS não localizado.")
    visualize_button.click()

    print_button = _wait_for_visible_locator(page, flow["print"], timeout_ms=10000)
    if print_button is None:
        raise SiteAutomationError("Botão Imprimir do certificado FGTS não localizado.")
    # The first Caixa print action opens its official print-only page. Export
    # that page directly instead of opening a native Save As dialog, which
    # would detach the browser flow and leave the consultation waiting.
    page.evaluate("window.print = () => {}; ")
    print_button.click()
    page.pdf(path=str(target), format="A4", print_background=True, prefer_css_page_size=True)
    _validate_pdf_file(target, "FGTS")


def _wait_for_url_fragment(page, fragment: str, site_name: str, timeout_ms: int = 15000) -> None:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        if fragment in page.url:
            return
        page.wait_for_timeout(200)
    raise SiteAutomationError(f"{site_name}: o portal não avançou para a etapa esperada ({fragment}).")


def _click_required(page, selectors: list[str], error_message: str):
    locator = _wait_for_visible_locator(page, selectors)
    if locator is None:
        raise SiteAutomationError(error_message)
    locator.click()
    return locator


def _required_locator(page, selectors: list[str], error_message: str):
    locator = _wait_for_visible_locator(page, selectors)
    if locator is None:
        raise SiteAutomationError(error_message)
    return locator


def _save_page_as_pdf(page, target: Path, site_name: str) -> None:
    try:
        page.pdf(path=str(target), format="A4", print_background=True)
    except Exception as error:
        raise SiteAutomationError(f"{site_name}: não foi possível gerar o PDF da página oficial.") from error
    _validate_pdf_file(target, site_name)


def _validate_pdf_file(target: Path, site_name: str) -> None:
    if not target.is_file() or target.stat().st_size < 8 or target.read_bytes()[:5] != b"%PDF-":
        target.unlink(missing_ok=True)
        raise SiteAutomationError(f"{site_name}: a saída não é um PDF válido.")


def _download_from_click(page, locator, target: Path, site_name: str, timeout_ms: int = 15000) -> None:
    try:
        with page.expect_download(timeout=timeout_ms) as download_info:
            locator.click()
        download_info.value.save_as(target)
    except PlaywrightTimeoutError as error:
        raise SiteAutomationError(f"{site_name}: o portal não iniciou o download do PDF.") from error
    _validate_pdf_file(target, site_name)


def _handle_visible_captcha_if_present(
    page,
    site_code: str,
    flow: dict,
    on_status: StatusHandler,
    on_captcha: CaptchaHandler,
) -> bool:
    captcha = _captcha_kind(page, flow)
    if captcha is None:
        return False
    if flow.get("execution_mode") == "INTERNO":
        raise SiteAutomationError(
            "Desafio inesperado em portal INTERNO; consulta interrompida sem abrir janela nem contornar CAPTCHA."
        )
    on_status(site_code, "aguardando_captcha", None)
    _handle_human_captcha(page, site_code, flow, captcha, on_captcha)
    on_status(site_code, "rodando", None)
    return True


def _run_receita_cpf_macro(page, flow: dict, document: str, birth_date: str, target: Path) -> None:
    document_locator = _wait_for_visible_locator(page, flow["document"])
    birth_date_locator = _wait_for_visible_locator(page, flow["birth_date"])
    if document_locator is None or birth_date_locator is None:
        raise SiteAutomationError("Receita CPF: campo CPF/data de nascimento não localizado.")
    document_locator.fill(_formatted_document(re.sub(r"\D", "", document)))
    birth_date_locator.fill(datetime.strptime(birth_date, "%Y-%m-%d").strftime("%d/%m/%Y"))
    _click_required(page, flow["submit"], "Receita CPF: botão Consultar Certidão não localizado.")
    _wait_for_url_fragment(page, "/cpf/consultar", "Receita CPF")
    _click_required(page, flow["submit"], "Receita CPF: segundo botão Consultar Certidão não localizado.")
    _wait_for_url_fragment(page, "/cpf/consultar/resultado", "Receita CPF")
    download_button = _visible_locator(page, flow["latest_second_copy"])
    if download_button is None:
        raise SiteAutomationError("Receita CPF: ação 2ª Via da certidão mais recente não encontrada.")
    _download_from_click(page, download_button, target, "Receita CPF")


def _run_receita_cnpj_macro(page, flow: dict, document: str, target: Path) -> None:
    """Run the Receita CNPJ query flow without falling through to a different issuance path."""
    document_locator = _wait_for_visible_locator(page, flow["document"], timeout_ms=15000)
    if document_locator is None:
        raise SiteAutomationError("Receita CNPJ: campo CNPJ não localizado na página de consulta.")
    document_locator.fill(_formatted_document(re.sub(r"\D", "", document)))

    consult_button = _wait_for_visible_locator(page, flow["consult"], timeout_ms=15000)
    if consult_button is None:
        raise SiteAutomationError("Receita CNPJ: botão Consultar Certidão não localizado.")
    consult_button.click()

    def wait_for_state(page, state_keys: tuple[str, ...], timeout_ms: int, timeout_message: str) -> str:
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            error_notice = _visible_locator(page, flow.get("query_error", []))
            if error_notice is not None:
                try:
                    error_text = error_notice.inner_text()
                except Exception:
                    error_text = ""
                if "023" in error_text:
                    raise SiteAutomationError(
                        "Receita CNPJ: portal oficial retornou erro 023 e informou que não foi possível "
                        "concluir agora; tente novamente em alguns minutos. Nenhum PDF foi emitido."
                    )
                raise SiteAutomationError(
                    "Receita CNPJ: o portal oficial informou que não foi possível concluir a consulta. "
                    "Nenhum PDF foi emitido."
                )
            for state_key in state_keys:
                if _visible_locator(page, flow[state_key]) is not None:
                    return state_key
            page.wait_for_timeout(250)
        raise SiteAutomationError(timeout_message)

    first_state = wait_for_state(
        page,
        ("query_form", "latest_second_copy", "query_results"),
        timeout_ms=flow.get("query_form_timeout_ms", 30000),
        timeout_message=(
            "Receita CNPJ: após a primeira consulta, o formulário 'Data Inicial' não apareceu. "
            "O fluxo foi interrompido nessa etapa; nenhuma emissão alternativa foi iniciada."
        ),
    )

    if first_state == "latest_second_copy":
        download_button = _visible_locator(page, flow["latest_second_copy"])
        _download_from_click(page, download_button, target, "Receita CNPJ")
        return

    if first_state == "query_form":
        query_submit = _wait_for_visible_locator(page, flow["query_submit"], timeout_ms=15000)
        if query_submit is None:
            raise SiteAutomationError("Receita CNPJ: botão da segunda consulta não localizado após 'Data Inicial'.")
        query_submit.click()

    wait_for_state(
        page,
        ("query_results",),
        timeout_ms=flow.get("query_results_timeout_ms", 30000),
        timeout_message="Receita CNPJ: tabela de certidões emitidas não apareceu após a consulta.",
    )
    download_button = _wait_for_visible_locator(page, flow["latest_second_copy"], timeout_ms=15000)
    if download_button is None:
        raise SiteAutomationError("Receita CNPJ: ação '2ª Via' da certidão mais recente não localizada.")
    _download_from_click(page, download_button, target, "Receita CNPJ")


def _run_cndt_macro(page, flow: dict, document: str, target: Path, on_status, on_captcha) -> None:
    document_locator = _wait_for_visible_locator(
        page,
        flow["document"],
        timeout_ms=flow.get("document_timeout_ms", 30000),
    )
    if document_locator is None:
        raise SiteAutomationError(
            "CNDT: o formulário do serviço oficial não respondeu em cndt-certidao.tst.jus.br "
            "ou o campo CPF/CNPJ mudou; nenhuma emissão foi iniciada."
        )
    document_locator.fill(_formatted_document(re.sub(r"\D", "", document)))
    _required_locator(page, flow["submit"], "CNDT: botão Emitir Certidão não localizado.")

    downloads = []
    # Playwright wraps Python callbacks and stores bookkeeping on the callable;
    # built-in bound methods such as list.append do not allow that attribute.
    page.on("download", lambda download: downloads.append(download))
    page.bring_to_front()
    on_status("cndt", "aguardando_captcha", None)
    answer = on_captcha("cndt", "imagem", None, None)
    if answer is None:
        raise SiteAutomationError("CNDT: o operador não confirmou a emissão dentro do prazo de cinco minutos.")

    on_status("cndt", "rodando", None)
    deadline = time.monotonic() + 300
    while not downloads and time.monotonic() < deadline:
        page.wait_for_timeout(250)
    if not downloads:
        raise SiteAutomationError("CNDT: nenhum PDF foi baixado. Na aba do TST, preencha o CAPTCHA e clique em Emitir Certidão antes de confirmar no painel.")
    try:
        downloads[0].save_as(target)
    except Exception as error:
        raise SiteAutomationError("CNDT: não foi possível salvar o PDF iniciado pelo operador.") from error
    _validate_pdf_file(target, "CNDT")


def _run_cgu_macro(page, flow: dict, document: str, target: Path, on_status, on_captcha) -> None:
    try:
        login_required = "Para continuar, é necessário fazer o login" in page.locator("body").inner_text()
    except Exception:
        login_required = False
    if login_required or "/signin" in page.url:
        raise SiteAutomationError("CGU: o portal oficial exige sessão autenticada. Entre no portal e execute novamente; não foram enviados dados nem emitida certidão.")
    _click_required(page, flow["private_entity"], "CGU: opção Ente Privado não encontrada.")
    checkbox = _visible_locator(page, flow["negative_certificate"])
    if checkbox is None:
        raise SiteAutomationError("CGU: seleção da Certidão Negativa Correcional não encontrada.")
    label = page.locator("label:has-text('Certidão Negativa Correcional')").first
    if label.count() and label.is_visible():
        label.click()
    else:
        checkbox.check()
    document_locator = _wait_for_visible_locator(page, flow["document"])
    if document_locator is None:
        raise SiteAutomationError("CGU: campo CPF/CNPJ não localizado.")
    document_locator.fill(re.sub(r"\D", "", document))
    _click_required(page, flow["submit"], "CGU: botão Consultar não localizado.")
    _handle_visible_captcha_if_present(page, "ceis_cgu", flow, on_status, on_captcha)
    _wait_for_url_fragment(page, flow["result_url"], "CGU", timeout_ms=20000)
    certificate_button = _visible_locator(page, flow["certificate_button"])
    if certificate_button is None:
        raise SiteAutomationError("CGU: botão Certidão não encontrado na página de resultados.")
    _download_from_click(page, certificate_button, target, "CGU")


def _run_cartao_cnpj_macro(page, flow: dict, document: str, target: Path, on_status, on_captcha) -> None:
    document_locator = _wait_for_visible_locator(page, flow["document"])
    if document_locator is None:
        raise SiteAutomationError("Comprovante CNPJ: campo CNPJ não localizado.")
    document_locator.fill(re.sub(r"\D", "", document))
    _handle_visible_captcha_if_present(page, "cartao_cnpj", flow, on_status, on_captcha)
    _click_required(page, flow["submit"], "Comprovante CNPJ: botão CONSULTAR não localizado.")
    if _handle_visible_captcha_if_present(page, "cartao_cnpj", flow, on_status, on_captcha):
        _click_required(page, flow["submit"], "Comprovante CNPJ: botão CONSULTAR sumiu após resolver o CAPTCHA.")
    _wait_for_url_fragment(page, flow["result_url"], "Comprovante CNPJ", timeout_ms=20000)
    _save_page_as_pdf(page, target, "Comprovante CNPJ")


def _run_tcu_macro(page, flow: dict, document: str, document_type: str, target: Path) -> None:
    if document_type == "CPF":
        _click_required(page, flow["cpf_toggle"], "TCU: opção CPF não localizada.")
    document_locator = _wait_for_visible_locator(page, flow["document"])
    if document_locator is None:
        raise SiteAutomationError("TCU: campo CPF/CNPJ não localizado.")
    document_locator.fill(re.sub(r"\D", "", document))
    _click_required(page, flow["submit"], "TCU: botão Emitir certidão não localizado.")
    download_button = _wait_for_visible_locator(page, flow["download_button"], timeout_ms=20000)
    if download_button is None:
        raise SiteAutomationError("TCU: botão Baixar Certidão não apareceu após a consulta.")
    _download_from_click(page, download_button, target, "TCU")


def _run_simples_nacional_macro(page, flow: dict, document: str, target: Path, on_status, on_captcha) -> None:
    document_locator = _wait_for_visible_locator(page, flow["document"])
    if document_locator is None:
        raise SiteAutomationError("Simples Nacional: campo CNPJ não localizado.")
    document_locator.fill(re.sub(r"\D", "", document))
    _handle_visible_captcha_if_present(page, "simples_nacional", flow, on_status, on_captcha)
    _click_required(page, flow["submit"], "Simples Nacional: botão Consultar não localizado.")
    _handle_visible_captcha_if_present(page, "simples_nacional", flow, on_status, on_captcha)
    if _wait_for_visible_locator(page, flow["result_notice"], timeout_ms=20000) is None:
        raise SiteAutomationError("Simples Nacional: resultado Situação Atual não apareceu.")
    more_info = _visible_locator(page, flow["more_info"])
    if more_info is not None:
        more_info.click()
    generate_pdf = _visible_locator(page, flow["generate_pdf"])
    if generate_pdf is None:
        _save_page_as_pdf(page, target, "Resultado oficial do Simples Nacional")
        return
    _download_from_click(page, generate_pdf, target, "Simples Nacional")


def _run_sicaf_token_flow(page, document: str, target: Path, on_status, on_captcha) -> None:
    on_status("sicaf", "aguardando_captcha", "Autentique com certificado digital/token e deixe a certidão aberta para impressão.")
    answer = on_captcha("sicaf", "token", None, None)
    if answer is None:
        raise SiteAutomationError("SICAF: autenticação por certificado/token não foi concluída em cinco minutos.")
    on_status("sicaf", "rodando", None)
    try:
        page_text = page.locator("body").inner_text().lower()
    except Exception as error:
        raise SiteAutomationError("SICAF: não foi possível validar a página após a autenticação.") from error
    page_digits = re.sub(r"\D", "", page_text)
    if "certid" not in page_text or re.sub(r"\D", "", document) not in page_digits:
        raise SiteAutomationError("SICAF: autenticação confirmada, mas nenhuma tela de certidão está aberta; não será exportado o painel inicial.")
    _save_page_as_pdf(page, target, "SICAF")


def _fgts_portal_error(page) -> str | None:
    try:
        title = page.title()
        body = page.locator("body").inner_text()
    except Exception:
        return None

    title_lower = title.lower()
    body_lower = body.lower()

    if "shieldsquare" in title_lower or "shieldsquare" in body_lower or "bot protection" in body_lower:
        return (
            "Portal FGTS bloqueado pela proteção anti-bot do site da Caixa (ShieldSquare). "
            "Use o navegador do operador conectado via CDP e acesse a página manualmente; "
            "não é possível continuar em headless."
        )

    if "azion" not in title_lower or not re.search(r"Status Code\s*504", body, re.IGNORECASE):
        return None
    request_id = re.search(r"Request ID\s*([a-f0-9]+)", body, re.IGNORECASE)
    request_detail = f" Solicitação: {request_id.group(1)}." if request_id else ""
    return f"Portal FGTS indisponível: a Azion retornou HTTP 504.{request_detail}"


def _prepare_site_submission(
    page,
    flow: dict,
    site_code: str,
    document: str,
    on_status: StatusHandler,
    on_captcha: CaptchaHandler,
):
    if site_code != "inelegibilidade_cnj":
        submit_locator = _visible_locator(page, flow["submit"])
        if submit_locator is None:
            raise SiteAutomationError("Botão de emissão não localizado; o portal pode ter alterado o formulário.")
        return submit_locator

    search_locator = _visible_locator(page, flow["search"])
    if search_locator is None:
        raise SiteAutomationError("Botão Pesquisar do CNJ não localizado.")
    search_locator.click()
    try:
        page.wait_for_function(
            """() => ['btnCertidaoNegativa', 'btnCertidaoPositiva'].some(id => {
              const element = document.getElementById(id);
              return element && (element.offsetWidth > 0 || element.offsetHeight > 0);
            })""",
            timeout=30000,
        )
    except PlaywrightTimeoutError as error:
        raise SiteAutomationError("A pesquisa CNJ não apresentou uma opção de certidão em 30 segundos.") from error

    negative_button = _visible_locator(page, flow["submit"])
    if negative_button is not None:
        return negative_button
    if _visible_locator(page, flow["positive_result"]):
        raise SiteAutomationError("O CNJ apresentou opção de certidão positiva; a emissão negativa não foi iniciada.")
    raise SiteAutomationError("O CNJ não disponibilizou o botão de certidão negativa após a pesquisa.")


def _handle_human_captcha(
    page,
    site_code: str,
    flow: dict,
    captcha: tuple[str, str],
    captcha_handler: CaptchaHandler,
) -> None:
    kind, _selector = captcha
    image_base64 = None
    input_selector = None

    page.bring_to_front()
    answer = captcha_handler(site_code, kind, image_base64, input_selector)
    if answer is None:
        raise SiteAutomationError("O captcha não foi resolvido dentro do prazo.")

    if kind == "token":
        return

    if kind == "imagem":
        input_locator = _visible_locator(page, flow.get("captcha_input", []))
        if input_locator is None or not input_locator.input_value().strip():
            raise SiteAutomationError("Confirme o CAPTCHA somente depois de resolvê-lo na aba oficial do portal.")
        return

    # reCAPTCHA/hCaptcha are completed in the visible portal window; tokens are never injected.
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        response_selectors = [
            "textarea[name='g-recaptcha-response']",
            "textarea[name='h-captcha-response']",
            "textarea[name='altcha-response']",
        ]
        scopes = [page]
        try:
            scopes.extend(frame for frame in page.frames if frame != page.main_frame)
        except Exception:
            pass
        response_present = False
        for scope in scopes:
            for selector in response_selectors:
                try:
                    fields = scope.locator(selector)
                    for index in range(fields.count()):
                        if fields.nth(index).input_value().strip():
                            response_present = True
                            break
                except Exception:
                    continue
                if response_present:
                    break
            if response_present:
                break
        if response_present:
            return
        page.wait_for_timeout(500)
    raise SiteAutomationError("O desafio interativo não foi concluído no portal.")


def run_site(
    consultation_id: str,
    site_code: str,
    document: str,
    on_status: StatusHandler,
    on_captcha: CaptchaHandler,
    output_root: Path | str | None = None,
    headless: bool | None = None,
    additional_data: dict | None = None,
) -> dict:
    if sync_playwright is None:
        raise SiteAutomationError(
            "Playwright indisponível no ambiente atual: a automação do navegador foi bloqueada pelo Windows "
            "(dependência nativa greenlet/playwright). A API pode iniciar, mas a execução dos portais precisa "
            "do módulo liberado antes de usar a consulta automatizada."
        ) from _PLAYWRIGHT_IMPORT_ERROR

    flow = SITE_FLOWS.get(site_code)
    if flow is None:
        raise SiteAutomationError(f"Portal não configurado: {site_code}")
    execution_mode = flow.get("execution_mode", "INTERNO")

    on_status(site_code, "rodando", None)
    target_root = (
        create_consultation_directory(re.sub(r"\D", "", document))[0]
        if output_root is None
        else resolve_project_path(output_root)
    )
    target_root.mkdir(parents=True, exist_ok=True)
    target = target_root / f"{flow.get('file_id', site_code)}.pdf"
    target.parent.mkdir(parents=True, exist_ok=True)
    browser = None
    context = None
    page = None
    owns_browser = execution_mode == "INTERNO"
    visible_slot_kind = None

    try:
        if execution_mode in {"VISÍVEL", "VISÍVEL/CAPTCHA", "TOKEN"}:
            visible_slot_kind = _visible_browser_slot_kind(site_code, document)
            _acquire_visible_browser_slot(visible_slot_kind)
        with sync_playwright() as playwright:
            if execution_mode in {"VISÍVEL", "VISÍVEL/CAPTCHA", "TOKEN"}:
                cdp_url = get_env_var("CERTHUB_CDP_URL", "") or "http://127.0.0.1:9222"
                try:
                    browser = _connect_with_cdp_fallback(playwright, cdp_url)
                except Exception as error:
                    if "ECONNREFUSED" in str(error).upper():
                        raise SiteAutomationError(
                            "Chrome do operador não está acessível via CDP. Inicie o Chrome com "
                            "--remote-debugging-port=9222 ou ajuste CERTHUB_CDP_URL para a porta configurada; "
                            "depois tente novamente."
                        ) from error
                    raise
                if not browser.contexts:
                    raise SiteAutomationError("O navegador conectado por CDP não possui um contexto ativo.")
                context = browser.contexts[0]
                page = _reuse_visible_page(
                    context,
                    flow,
                    force_new=visible_slot_kind == "parallel-cnpj-captcha",
                )
            else:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(accept_downloads=True)
                page = context.new_page()
            pdf_responses = []

            def collect_pdf_response(response):
                pdf_responses.append(response)

            page.on("response", collect_pdf_response)
            page.goto(flow["url"], wait_until="domcontentloaded", timeout=60000)
            _dismiss_cookie_consent(page)
            _prepare_site_entry(page, flow)

            if site_code == "sicaf":
                _run_sicaf_token_flow(page, document, target, on_status, on_captcha)
                return _build_pdf_result(site_code, flow, target)

            if site_code == "receita_inss_cpf":
                birth_date = (additional_data or {}).get("data_nascimento", "")
                if not birth_date:
                    raise SiteAutomationError("Receita CPF: a data de nascimento é obrigatória.")
                _run_receita_cpf_macro(page, flow, document, birth_date, target)
                return _build_pdf_result(site_code, flow, target)

            if site_code == "receita_inss_cnpj":
                _run_receita_cnpj_macro(page, flow, document, target)
                return _build_pdf_result(site_code, flow, target)

            if site_code == "cndt":
                _run_cndt_macro(page, flow, document, target, on_status, on_captcha)
                return _build_pdf_result(site_code, flow, target)

            if site_code == "ceis_cgu":
                _run_cgu_macro(page, flow, document, target, on_status, on_captcha)
                return _build_pdf_result(site_code, flow, target)

            if site_code == "cartao_cnpj":
                _run_cartao_cnpj_macro(page, flow, document, target, on_status, on_captcha)
                return _build_pdf_result(site_code, flow, target)

            if site_code == "tcu_inidoneos":
                _run_tcu_macro(page, flow, document, (additional_data or {}).get("tipo", "CNPJ"), target)
                return _build_pdf_result(site_code, flow, target)

            if site_code == "simples_nacional":
                _run_simples_nacional_macro(page, flow, document, target, on_status, on_captcha)
                return _build_pdf_result(site_code, flow, target)

            if site_code == "fgts":
                _run_fgts_macro(page, flow, document, target)
                _validate_pdf_file(target, "FGTS")
                return _build_pdf_result(site_code, flow, target)

            document_locator = _wait_for_visible_locator(page, flow["document"])
            if document_locator is None:
                raise SiteAutomationError("Campo CPF/CNPJ não localizado; o portal pode ter alterado o formulário.")
            document_value = re.sub(r"\D", "", document) if flow.get("digits_only") else _formatted_document(document) if flow.get("format_document") else document
            document_locator.fill(document_value)

            captcha = _captcha_kind(page, flow)
            if captcha:
                if execution_mode == "INTERNO":
                    raise SiteAutomationError(
                        "Desafio inesperado em portal INTERNO; consulta interrompida sem abrir janela nem contornar CAPTCHA."
                    )
                _handle_human_captcha(page, site_code, flow, captcha, on_captcha)

            submit_locator = _prepare_site_submission(
                page, flow, site_code, document, on_status, on_captcha
            )

            downloaded = None
            for submit_attempt in range(2):
                try:
                    with page.expect_download(timeout=12000) as download_info:
                        submit_locator.click()
                    downloaded = download_info.value
                    break
                except PlaywrightTimeoutError:
                    captcha = _captcha_kind(page, flow)
                    if captcha is None:
                        break
                    if execution_mode == "INTERNO":
                        raise SiteAutomationError(
                            "Desafio inesperado em portal INTERNO; consulta interrompida sem abrir janela nem contornar CAPTCHA."
                        )
                    on_status(site_code, "aguardando_captcha", None)
                    _handle_human_captcha(page, site_code, flow, captcha, on_captcha)
                    on_status(site_code, "rodando", None)
                    submit_locator = _visible_locator(page, flow["submit"])
                    if submit_locator is None:
                        break

            suggested_filename = None
            if downloaded is not None:
                downloaded.save_as(target)
                suggested_filename = downloaded.suggested_filename
            else:
                for response in pdf_responses:
                    try:
                        content_type = response.headers.get("content-type", "").lower()
                        if "pdf" not in content_type:
                            continue
                        content = response.body()
                        if content.startswith(b"%PDF-"):
                            target.write_bytes(content)
                            suggested_filename = Path(response.url.split("?", 1)[0]).name or f"{site_code}.pdf"
                            break
                    except Exception:
                        continue
            if suggested_filename is None:
                raise SiteAutomationError("O portal não iniciou o download de uma certidão PDF.")
            if not target.is_file() or target.stat().st_size < 8 or target.read_bytes()[:5] != b"%PDF-":
                target.unlink(missing_ok=True)
                raise SiteAutomationError("O arquivo baixado não é um PDF válido.")

            result = {
                "site_codigo": site_code,
                "site_url": flow["url"],
                "pdf_path": str(target.resolve()),
                "pdf_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "arquivo": target.name,
            }
            return result
    except SiteAutomationError:
        raise
    except Exception as error:
        raise SiteAutomationError(f"Falha ao consultar o portal: {_safe_error_detail(error)}") from error
    finally:
        if owns_browser and context is not None:
            try:
                context.close()
            except Exception:
                pass
        if owns_browser and browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        elif page is not None and execution_mode not in {"VISÍVEL", "VISÍVEL/CAPTCHA", "TOKEN"}:
            try:
                page.close()
            except Exception:
                pass
        if visible_slot_kind is not None:
            _release_visible_browser_slot(visible_slot_kind)


def _build_pdf_result(site_code: str, flow: dict, target: Path) -> dict:
    _validate_pdf_file(target, site_code)
    content = target.read_bytes()
    return {
        "site_codigo": site_code,
        "site_url": flow["url"],
        "pdf_path": str(target.resolve()),
        "pdf_sha256": hashlib.sha256(content).hexdigest(),
        "arquivo": target.name,
    }