from __future__ import annotations

import os
import re
import hashlib
import hmac
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml


BASE_DIR = Path(__file__).resolve().parents[2]
CONFIG_PATH = BASE_DIR / "config" / "config.yaml"
CERTIDOES_CONFIG_PATH = BASE_DIR / "certidoes.yaml"
ENV_PATH = BASE_DIR / ".env"


def resolve_project_path(path: str | Path) -> Path:
    """Resolve relative application paths from the repository root, not the caller's cwd."""
    candidate = Path(path).expanduser()
    return candidate if candidate.is_absolute() else BASE_DIR / candidate


def downloads_directory() -> Path:
    """Return the operator's Downloads directory, honoring CERTHUB_DOWNLOADS_DIR."""
    configured = get_env_var("CERTHUB_DOWNLOADS_DIR", "")
    if configured:
        return resolve_project_path(configured)
    return Path.home() / "Downloads"


def create_consultation_directory(
    document_digits: str,
    root: Path | None = None,
) -> tuple[Path, datetime]:
    """Create one collision-safe `{document}_{date}_{time}` folder for a consultation."""
    root = root or downloads_directory()
    root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().astimezone().replace(microsecond=0)
    for offset in range(3600):
        candidate_time = timestamp + timedelta(seconds=offset)
        folder_name = f"{document_digits}_{candidate_time:%Y-%m-%d_%H-%M-%S}"
        folder = root / folder_name
        try:
            folder.mkdir()
        except FileExistsError:
            continue
        return folder, candidate_time
    raise RuntimeError("Não foi possível criar uma pasta exclusiva para esta consulta.")


def find_consultation_directory(document_hash: str, started_at: str, root: Path) -> Path | None:
    """Find a consultation folder without storing the full CPF/CNPJ path in SQLite."""
    timestamp = datetime.fromisoformat(started_at).strftime("%Y-%m-%d_%H-%M-%S")
    pattern = re.compile(rf"(?P<document>\d{{11}}|\d{{14}})_{re.escape(timestamp)}\Z")
    if not root.is_dir():
        return None
    for folder in root.iterdir():
        match = pattern.fullmatch(folder.name)
        if match and folder.is_dir():
            candidate_hash = hashlib.sha256(match.group("document").encode("ascii")).hexdigest()
            if hmac.compare_digest(candidate_hash, document_hash):
                return folder
    return None


def load_yaml_config(path: str | Path | None = None) -> dict[str, Any]:
    config_file = Path(path) if path else CONFIG_PATH
    if not config_file.exists():
        return {}
    with config_file.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data if isinstance(data, dict) else {}


def load_certidoes_config(path: str | Path | None = None) -> dict[str, Any]:
    config_file = Path(path) if path else CERTIDOES_CONFIG_PATH
    if not config_file.exists():
        return {}
    with config_file.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data if isinstance(data, dict) else {}


def load_env(path: str | Path | None = None) -> dict[str, str]:
    env_file = Path(path) if path else ENV_PATH
    env: dict[str, str] = {}
    if not env_file.exists():
        return env
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"\'')
    return env


def get_setting(*keys: str, default: Any = None) -> Any:
    config = load_yaml_config()
    current: Any = config
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def get_env_var(name: str, default: Any = None) -> str | Any:
    value = os.getenv(name)
    if value is not None:
        return value
    env_values = load_env()
    return env_values.get(name, default)
