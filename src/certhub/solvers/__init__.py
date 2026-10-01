"""Captcha solvers for CertHub."""

from .hcaptcha_solver import HCaptchaSolver
from .ocr_solver import OCRSolver

__all__ = ["OCRSolver", "HCaptchaSolver"]
