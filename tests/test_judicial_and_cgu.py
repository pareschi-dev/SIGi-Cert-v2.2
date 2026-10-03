from certhub.core.models import EmissionRequest
from certhub.portals import CEISPortal, CNJPortal, SICAFPortal, TCUPortal, CartaoCNPJPortal


def test_legacy_portal_wrappers_never_claim_synthetic_success():
    document = "12.345.678/0001-95"

    for portal_cls in (CEISPortal, CNJPortal, TCUPortal, CartaoCNPJPortal, SICAFPortal):
        result = portal_cls(EmissionRequest(portal=portal_cls.name, document=document)).emit()
        assert result.success is False
        assert result.pdf_path is None
        assert result.pdf_hash is None
