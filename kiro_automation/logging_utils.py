"""Logging helpers for the automation suite."""

from __future__ import annotations

import logging
from typing import Optional


def setup_logging(level: int = logging.INFO, rich: bool = True) -> None:
    """Initialise the root logger with sensible defaults."""

    if logging.getLogger().handlers:
        return

    if rich:
        try:
            from rich.logging import RichHandler  # type: ignore

            handler: logging.Handler = RichHandler(show_time=True, show_path=False)
        except Exception:  # pragma: no cover - fallback when Rich is unavailable
            handler = logging.StreamHandler()
    else:
        handler = logging.StreamHandler()

    handler.setLevel(level)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    if hasattr(handler, "setFormatter"):
        handler.setFormatter(formatter)
    logging.basicConfig(level=level, handlers=[handler])


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a module-specific logger, ensuring configuration exists."""

    setup_logging()
    return logging.getLogger(name)
