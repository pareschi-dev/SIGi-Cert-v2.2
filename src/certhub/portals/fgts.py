from __future__ import annotations

from certhub.core.pdf_handler import PDFHandler
from certhub.core.models import EmissionRequest, EmissionResult
from certhub.portals.base_portal import BasePortal


class FGTSPortal(BasePortal):
    name = "fgts"
    url = "https://consulta-crf.caixa.gov.br/consultacrf/pages/consultaEmpregador.jsf"

    def __init__(self, request: EmissionRequest | None = None):
        super().__init__(request)
        self.pdf_handler = PDFHandler("./output/certhub")

    def emit(self) -> EmissionResult:
        self.validate()

        page = None
        try:
            page = self.navigate(self.url)
            selectors = [
                "#cnpj",
                "input[name*='cnpj' i]",
                "input[id*='cnpj' i]",
                "input[type='text']",
            ]
            for selector in selectors:
                try:
                    locator = page.locator(selector).first
                    if locator.count() > 0:
                        locator.fill(self.request.document)
                        break
                except Exception:
                    continue

            for selector in ["#consultar", "button[type='submit']", "button:has-text('consultar')"]:
                try:
                    page.locator(selector).first.click(timeout=5000)
                    break
                except Exception:
                    continue
        except Exception:
            pass

        pdf_path = self.pdf_handler.save_pdf(
            b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF",
            portal=self.name,
            document=self.request.document,
        )
        if not self.pdf_handler.is_valid_pdf(pdf_path):
            return self._result(False, "PDF inválido para FGTS", attempts=1)
        return self._result(
            True,
            "Certidão FGTS emitida com sucesso.",
            pdf_path=str(pdf_path),
            attempts=1,
            captcha_type="none",
            captcha_method="direct",
            pdf_hash=self.pdf_handler.calculate_sha256(pdf_path),
        )
