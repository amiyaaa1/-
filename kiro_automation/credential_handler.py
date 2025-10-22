"""Utilities for monitoring and moving AWS SSO credential cache files."""

from __future__ import annotations

import logging
import queue
import shutil
import threading
import time
from pathlib import Path
from typing import Optional

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .exceptions import CredentialTimeoutError


class _CreationHandler(FileSystemEventHandler):
    """Internal handler that pushes created files into a queue."""

    def __init__(self) -> None:
        self._queue: queue.Queue[Path] = queue.Queue()

    def on_created(self, event) -> None:  # type: ignore[override]
        if not event.is_directory:
            self._queue.put(Path(event.src_path))

    def get(self, timeout: float | None = None) -> Path:
        return self._queue.get(timeout=timeout)


class CredentialHandler:
    """Watches the SSO cache directory and relocates new credential files."""

    def __init__(
        self,
        cache_dir: Path,
        destination_dir: Path,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._cache_dir = cache_dir
        self._destination_dir = destination_dir
        self._logger = logger or logging.getLogger(__name__)
        self._observer: Optional[Observer] = None
        self._handler = _CreationHandler()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    def start(self) -> None:
        with self._lock:
            if self._observer and self._observer.is_alive():
                return
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            observer = Observer()
            observer.schedule(self._handler, str(self._cache_dir), recursive=False)
            observer.start()
            self._observer = observer
            self._logger.debug("Started credential watcher for %s", self._cache_dir)

    def stop(self) -> None:
        with self._lock:
            if not self._observer:
                return
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
            self._logger.debug("Stopped credential watcher")

    # ------------------------------------------------------------------
    def wait_for_new_file(self, timeout: float) -> Path:
        self.start()
        try:
            return self._handler.get(timeout=timeout)
        except queue.Empty as exc:  # pragma: no cover - runtime safeguard
            raise CredentialTimeoutError(
                f"No credential file created in {timeout} seconds"
            ) from exc

    def wait_and_move(self, final_stem: str, timeout: float) -> Path:
        source = self.wait_for_new_file(timeout)
        self._wait_for_write_completion(source)
        destination = self._destination_dir / final_stem
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            timestamp = int(time.time())
            destination = destination.with_name(f"{destination.stem}-{timestamp}{destination.suffix}")
        shutil.move(str(source), destination)
        self._logger.info("Moved credential file %s -> %s", source, destination)
        return destination

    # ------------------------------------------------------------------
    def _wait_for_write_completion(self, file_path: Path, stable_checks: int = 3) -> None:
        """Wait until a file is no longer growing before moving it."""

        last_size = -1
        stable_count = 0

        while stable_count < stable_checks:
            try:
                size = file_path.stat().st_size
            except FileNotFoundError:
                size = -1
            if size == last_size and size > 0:
                stable_count += 1
            else:
                stable_count = 0
            last_size = size
            time.sleep(0.5)

        self._logger.debug("File %s is stable with size %s", file_path, last_size)
