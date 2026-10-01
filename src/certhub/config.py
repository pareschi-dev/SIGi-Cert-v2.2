from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


BASE_DIR = Path(__file__).resolve().parents[2]
CONFIG_PATH = BASE_DIR / "config" / "config.yaml"
CERTIDOES_CONFIG_PATH = BASE_DIR / "certidoes.yaml"
ENV_PATH = BASE_DIR / ".env"


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
