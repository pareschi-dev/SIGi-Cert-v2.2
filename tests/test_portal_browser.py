from certhub.core.models import EmissionRequest
from certhub.portals.fgts import FGTSPortal


def test_base_portal_exposes_browser_session():
    portal = FGTSPortal(EmissionRequest(portal="fgts", document="12.345.678/0001-95"))

    assert portal.browser_session is not None
    page = portal.open_browser()
    assert page is not None

    portal.close_browser()
    assert portal.browser_session.page is None
