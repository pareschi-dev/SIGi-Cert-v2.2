from certhub.core.models import EmissionRequest
from certhub.portals import ReceitaCNPJPortal, ReceitaCPFPortal


def test_receita_cnpj_emits_valid_document_with_pdf():
    result = ReceitaCNPJPortal(
        EmissionRequest(portal="receita_cnpj", document="12.345.678/0001-95")
    ).emit()

    assert result.success is True
    assert result.captcha_type == "hcaptcha"
    assert result.captcha_method == "solver_fazenda_or_2captcha"
    assert result.pdf_path is not None
    assert result.pdf_hash is not None


def test_receita_cpf_emits_valid_document_with_pdf():
    result = ReceitaCPFPortal(
        EmissionRequest(
            portal="receita_cpf",
            document="529.982.247-25",
            additional_data={"data_nascimento": "2000-01-01"},
        )
    ).emit()

    assert result.success is True
    assert result.captcha_type == "hcaptcha"
    assert result.captcha_method == "solver_fazenda_or_2captcha"
    assert result.pdf_path is not None
    assert result.pdf_hash is not None
