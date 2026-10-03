from certhub.core.models import EmissionRequest
from certhub.portals.cndt import CNDTPortal


def test_legacy_cndt_wrapper_does_not_fabricate_a_pdf():
    result = CNDTPortal(EmissionRequest(portal="cndt", document="12.345.678/0001-95")).emit()
    assert result.success is False
    assert result.pdf_path is None
    assert result.pdf_hash is None
