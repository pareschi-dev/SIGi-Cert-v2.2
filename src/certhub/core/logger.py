from __future__ import annotations

import logging
from pathlib import Path


def get_logger(name: str = "certhub") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    log_dir = Path("./logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_dir / "certhub.log", encoding="utf-8")
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


def setup_logger(name: str = "certhub") -> logging.Logger:
    return get_logger(name)


logger = setup_logger()
