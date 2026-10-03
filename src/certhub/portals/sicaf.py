from __future__ import annotations

from certhub.portals.base_portal import BasePortal


class SICAFPortal(BasePortal):
    name = "sicaf"
    url = "https://comprasnet.gov.br/seguro/loginPortalUASG.asp"

    def __init__(self, request=None):
        super().__init__(request)

    def emit(self):
        self.validate()
        return self.unimplemented_result()
