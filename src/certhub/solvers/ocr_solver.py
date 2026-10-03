class OCRSolver:
    """Compatibility shim that refuses to solve CAPTCHA challenges automatically."""

    def __init__(self, confidence_threshold: float = 0.7):
        self.threshold = confidence_threshold

    def preprocessar(self, imagem_bytes: bytes) -> bytes:
        raise RuntimeError("CAPTCHA deve ser resolvido por uma pessoa no portal oficial.")

    def resolver(self, imagem_bytes: bytes) -> str:
        raise RuntimeError("CAPTCHA deve ser resolvido por uma pessoa no portal oficial.")

    def resolver_matematico(self, imagem_bytes: bytes) -> str:
        raise RuntimeError("CAPTCHA deve ser resolvido por uma pessoa no portal oficial.")