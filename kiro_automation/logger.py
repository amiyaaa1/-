"""Logging helpers."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

from .config_manager import LoggingConfig

DEFAULT_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def setup_logging(config: LoggingConfig) -> logging.Logger:
    """Initialise root logging handlers and return the package logger."""

    handlers: list[logging.Handler] = []
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(logging.Formatter(DEFAULT_FORMAT))
    handlers.append(stream_handler)

    if config.log_directory:
        log_directory = Path(config.log_directory)
        log_directory.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_directory / "automation.log", encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(DEFAULT_FORMAT))
        handlers.append(file_handler)

    level = _parse_level(config.level)
    logging.basicConfig(level=level, handlers=handlers, force=True)
    logging.captureWarnings(True)

    return logging.getLogger("kiro_automation")


def _parse_level(raw_level: Optional[str]) -> int:
    if not raw_level:
        return logging.INFO
    if isinstance(raw_level, str):
        try:
            return logging.getLevelName(raw_level.upper())
        except Exception:  # pragma: no cover - defensive
            return logging.INFO
    return int(raw_level)
