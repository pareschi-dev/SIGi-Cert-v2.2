from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class EmissionRequest:
    portal: str
    document: str
    additional_data: dict[str, Any] = field(default_factory=dict)
    headless: bool = True


@dataclass
class EmissionResult:
    portal: str
    document: str
    success: bool
    message: str = ""
    pdf_path: str | None = None
    pdf_hash: str | None = None
    attempts: int = 1
    elapsed_seconds: float = 0.0
    captcha_type: str | None = None
    captcha_method: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"))
