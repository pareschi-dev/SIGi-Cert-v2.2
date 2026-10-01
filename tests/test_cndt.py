from certhub.core.models import EmissionRequest
from certhub.portals.cndt import CNDTPortal


def test_cndt_emits_valid_cnpj_with_pdf():
    result = CNDTPortal(EmissionRequest(portal="cndt", document="12.345.678/0001-95")).emit()
    assert result.success is True
    assert result.captcha_type == "text"
    assert result.captcha_method == "ocr_solver"
    assert result.pdf_path is not None
    assert result.pdf_hash is not None
