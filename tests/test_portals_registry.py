from certhub.main import PORTAL_REGISTRY


def test_todos_portais_registrados():
    esperados = {
        "fgts",
        "cndt",
        "receita_cnpj",
        "receita_cpf",
        "simples_nacional",
        "ceis",
        "cnj",
        "tcu",
        "cartao_cnpj",
        "sicaf",
    }
    assert set(PORTAL_REGISTRY.keys()) == esperados
