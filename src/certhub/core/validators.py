from __future__ import annotations

import re


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def validate_cpf(value: str) -> bool:
    digits = _digits(value)
    if len(digits) != 11 or digits == digits[0] * len(digits):
        return False

    def calc_digit(numbers: str, weight: int) -> int:
        total = sum(int(d) * w for d, w in zip(numbers, range(weight, 1, -1)))
        remainder = total % 11
        return 0 if remainder < 2 else 11 - remainder

    digits_9 = digits[:9]
    d1 = calc_digit(digits_9, 10)
    d2 = calc_digit(digits_9 + str(d1), 11)
    return digits == digits_9 + str(d1) + str(d2)


def validate_cnpj(value: str) -> bool:
    digits = _digits(value)
    if len(digits) != 14 or digits == digits[0] * len(digits):
        return False

    def calc_digit(numbers: str, weights: list[int]) -> int:
        total = sum(int(d) * w for d, w in zip(numbers, weights))
        remainder = total % 11
        return 0 if remainder < 2 else 11 - remainder

    weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    weights2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]

    d1 = calc_digit(digits[:12], weights1)
    d2 = calc_digit(digits[:12] + str(d1), weights2)
    check = digits[12:]
    return check == f"{d1}{d2}"


def mask_document(value: str) -> str:
    digits = _digits(value)
    if len(digits) == 11:
        return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"
    if len(digits) == 14:
        return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"
    return value


def guess_document_type(value: str) -> str:
    digits = _digits(value)
    if len(digits) == 11:
        return "cpf"
    if len(digits) == 14:
        return "cnpj"
    raise ValueError("Documento inválido: informe CPF ou CNPJ.")
