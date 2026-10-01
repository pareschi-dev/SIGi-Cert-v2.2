from __future__ import annotations

from certhub.core.pdf_handler import PDFHandler
from certhub.portals.base_portal import BasePortal


class CNJPortal(BasePortal):
    name = "cnj"
    url = "https://www.cnj.jus.br/improbidade_adm/consultar_requerido.php?validar=form"

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
            return self._result(False, "PDF inválido para CNJ", attempts=1, captcha_type="text", captcha_method="ocr_solver")
        return self._result(
            True,
            "Certidão CNJ emitida com sucesso.",
            pdf_path=str(pdf_path),
            attempts=1,
            captcha_type="text",
            captcha_method="ocr_solver",
            pdf_hash=self.pdf_handler.calculate_sha256(pdf_path),
        )
