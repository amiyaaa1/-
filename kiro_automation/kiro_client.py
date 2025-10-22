"""Wrappers around the Kiro desktop application using pywinauto."""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path
from typing import Optional

from pywinauto import timings
from pywinauto.application import Application
from pywinauto.findwindows import ElementNotFoundError


class KiroClient:
    """Controls the local Kiro executable via UI Automation."""

    def __init__(self, executable: Path, logger: Optional[logging.Logger] = None) -> None:
        self._exe = Path(executable)
        self._logger = logger or logging.getLogger(__name__)
        self._app: Optional[Application] = None

    # ------------------------------------------------------------------
    def launch(self) -> None:
        self._logger.info("Launching Kiro: %s", self._exe)
        self._app = Application(backend="uia").start(str(self._exe))
        self._main_window.wait("visible", timeout=30)
        self._logger.debug("Kiro window is visible")

    def ensure_running(self) -> None:
        if self._app is None:
            self.launch()

    def close(self) -> None:
        if not self._app:
            return
        self._logger.debug("Closing Kiro application")
        with contextlib.suppress(Exception):
            self._app.kill()
        self._app = None

    # ------------------------------------------------------------------
    def click_google(self) -> None:
        if not self._click_button("Sign in with Google"):
            raise RuntimeError("Could not locate 'Sign in with Google' button")

    def click_aws(self) -> None:
        if not self._click_button("Sign in with AWS Builder ID"):
            raise RuntimeError("Could not locate 'Sign in with AWS Builder ID' button")

    # ------------------------------------------------------------------
    def restart(self) -> None:
        self.close()
        self.launch()

    # ------------------------------------------------------------------
    @property
    def _main_window(self):
        if not self._app:
            raise RuntimeError("Kiro application is not running")
        return self._app.top_window()

    def _click_button(self, label: str) -> bool:
        try:
            button = self._main_window.child_window(title=label, control_type="Button")
            button.wait("enabled", timeout=20)
            button.click_input()
            self._logger.info("Clicked Kiro button: %s", label)
            return True
        except (ElementNotFoundError, timings.TimeoutError):
            self._logger.exception("Failed to click button '%s'", label)
            return False
