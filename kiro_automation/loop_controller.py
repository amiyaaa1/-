"""Main orchestration loop for Kiro credential automation."""

from __future__ import annotations

import time
from typing import Dict, Iterable, Optional, Union

import psutil

from .auth_aws import AwsAuthenticator
from .auth_google import GoogleAuthenticator
from .browser import BrowserSession
from .config import Config, GoogleAccount
from .credential_watcher import CredentialWatcher
from .exceptions import AutomationError
from .kiro_launcher import KiroLauncher
from .logging_utils import get_logger

LOGGER = get_logger(__name__)


class LoopController:
    """Coordinate each automation cycle."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.launcher = KiroLauncher(config.kiro_exe_path)
        self.credential_watcher = CredentialWatcher(config.cache_dir, config.archive_dir)
        self._google_index = 0

    def run(self) -> None:
        cycles = 0
        max_cycles = self.config.max_cycles or float("inf")
        try:
            while cycles < max_cycles:
                cycles += 1
                LOGGER.info("=== Starting automation cycle %s ===", cycles)
                try:
                    self._run_cycle(cycles)
                except AutomationError as exc:
                    LOGGER.exception("Cycle %s failed: %s", cycles, exc)
                except Exception as exc:  # pragma: no cover - defensive logging
                    LOGGER.exception("Unexpected error during cycle %s: %s", cycles, exc)
                LOGGER.info("Sleeping for %s seconds before next cycle", self.config.cycle_sleep)
                time.sleep(self.config.cycle_sleep)
        except KeyboardInterrupt:  # pragma: no cover - manual stop
            LOGGER.warning("Automation interrupted by user")
        finally:
            self.launcher.stop()

    def _run_cycle(self, cycle_number: int) -> None:
        LOGGER.debug("Preparing cycle %s", cycle_number)
        self.launcher.ensure_closed()
        self.launcher.launch()

        login_label = "Sign in with Google" if self.config.login_mode == "google" else "Sign in with AWS Builder ID"
        before_processes = self._collect_browser_processes()
        self.launcher.click_login_button(login_label)
        auth_url, pid = self._wait_for_auth_url(before_processes)
        LOGGER.info("Captured OAuth URL: %s", auth_url)
        try:
            if pid is not None:
                self._terminate_process(pid)

            with BrowserSession() as browser:
                authenticator = self._build_authenticator(browser)
                auth_result = authenticator.perform_login(auth_url)

            moved_files = self.credential_watcher.wait_and_move(auth_result)
            for path in moved_files:
                LOGGER.info("Credential archived at %s", path)
        finally:
            self.launcher.stop()

    def _build_authenticator(self, browser: BrowserSession) -> Union[GoogleAuthenticator, AwsAuthenticator]:
        if self.config.login_mode == "google":
            account = self._next_google_account()
            return GoogleAuthenticator(browser=browser, account=account)
        else:
            if not self.config.temp_mail:
                raise AutomationError("Temp mail configuration missing for AWS flow")
            return AwsAuthenticator(
                browser=browser,
                password_rule=self.config.aws_password_rule,
                temp_mail_config=self.config.temp_mail,
            )

    def _next_google_account(self) -> GoogleAccount:
        if not self.config.google_accounts:
            raise AutomationError("No Google accounts configured")
        account = self.config.google_accounts[self._google_index % len(self.config.google_accounts)]
        self._google_index += 1
        return account

    def _collect_browser_processes(self) -> Dict[int, Iterable[str]]:
        snapshot: Dict[int, Iterable[str]] = {}
        for proc in psutil.process_iter(attrs=["pid", "name", "cmdline"]):
            try:
                name = (proc.info.get("name") or "").lower()
                if name and any(browser in name for browser in ["chrome", "msedge", "brave", "firefox"]):
                    snapshot[proc.info["pid"]] = proc.info.get("cmdline") or []
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return snapshot

    def _wait_for_auth_url(self, before: Dict[int, Iterable[str]], timeout: float = 40.0) -> tuple[str, Optional[int]]:
        deadline = time.time() + timeout
        seen_urls = {url for url in (self._extract_url(cmdline) for cmdline in before.values()) if url}
        while time.time() < deadline:
            for proc in psutil.process_iter(attrs=["pid", "name", "cmdline"]):
                try:
                    if proc.pid in before:
                        # allow reuse of existing browser process if new URL detected
                        cmdline = proc.info.get("cmdline") or []
                        url = self._extract_url(cmdline)
                        if url and url not in seen_urls:
                            return url, proc.pid
                        continue
                    name = (proc.info.get("name") or "").lower()
                    if not any(browser in name for browser in ["chrome", "msedge", "brave", "firefox"]):
                        continue
                    cmdline = proc.info.get("cmdline") or []
                    url = self._extract_url(cmdline)
                    if url:
                        seen_urls.add(url)
                        return url, proc.pid
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            time.sleep(1.0)
        raise AutomationError("Unable to capture OAuth URL from browser launch")

    def _extract_url(self, cmdline: Iterable[str]) -> Optional[str]:
        for token in cmdline:
            if token.startswith("http"):
                return token
            if token.startswith("--app=") and token[6:].startswith("http"):
                return token[6:]
        return None

    def _terminate_process(self, pid: int) -> None:
        try:
            proc = psutil.Process(pid)
            LOGGER.info("Closing spawned browser process pid=%s", pid)
            proc.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            LOGGER.debug("Browser process already closed")
