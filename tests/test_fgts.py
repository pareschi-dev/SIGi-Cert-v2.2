from typer.testing import CliRunner
import pytest

from certhub.core.models import EmissionRequest
from certhub.main import app
from certhub.portals.fgts import FGTSPortal

runner = CliRunner()
VALID_CNPJ = "12.345.678/0001-95"


class FakeLocator:
    def __init__(self):
        self.first = self

    def count(self):
        return 1

    def fill(self, value):
        self.value = value

    def click(self, timeout=5000):
        pass


class FakePage:
    def locator(self, selector):
        return FakeLocator()

    def goto(self, url, wait_until=None):
        self.url = url


class FakeBrowserSession:
    def __init__(self, headless=True):
        self.page = None

    def start(self):
        self.page = FakePage()
        return self.page

    def close(self):
        self.page = None


@pytest.fixture(autouse=True)
def prevent_external_portal_access(monkeypatch):
    monkeypatch.setattr("certhub.portals.base_portal.BrowserSession", FakeBrowserSession)


def test_legacy_fgts_wrapper_never_claims_a_synthetic_certificate():
    result = FGTSPortal(EmissionRequest(portal="fgts", document=VALID_CNPJ)).emit()
    assert result.success is False
    assert result.pdf_path is None
    assert "não está implementado" in result.message


def test_cli_routes_sicaf_to_token_assisted_flow(monkeypatch, tmp_path):
    called = {}

    def fake_run_site(consultation_id, site_code, *args, **kwargs):
        called["site_code"] = site_code
        return {"arquivo": "compras_gov.pdf", "pdf_path": str(tmp_path / "compras_gov.pdf"), "pdf_sha256": "a" * 64}

    monkeypatch.setattr("certhub.main.run_site", fake_run_site)
    response = runner.invoke(app, ["emitir", "--portal", "sicaf", "--documento", VALID_CNPJ])
    assert response.exit_code == 0
    assert called["site_code"] == "sicaf"


@pytest.mark.parametrize(
    ("portal", "expected_flow"),
    [("cnj", "inelegibilidade_cnj"), ("receita_cnpj", "receita_inss_cnpj"), ("fgts", "fgts")],
)
def test_cli_uses_implemented_macro(monkeypatch, tmp_path, portal, expected_flow):
    pdf_path = tmp_path / "certidao.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%test\n")
    called = {}

    def fake_run_site(consultation_id, site_code, *args, **kwargs):
        called["site_code"] = site_code
        return {
            "arquivo": "certidao.pdf",
            "pdf_path": str(pdf_path),
            "pdf_sha256": "a" * 64,
        }

    monkeypatch.setattr(
        "certhub.main.run_site",
        fake_run_site,
    )
    response = runner.invoke(app, ["emitir", "--portal", portal, "--documento", VALID_CNPJ])
    assert response.exit_code == 0
    assert called["site_code"] == expected_flow
    assert "PDF baixado e validado" in response.stdout
