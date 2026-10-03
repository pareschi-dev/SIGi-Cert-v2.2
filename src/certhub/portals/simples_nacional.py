from __future__ import annotations

from certhub.portals.base_portal import BasePortal


class SimplesNacionalPortal(BasePortal):
    name = "simples_nacional"
    url = "https://www8.receita.fazenda.gov.br/simplesnacional/aplicacoes.aspx?id=21"

    def __init__(self, request=None):
        super().__init__(request)

    def emit(self):
        self.validate()
        return self.unimplemented_result()
