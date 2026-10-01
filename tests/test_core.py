from pathlib import Path

from certhub.core.validators import validate_cnpj, validate_cpf
from certhub.core.pdf_handler import PDFHandler


def _valid_cpf():
    base = "123456789"
    total = sum(int(d) * w for d, w in zip(base, range(10, 1, -1)))
    d1 = 0 if total % 11 < 2 else 11 - (total % 11)
    total_2 = sum(int(d) * w for d, w in zip(base + str(d1), range(11, 1, -1)))
    d2 = 0 if total_2 % 11 < 2 else 11 - (total_2 % 11)
    return f"{base}{d1}{d2}"


def _valid_cnpj():
    base = "123456780001"
    weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    weights2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    total1 = sum(int(d) * w for d, w in zip(base, weights1))
    d1 = 0 if total1 % 11 < 2 else 11 - (total1 % 11)
    total2 = sum(int(d) * w for d, w in zip(base + str(d1), weights2))
    d2 = 0 if total2 % 11 < 2 else 11 - (total2 % 11)
    return f"{base}{d1}{d2}"


def test_validate_cnpj_success():
    valid = _valid_cnpj()
    assert validate_cnpj(valid) is True


def test_validate_cpf_success():
    valid = _valid_cpf()
    assert validate_cpf(valid) is True


def test_validate_cnpj_invalid():
    assert validate_cnpj("11.111.111/1111-11") is False


def test_pdf_handler_creates_valid_pdf(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF")

    handler = PDFHandler(output_dir=tmp_path)
    assert handler.is_valid_pdf(pdf_path) is True
    digest = handler.calculate_sha256(pdf_path)
    assert len(digest) == 64
