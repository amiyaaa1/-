"""Wrapper around pywinauto to control the Kiro desktop application."""

from __future__ import annotations

import platform
import time
from pathlib import Path

import psutil

from .exceptions import AutomationError, UnsupportedPlatformError
from .logging_utils import get_logger

LOGGER = get_logger(__name__)


class KiroLauncher:
    """Launches and stops the Kiro IDE Windows client."""

    def __init__(self, executable_path: str, startup_timeout: float = 25.0) -> None:
        self.executable_path = Path(executable_path)
        self.startup_timeout = startup_timeout
        self._app = None

    def _ensure_windows(self) -> None:
        if platform.system().lower() != "windows":
            raise UnsupportedPlatformError("KiroLauncher requires Windows to operate")

    def launch(self) -> None:
        """Launch Kiro.exe and wait for the login window to appear."""

        self._ensure_windows()
        if not self.executable_path.exists():
            raise AutomationError(f"Kiro executable not found at {self.executable_path}")

        LOGGER.info("Launching Kiro from %s", self.executable_path)
        try:
            from pywinauto.application import Application  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise AutomationError("pywinauto must be installed to control Kiro") from exc

        self._app = Application(backend="uia").start(rf'"{self.executable_path}"')
        self._wait_for_login_window()

    def stop(self) -> None:
        """Terminate the Kiro process if running."""

        self._ensure_windows()
        for proc in psutil.process_iter(attrs=["pid", "name"]):
            if proc.info.get("name", "").lower().startswith("kiro"):
                LOGGER.info("Terminating Kiro process pid=%s", proc.info["pid"])
                try:
                    psutil.Process(proc.info["pid"]).terminate()
                except psutil.Error:  # pragma: no cover - process might already exit
                    continue
        time.sleep(2.0)

    def _wait_for_login_window(self) -> None:
        if self._app is None:
            raise AutomationError("Kiro application is not running")
        start = time.time()
        while time.time() - start < self.startup_timeout:
            try:
                window = self._app.window(best_match="Kiro")
                if window.exists(timeout=1):
                    LOGGER.info("Kiro login window detected")
                    return
            except Exception:  # pragma: no cover - pywinauto specific errors
                time.sleep(1)
        raise AutomationError("Timed out waiting for Kiro to start")

    def click_login_button(self, label: str, wait: float = 1.0) -> None:
        """Click one of the OAuth provider buttons."""

        if self._app is None:
            raise AutomationError("Kiro is not running; call launch() first")
        try:
            from pywinauto.findwindows import ElementNotFoundError  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise AutomationError("pywinauto must be installed to control Kiro") from exc

        try:
            window = self._app.window(best_match="Kiro")
            window.wait("visible", timeout=15)
            window.wait("enabled", timeout=15)
            window.set_focus()

            control = self._locate_login_control(window, label)
            if control is None:
                available = [
                    f"{ctrl.control_type()}:{ctrl.window_text().strip()}"
                    for ctrl in window.descendants()
                    if ctrl.window_text().strip()
                ][:10]
                raise AutomationError(
                    f"Unable to locate login control '{label}'. Known controls: {', '.join(available)}"
                )

            LOGGER.info("Clicking login control labelled '%s'", control.window_text().strip() or label)
            control.wait("ready", timeout=5)
            control.click_input()
            time.sleep(wait)
        except ElementNotFoundError as exc:
            raise AutomationError(f"Login control '{label}' not found") from exc
        except Exception as exc:
            raise AutomationError(f"Unable to click login control '{label}': {exc}") from exc

    def _locate_login_control(self, window, label: str):
        """Search for a clickable control matching the provided label."""

        def normalise(text: str) -> str:
            cleaned = text.lower().replace("&", "").strip()
            return " ".join(cleaned.split())

        target = normalise(label)

        search_control_types = ("Button", "Hyperlink", "Text")
        for ctrl_type in search_control_types:
            for ctrl in window.descendants(control_type=ctrl_type):
                text = ctrl.window_text().strip()
                if not text:
                    continue
                normalised_text = normalise(text)
                if normalised_text == target or target in normalised_text:
                    return ctrl

        try:
            fallback = window.child_window(best_match=label)
            fallback.wait("exists", timeout=3)
            return fallback
        except Exception:
            return None

    def ensure_closed(self) -> None:
        """Ensure Kiro is not running before starting a cycle."""

        self._ensure_windows()
        for proc in psutil.process_iter(attrs=["pid", "name", "exe"]):
            try:
                if proc.info.get("exe") and Path(proc.info["exe"]).samefile(self.executable_path):
                    LOGGER.info("Closing existing Kiro instance pid=%s", proc.info["pid"])
                    proc.terminate()
            except (psutil.NoSuchProcess, FileNotFoundError):  # pragma: no cover
                continue
        time.sleep(2.0)
