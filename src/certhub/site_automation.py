from __future__ import annotations

import base64
import hashlib
import os
import re
import time
from pathlib import Path
from typing import Callable

from certhub.config import load_certidoes_config

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
        "url": "https://comprasnet.gov.br/seguro/loginPortalUASG.asp",
        "document": ["input[name='cnpj']"],
        "submit": ["input[type='submit']"],
        "captcha_image": ["img#imgCaptcha"],
        "captcha_input": ["input[name='txtTexto_captcha_serpro_gov_br']"],
    },
    "receita_inss_cnpj": {
        "url": "https://servicos.receitafederal.gov.br/servico/certidoes/#/home/cnpj#",
        "document": ["input[name='niContribuinte']"],
        "emit": ["button:has-text('Emitir Certidão')"],
        "consult_existing": ["[role='dialog'] button:has-text('Consultar Certidão')"],
        "valid_certificate_notice": ["text=Certidão Válida Encontrada"],
        "result_table": ["table:has-text('Código de Controle')"],
        "latest_second_copy": [
            "table:has-text('Código de Controle') tbody tr:first-child td:last-child a",
            "table:has-text('Código de Controle') tbody tr:first-child td:last-child button",
            "table:has-text('Código de Controle') tbody tr:first-child td:last-child [role='button']",
        ],
        "format_document": True,
        "captcha_recaptcha": ["div.g-recaptcha", "iframe[src*='recaptcha']"],
        "captcha_hcaptcha": ["div.h-captcha", "iframe[src*='hcaptcha']"],
    },
    "receita_inss_cpf": {
        "url": "https://servicos.receitafederal.gov.br/servico/certidoes/#/home/cpf#",
        "document": ["input[name='cpf']", "input[id*='cpf' i]", "input[type='text']"],
        "submit": ["button[type='submit']"],
        "captcha_recaptcha": ["div.g-recaptcha", "iframe[src*='recaptcha']"],
    },
    "fgts": {
        "url": "https://consulta-crf.caixa.gov.br/consultacrf/pages/consultaEmpregador.jsf",
        "document": ["input[name='mainForm:txtInscricao1']"],
        "uf": ["select[name='mainForm:uf']"],
        "submit": ["input[name='mainForm:btnConsultar']"],
        "certificate_link": ["a:has-text('Obtenha o Certificado de Regularidade do FGTS - CRF')"],
        "visualize": ["input[type='button'][value='Visualizar']", "button:has-text('Visualizar')"],
        "print": ["input[type='button'][value='Imprimir']", "button:has-text('Imprimir')"],
        "digits_only": True,
    },
    "cndt": {
        "url": "https://www.tst.jus.br/certidao",
        "document": ["input[id='cpfCnpj']"],
        "submit": ["button[id='btnEmitir']", "button[type='submit']"],
        "captcha_image": ["img#captchaImg"],
        "captcha_input": ["input[name='captcha']"],
    },
    "inelegibilidade_cnj": {
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
        "url": "https://certidoes.cgu.gov.br/",
        "document": ["input[name='cpfCnpj']", "input[id*='cpfCnpj' i]"],
        "submit": ["button[type='submit']"],
        "captcha_image": ["img#imgCaptcha"],
        "captcha_input": ["input[name='captcha']"],
    },
    "cartao_cnpj": {
        "url": "https://solucoes.receita.fazenda.gov.br/servicos/cnpjreva/cnpjreva_solicitacao.asp",
        "document": ["input[name='cnpj']"],
        "submit": ["button[type='submit']", "input[type='submit']"],
        "captcha_recaptcha": ["div.g-recaptcha", "iframe[src*='recaptcha']"],
    },
    "tcu_inidoneos": {
        "url": "https://certidoes.apps.tcu.gov.br/emitir-certidao-inidoneos",
        "document": ["input[name='cpfCnpj']", "input[id*='cpfCnpj' i]"],
        "submit": ["button[type='submit']"],
        "captcha_image": ["img#captcha"],
        "captcha_input": ["input[name='captcha']"],
    },
    "simples_nacional": {
        "url": "https://www8.receita.fazenda.gov.br/simplesnacional/aplicacoes.aspx?id=21",
        "document": ["input[id='cnpj']", "input[name='cnpj']"],
        "submit": ["button[type='submit']", "input[type='submit']"],
        "captcha_hcaptcha": ["div.h-captcha", "iframe[src*='hcaptcha']"],
    },
}


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
        url = portal.get("url_inicial")
        if isinstance(url, str) and url:
            flow["url"] = url
        selectors = portal.get("seletores")
        if not isinstance(selectors, dict):
            continue
        selector_map = {
            "link_pessoa_juridica": "entry",
            "campo_cnpj": "document",
            "campo_documento": "document",
            "campo_inscricao": "document",
            "campo_uf": "uf",
            "botao_emitir": "emit",
            "botao_consultar_certidao": "consult_existing",
            "segunda_via": "latest_second_copy",
            "botao_pesquisar": "search",
            "botao_certidao_negativa": "submit",
            "botao_consultar": "submit",
            "link_crf": "certificate_link",
            "botao_visualizar": "visualize",
            "botao_imprimir": "print",
        }
        for config_key, flow_key in selector_map.items():
            selector = selectors.get(config_key)
            if isinstance(selector, str) and selector:
                flow[flow_key] = [part.strip() for part in selector.split(",") if part.strip()]
    return flows


SITE_FLOWS = _apply_certidoes_rules(SITE_FLOWS)

CaptchaHandler = Callable[[str, str, str | None, str | None], str | None]
StatusHandler = Callable[[str, str, str | None], None]


class SiteAutomationError(RuntimeError):
    pass


def _safe_error_detail(error: Exception) -> str:
    detail = str(error)
    detail = re.sub(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", "[CNPJ]", detail)
    detail = re.sub(r"\d{3}\.\d{3}\.\d{3}-\d{2}", "[CPF]", detail)
    detail = re.sub(r"(?<!\d)\d{11,14}(?!\d)", "[documento]", detail)
    return f"{type(error).__name__}: {detail}"[:400]


def _visible_locator(page, selectors: list[str]):
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if locator.count() and locator.is_visible():
                return locator
        except Exception:
            continue
    return None


def _wait_for_visible_locator(page, selectors: list[str], timeout_ms: int = 30000):
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


def _wait_for_receita_state(page, flow: dict, expected: str, on_status: StatusHandler, on_captcha: CaptchaHandler) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        selectors = flow["valid_certificate_notice"] if expected == "notice" else flow["result_table"]
        if _visible_locator(page, selectors) is not None:
            return
        captcha = _captcha_kind(page, flow)
        if captcha is not None:
            on_status("receita_inss_cnpj", "aguardando_captcha", None)
            _handle_human_captcha(page, "receita_inss_cnpj", flow, captcha, on_captcha)
        page.wait_for_timeout(250)
    if expected == "notice":
        raise SiteAutomationError("A Receita Federal não abriu o aviso de certidão válida nem a tela de resultados.")
    raise SiteAutomationError("A consulta da Receita Federal não exibiu a tabela de certidões.")


def _prepare_site_entry(page, flow: dict) -> None:
    entry_selectors = flow.get("entry", [])
    if not entry_selectors:
        return
    entry_locator = _visible_locator(page, entry_selectors)
    if entry_locator is not None:
        entry_locator.click()
        page.wait_for_timeout(250)


def _run_fgts_macro(page, flow: dict, document: str, target: Path) -> None:
    portal_error = _fgts_portal_error(page)
    if portal_error:
        raise SiteAutomationError(portal_error)

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

    deadline = time.monotonic() + 60000 / 1000
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

    visualize_button = _wait_for_visible_locator(page, flow["visualize"], timeout_ms=30000)
    if visualize_button is None:
        raise SiteAutomationError("Botão Visualizar do certificado FGTS não localizado.")
    visualize_button.click()

    print_button = _wait_for_visible_locator(page, flow["print"], timeout_ms=30000)
    if print_button is None:
        raise SiteAutomationError("Botão Imprimir do certificado FGTS não localizado.")
    page.evaluate("window.print = () => {};")
    print_button.click()
    page.pdf(path=str(target), print_background=True, prefer_css_page_size=True)


def _fgts_portal_error(page) -> str | None:
    try:
        title = page.title()
        body = page.locator("body").inner_text()
    except Exception:
        return None
    if "azion" not in title.lower() or not re.search(r"Status Code\s*504", body, re.IGNORECASE):
        return None
    request_id = re.search(r"Request ID\s*([a-f0-9]+)", body, re.IGNORECASE)
    request_detail = f" Solicitação: {request_id.group(1)}." if request_id else ""
    return f"Portal FGTS indisponível: a Azion retornou HTTP 504.{request_detail}"


def _prepare_site_submission(
    page,
    flow: dict,
    site_code: str,
    on_status: StatusHandler,
    on_captcha: CaptchaHandler,
):
    if site_code == "receita_inss_cnpj":
        consult_selectors = flow.get("consult", flow.get("consult_existing", []))
        consult_button = _wait_for_visible_locator(page, consult_selectors)
        if consult_button is None:
            raise SiteAutomationError("Botão Consultar Certidão da Receita Federal não localizado.")
        consult_button.click()

        second_consult_button = _wait_for_visible_locator(page, consult_selectors)
        if second_consult_button is None:
            raise SiteAutomationError("Segundo botão Consultar Certidão da Receita Federal não localizado.")
        captcha = _captcha_kind(page, flow)
        if captcha is not None:
            on_status(site_code, "aguardando_captcha", None)
            _handle_human_captcha(page, site_code, flow, captcha, on_captcha)
        second_consult_button.click()
        _wait_for_receita_state(page, flow, "results", on_status, on_captcha)

        download_button = _visible_locator(page, flow["latest_second_copy"])
        if download_button is None:
            raise SiteAutomationError("A seta da 2ª Via da certidão mais recente não foi localizada.")
        return download_button

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
    kind, selector = captcha
    image_base64 = None
    input_selector = None
    if kind == "imagem":
        input_selectors = flow.get("captcha_input", [])
        input_locator = _visible_locator(page, input_selectors)
        if input_locator is None:
            raise SiteAutomationError("Captcha de imagem detectado, mas o campo de resposta não foi encontrado.")
        input_selector = input_selectors[0]
        image_base64 = base64.b64encode(page.locator(selector).first.screenshot()).decode("ascii")

    page.bring_to_front()
    answer = captcha_handler(site_code, kind, image_base64, input_selector)
    if answer is None:
        raise SiteAutomationError("O captcha não foi resolvido dentro do prazo.")

    if kind == "imagem":
        page.locator(input_selector).fill(answer)
        return

    # reCAPTCHA/hCaptcha are completed in the visible portal window; tokens are never injected.
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        token_present = page.evaluate(
            """() => Array.from(document.querySelectorAll(
              'textarea[name="g-recaptcha-response"], textarea[name="h-captcha-response"]'
            )).some(element => element.value.trim().length > 0)"""
        )
        if token_present:
            return
        page.wait_for_timeout(500)
    raise SiteAutomationError("O desafio interativo não foi concluído no portal.")


def run_site(
    consultation_id: str,
    site_code: str,
    document: str,
    on_status: StatusHandler,
    on_captcha: CaptchaHandler,
    output_root: Path | str = "output/consultas",
    headless: bool | None = None,
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

    on_status(site_code, "rodando", None)
    if headless is None:
        headless = os.getenv("PLAYWRIGHT_HEADLESS", "false").lower() in {"1", "true", "yes"}
    target = Path(output_root) / consultation_id / f"{site_code}.pdf"
    target.parent.mkdir(parents=True, exist_ok=True)
    browser = None
    context = None

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=headless)
            context = browser.new_context(accept_downloads=True)
            page = context.new_page()
            pdf_responses = []

            def collect_pdf_response(response):
                pdf_responses.append(response)

            page.on("response", collect_pdf_response)
            page.goto(flow["url"], wait_until="domcontentloaded", timeout=60000)
            _prepare_site_entry(page, flow)

            if site_code == "fgts":
                _run_fgts_macro(page, flow, document, target)
                if not target.is_file() or target.stat().st_size < 8 or target.read_bytes()[:5] != b"%PDF-":
                    target.unlink(missing_ok=True)
                    raise SiteAutomationError("O certificado FGTS não foi salvo como PDF válido.")
                return {
                    "site_codigo": site_code,
                    "site_url": flow["url"],
                    "pdf_path": str(target.resolve()),
                    "pdf_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                    "arquivo": target.name,
                }

            document_locator = _wait_for_visible_locator(page, flow["document"])
            if document_locator is None:
                raise SiteAutomationError("Campo CPF/CNPJ não localizado; o portal pode ter alterado o formulário.")
            document_value = re.sub(r"\D", "", document) if flow.get("digits_only") else _formatted_document(document) if flow.get("format_document") else document
            document_locator.fill(document_value)

            captcha = _captcha_kind(page, flow)
            if captcha:
                _handle_human_captcha(page, site_code, flow, captcha, on_captcha)

            submit_locator = _prepare_site_submission(page, flow, site_code, on_status, on_captcha)

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
                    on_status(site_code, "aguardando_captcha", None)
                    _handle_human_captcha(page, site_code, flow, captcha, on_captcha)
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
                "arquivo": re.sub(r"[^A-Za-z0-9._-]", "_", suggested_filename),
            }
            return result
    except SiteAutomationError:
        raise
    except Exception as error:
        raise SiteAutomationError(f"Falha ao consultar o portal: {_safe_error_detail(error)}") from error
    finally:
        if context is not None:
            try:
                context.close()
            except Exception:
                pass
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass