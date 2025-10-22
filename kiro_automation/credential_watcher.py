"""Monitor the AWS SSO cache directory and move credential files."""

from __future__ import annotations

import random
import shutil
import time
from pathlib import Path
from typing import Iterable, List

from .auth_base import AuthResult
from .exceptions import CredentialTimeoutError
from .logging_utils import get_logger

LOGGER = get_logger(__name__)


class CredentialWatcher:
    """Poll a directory for newly created credential cache files."""

    def __init__(self, cache_dir: str, archive_dir: str, poll_interval: float = 2.0) -> None:
        self.cache_dir = Path(cache_dir)
        self.archive_dir = Path(archive_dir)
        self.poll_interval = poll_interval
        self.archive_dir.mkdir(parents=True, exist_ok=True)

    def wait_and_move(self, auth: AuthResult, timeout: float = 120.0) -> List[Path]:
        """Wait for new files and move them according to naming rules."""

        LOGGER.info("Waiting for new credential files for %s", auth.email)
        deadline = time.time() + timeout
        existing = self._current_file_snapshot()
        while time.time() < deadline:
            time.sleep(self.poll_interval)
            current = self._current_file_snapshot()
            new_files = [path for path in current if path not in existing]
            if new_files:
                LOGGER.info("Detected %s new credential file(s)", len(new_files))
                return [self._move_file(path, auth) for path in new_files]
        raise CredentialTimeoutError("Timed out waiting for credential cache files")

    def _current_file_snapshot(self) -> List[Path]:
        return [path for path in self.cache_dir.glob("*") if path.is_file()]

    def _move_file(self, source: Path, auth: AuthResult) -> Path:
        target_name = self._build_filename(source, auth)
        target_path = self.archive_dir / target_name
        LOGGER.info("Moving %s -> %s", source, target_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target_path))
        return target_path

    def _build_filename(self, source: Path, auth: AuthResult) -> str:
        suffix = source.suffix
        stem = auth.email.split("@")[0]
        if auth.provider == "aws":
            rand = random.randint(10, 99)
            return f"{stem}+kiro+{rand}{suffix}"
        return f"{stem}+kiro{suffix}"
