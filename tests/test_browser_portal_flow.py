from certhub.core.models import EmissionRequest
from certhub.portals.fgts import FGTSPortal


def test_portal_can_navigate_and_detect_captcha_state():
    portal = FGTSPortal(EmissionRequest(portal="fgts", document="12.345.678/0001-95"))

    page = portal.open_browser()
    page.goto("https://example.com", wait_until="domcontentloaded")

    assert "Example Domain" in page.title()
    assert portal.detect_captcha(page.content()) == "none"
    assert portal.detect_captcha("<div class='h-captcha'></div>") == "hcaptcha"

    portal.close_browser()


def test_fgts_emit_runs_browser_flow_before_pdf_generation():
    portal = FGTSPortal(EmissionRequest(portal="fgts", document="12.345.678/0001-95"))
    portal.url = (
        "data:text/html,<html><body>"
        "<input id='cnpj' />"
        "<button id='consultar'>Consultar</button>"
        "</body></html>"
    )

    result = portal.emit()

    assert result.success is True
    assert result.pdf_path is not None
    assert portal.browser_session.page is not None
    portal.close_browser()
