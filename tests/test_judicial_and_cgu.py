from certhub.core.models import EmissionRequest
from certhub.portals import CEISPortal, CNJPortal, SICAFPortal, TCUPortal, CartaoCNPJPortal


def test_portal_group_emits_pdf_artifacts():
    document = "12.345.678/0001-95"

    for portal_cls in (CEISPortal, CNJPortal, TCUPortal, CartaoCNPJPortal, SICAFPortal):
        result = portal_cls(EmissionRequest(portal=portal_cls.name, document=document)).emit()
        assert result.success is True
        assert result.pdf_path is not None
        assert result.pdf_hash is not None
