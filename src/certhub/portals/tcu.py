from __future__ import annotations

from certhub.portals.base_portal import BasePortal


class TCUPortal(BasePortal):
    name = "tcu"
    url = "https://certidoes.apps.tcu.gov.br/emitir-certidao-inidoneos"

    def __init__(self, request=None):
        super().__init__(request)

    def emit(self):
        self.validate()
        return self.unimplemented_result()
