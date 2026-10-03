from __future__ import annotations

from certhub.portals.base_portal import BasePortal


class CEISPortal(BasePortal):
    name = "ceis"
    url = "https://certidoes.cgu.gov.br/"

    def __init__(self, request=None):
        super().__init__(request)

    def emit(self):
        self.validate()
        return self.unimplemented_result()
