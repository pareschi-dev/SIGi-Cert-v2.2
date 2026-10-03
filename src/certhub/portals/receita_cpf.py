from __future__ import annotations

from certhub.portals.base_portal import BasePortal


class ReceitaCPFPortal(BasePortal):
    name = "receita_cpf"
    url = "https://servicos.receitafederal.gov.br/servico/certidoes/#/home/cpf#"

    def __init__(self, request=None):
        super().__init__(request)

    def emit(self):
        self.validate()
        if not self.request.additional_data.get("data_nascimento"):
            raise ValueError("A data de nascimento é obrigatória para Receita CPF.")
        return self.unimplemented_result()
