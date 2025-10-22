"""Utilities for capturing OAuth URLs from the clipboard."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Optional

import pyperclip

from .exceptions import AuthUrlTimeoutError


@dataclass(slots=True)
class ClipboardAuthUrlCollector:
    """Polls the system clipboard for URLs matching a regular expression."""

    pattern: str
    poll_interval: float = 1.0
    timeout: float = 120.0
    logger: Optional[logging.Logger] = None

    def wait_for_url(self) -> str:
        logger = self.logger or logging.getLogger(__name__)
        regex = re.compile(self.pattern)
        deadline = time.time() + self.timeout
        last_value: Optional[str] = None

        logger.info("Waiting for OAuth URL on clipboard (pattern: %s)", self.pattern)
        while time.time() < deadline:
            value = pyperclip.paste().strip()
            if value != last_value and regex.search(value):
                logger.info("Captured OAuth URL: %s", value)
                return value
            last_value = value
            time.sleep(self.poll_interval)

        raise AuthUrlTimeoutError(f"Failed to capture OAuth URL within {self.timeout} seconds")
