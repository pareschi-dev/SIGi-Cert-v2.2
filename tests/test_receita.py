from certhub.core.models import EmissionRequest
from certhub.portals import ReceitaCNPJPortal, ReceitaCPFPortal


def test_legacy_receita_cnpj_wrapper_does_not_fabricate_a_pdf():
    result = ReceitaCNPJPortal(
        EmissionRequest(portal="receita_cnpj", document="12.345.678/0001-95")
    ).emit()

    assert result.success is False
    assert result.pdf_path is None
    assert result.pdf_hash is None


def test_legacy_receita_cpf_wrapper_does_not_fabricate_a_pdf():
    result = ReceitaCPFPortal(
        EmissionRequest(
            portal="receita_cpf",
            document="529.982.247-25",
            additional_data={"data_nascimento": "2000-01-01"},
        )
    ).emit()

    assert result.success is False
    assert result.pdf_path is None
    assert result.pdf_hash is None
