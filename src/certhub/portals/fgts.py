from __future__ import annotations

from certhub.core.models import EmissionRequest, EmissionResult
from certhub.portals.base_portal import BasePortal


class FGTSPortal(BasePortal):
    name = "fgts"
    url = "https://consulta-crf.caixa.gov.br/consultacrf/pages/consultaEmpregador.jsf"

    def __init__(self, request: EmissionRequest | None = None):
        super().__init__(request)

    def emit(self) -> EmissionResult:
        self.validate()
        return self.unimplemented_result()
