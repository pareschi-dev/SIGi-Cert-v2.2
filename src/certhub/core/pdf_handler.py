from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path


class PDFHandler:
    def __init__(self, output_dir: str | Path = "./output/certhub") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def is_valid_pdf(self, file_path: str | Path) -> bool:
        path = Path(file_path)
        if not path.exists():
            return False
        with path.open("rb") as fh:
            header = fh.read(5)
        return header.startswith(b"%PDF-")

    def calculate_sha256(self, file_path: str | Path) -> str:
        path = Path(file_path)
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(8192), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def save_pdf(self, content: bytes, portal: str, document: str, emission_date: date | None = None) -> Path:
        doc_dir = self.output_dir / portal / self._document_slug(document)
        doc_dir.mkdir(parents=True, exist_ok=True)
        target_date = (emission_date or date.today()).isoformat()
        target_path = doc_dir / f"{target_date}.pdf"
        target_path.write_bytes(content)
        return target_path

    @staticmethod
    def _document_slug(document: str) -> str:
        return "".join(ch for ch in document if ch.isalnum())
