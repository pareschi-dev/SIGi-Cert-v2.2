from __future__ import annotations

from certhub.portals.base_portal import BasePortal


class CNJPortal(BasePortal):
    name = "cnj"
    url = "https://www.cnj.jus.br/improbidade_adm/consultar_requerido.php?validar=form"

    def __init__(self, request=None):
        super().__init__(request)

    def emit(self):
        self.validate()
        return self.unimplemented_result()
