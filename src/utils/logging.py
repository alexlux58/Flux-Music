"""Logging setup with rotating file handler."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src.config import LoggingConfig


def setup_logging(
    config: LoggingConfig, log_file: Path, *, component: str = "app"
) -> logging.Logger:
    """Configure root logging once and return a named component logger."""
    log_file.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    if not root.handlers:
        level = getattr(logging, config.level.upper(), logging.INFO)
        root.setLevel(level)

        formatter = logging.Formatter(
            fmt=("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"),
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=config.max_bytes,
            backupCount=config.backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

        console = logging.StreamHandler()
        console.setFormatter(formatter)
        root.addHandler(console)

    return logging.getLogger(f"music_library.{component}")


def get_logger(component: str) -> logging.Logger:
    return logging.getLogger(f"music_library.{component}")
