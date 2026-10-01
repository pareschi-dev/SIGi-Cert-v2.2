from __future__ import annotations

import re


def limpar_documento(value: str) -> str:
    return re.sub(r"\D", "", str(value or ""))


def validar_cpf(value: str) -> bool:
    digits = limpar_documento(value)
    if len(digits) != 11 or digits == digits[0] * 11:
        return False

    def calc(numbers: str, weight: int) -> int:
        total = sum(int(d) * w for d, w in zip(numbers, range(weight, 1, -1)))
        remainder = total % 11
        return 0 if remainder < 2 else 11 - remainder

    d1 = calc(digits[:9], 10)
    d2 = calc(digits[:9] + str(d1), 11)
    return digits == digits[:9] + str(d1) + str(d2)


def validar_cnpj(value: str) -> bool:
    digits = limpar_documento(value)
    if len(digits) != 14 or digits == digits[0] * 14:
        return False

    def calc(numbers: str, weights: list[int]) -> int:
        total = sum(int(d) * w for d, w in zip(numbers, weights))
        remainder = total % 11
        return 0 if remainder < 2 else 11 - remainder

    weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    weights2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    d1 = calc(digits[:12], weights1)
    d2 = calc(digits[:12] + str(d1), weights2)
    return digits[12:] == f"{d1}{d2}"
