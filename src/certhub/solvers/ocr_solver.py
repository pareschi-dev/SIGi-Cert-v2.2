from __future__ import annotations

import io
import re

import cv2
import numpy as np
from PIL import Image

try:
    import ddddocr
except Exception:  # pragma: no cover
    ddddocr = None

try:
    import pytesseract
except Exception:  # pragma: no cover
    pytesseract = None


class OCRSolver:
    def __init__(self, confidence_threshold: float = 0.7):
        self.threshold = confidence_threshold
        self.ocr = ddddocr.DdddOcr(show_ad=False) if ddddocr is not None else None

    def preprocessar(self, imagem_bytes: bytes) -> bytes:
        image = Image.open(io.BytesIO(imagem_bytes)).convert("L")
        img_np = np.array(image)
        img_np = cv2.adaptiveThreshold(
            img_np,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            11,
            2,
        )
        kernel = np.ones((1, 1), np.uint8)
        img_np = cv2.morphologyEx(img_np, cv2.MORPH_CLOSE, kernel)
        _, buffer = cv2.imencode(".png", img_np)
        return buffer.tobytes()

    def resolver(self, imagem_bytes: bytes) -> str:
        image_processed = self.preprocessar(imagem_bytes)

        if self.ocr is not None:
            resultado = self.ocr.classification(image_processed).strip()
            if resultado and len(resultado) >= 3:
                return resultado

        if pytesseract is not None:
            image = Image.open(io.BytesIO(image_processed))
            resultado = pytesseract.image_to_string(
                image,
                config="--psm 8 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
            ).strip()
            if resultado:
                return resultado

        raise RuntimeError("Nenhum engine OCR disponível (ddddocr ou tesseract).")

    def resolver_matematico(self, imagem_bytes: bytes) -> str:
        texto = self.resolver(imagem_bytes)
        nums = re.findall(r"\d+", texto)
        if len(nums) < 2:
            raise ValueError(f"Não foi possível interpretar captcha: {texto}")

        a, b = int(nums[0]), int(nums[1])
        if "+" in texto:
            return str(a + b)
        if "-" in texto:
            return str(a - b)
        if "*" in texto or "x" in texto.lower():
            return str(a * b)
        raise ValueError(f"Operação desconhecida: {texto}")
