from __future__ import annotations

from certhub.portals.base_portal import BasePortal


class ReceitaCNPJPortal(BasePortal):
    name = "receita_cnpj"
    url = "https://servicos.receitafederal.gov.br/servico/certidoes/#/home/cnpj#"

    def __init__(self, request=None):
        super().__init__(request)

    def emit(self):
        self.validate()
        return self.unimplemented_result()
