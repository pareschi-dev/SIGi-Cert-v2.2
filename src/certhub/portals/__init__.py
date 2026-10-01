"""Portal implementations."""

from .ceis import CEISPortal
from .cndt import CNDTPortal
from .cartao_cnpj import CartaoCNPJPortal
from .cnj import CNJPortal
from .fgts import FGTSPortal
from .receita_cnpj import ReceitaCNPJPortal
from .receita_cpf import ReceitaCPFPortal
from .sicaf import SICAFPortal
from .simples_nacional import SimplesNacionalPortal
from .tcu import TCUPortal

__all__ = [
    "FGTSPortal",
    "CNDTPortal",
    "ReceitaCNPJPortal",
    "ReceitaCPFPortal",
    "SimplesNacionalPortal",
    "CEISPortal",
    "CNJPortal",
    "TCUPortal",
    "CartaoCNPJPortal",
    "SICAFPortal",
]
