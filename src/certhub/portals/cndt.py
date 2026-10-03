from __future__ import annotations

from certhub.portals.base_portal import BasePortal


class CNDTPortal(BasePortal):
    name = "cndt"
    url = "https://www.tst.jus.br/certidao"

    def __init__(self, request=None):
        super().__init__(request)

    def emit(self):
        self.validate()
        return self.unimplemented_result()
