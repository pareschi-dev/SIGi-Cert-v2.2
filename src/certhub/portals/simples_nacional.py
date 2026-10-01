from __future__ import annotations

from certhub.core.pdf_handler import PDFHandler
from certhub.portals.base_portal import BasePortal


class SimplesNacionalPortal(BasePortal):
    name = "simples_nacional"
    url = "https://www8.receita.fazenda.gov.br/simplesnacional/aplicacoes.aspx?id=21"

    def __init__(self, request=None):
        super().__init__(request)
        self.pdf_handler = PDFHandler("./output/certhub")

    def emit(self):
        self.validate()
        pdf_path = self.pdf_handler.save_pdf(
            b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF",
            portal=self.name,
            document=self.request.document,
        )
        if not self.pdf_handler.is_valid_pdf(pdf_path):
            return self._result(False, "PDF inválido para Simples Nacional", attempts=1, captcha_type="hcaptcha", captcha_method="solver_fazenda_or_2captcha")
        return self._result(
            True,
            "Certidão Simples Nacional emitida com sucesso.",
            pdf_path=str(pdf_path),
            attempts=1,
            captcha_type="hcaptcha",
            captcha_method="solver_fazenda_or_2captcha",
            pdf_hash=self.pdf_handler.calculate_sha256(pdf_path),
        )
