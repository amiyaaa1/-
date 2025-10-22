"""Main orchestration logic for the Kiro automation project."""

from __future__ import annotations

import logging
import re
import time
from enum import Enum
from typing import Iterable, Optional

from .auth_url_collector import ClipboardAuthUrlCollector
from .browser_client import AwsBuilderFlow, BrowserSession, GoogleLoginFlow
from .config_manager import AppConfig, BrowserPatterns
from .credential_handler import CredentialHandler
from .email_service import ZyraMailClient
from .exceptions import AutomationError
from .generators import append_random_suffix, generate_display_name, generate_password
from .kiro_client import KiroClient


class LoginStrategy(str, Enum):
    GOOGLE = "google"
    AWS = "aws"

    @classmethod
    def from_raw(cls, raw: str) -> "LoginStrategy":
        for value in cls:
            if value.value.lower() == raw.lower():
                return value
        raise ValueError(f"Unsupported login strategy: {raw}")


class AutomationOrchestrator:
    """Coordinates the end-to-end automation loop."""

    def __init__(self, config: AppConfig, logger: Optional[logging.Logger] = None) -> None:
        self._config = config
        self._logger = logger or logging.getLogger(__name__)
        self._kiro = KiroClient(config.paths.kiro_executable, logger=self._logger)
        self._credentials = CredentialHandler(
            config.paths.sso_cache_dir,
            config.paths.credential_destination,
            logger=self._logger,
        )
        self._email_client = ZyraMailClient(
            config.email_service,
            config.aws,
            logger=self._logger,
        )
        patterns = config.browser.patterns or BrowserPatterns(
            google_auth="accounts.google.com",
            aws_auth="amazoncognito.com",
        )
        self._google_collector = ClipboardAuthUrlCollector(
            pattern=_compile_pattern(patterns.google_auth),
            poll_interval=config.auth.clipboard_poll_interval,
            timeout=config.auth.clipboard_timeout,
            logger=self._logger,
        )
        self._aws_collector = ClipboardAuthUrlCollector(
            pattern=_compile_pattern(patterns.aws_auth),
            poll_interval=config.auth.clipboard_poll_interval,
            timeout=config.auth.clipboard_timeout,
            logger=self._logger,
        )

    # ------------------------------------------------------------------
    def run(self) -> None:
        strategies = self._prepare_strategies(self._config.loop.strategies)
        self._logger.info("Executing automation loop with strategies: %s", strategies)

        iteration = 0
        while True:
            if self._config.loop.max_iterations is not None and iteration >= self._config.loop.max_iterations:
                self._logger.info("Reached configured iteration limit: %s", self._config.loop.max_iterations)
                break

            strategy = strategies[iteration % len(strategies)]
            self._logger.info("Starting iteration %s using %s", iteration + 1, strategy.value)

            try:
                if strategy is LoginStrategy.GOOGLE:
                    self._run_google_iteration()
                else:
                    self._run_aws_iteration()
            except AutomationError:
                raise
            except Exception as exc:
                self._logger.exception("Iteration %s failed: %s", iteration + 1, exc)
                if not self._config.loop.continue_on_error:
                    raise
            finally:
                iteration += 1
                if self._config.loop.delay_seconds:
                    self._logger.debug(
                        "Sleeping for %s seconds before next iteration",
                        self._config.loop.delay_seconds,
                    )
                    time.sleep(self._config.loop.delay_seconds)

    # ------------------------------------------------------------------
    def _run_google_iteration(self) -> None:
        if not self._config.google.enabled:
            self._logger.warning("Google strategy is disabled; skipping iteration")
            return

        self._kiro.ensure_running()
        self._kiro.click_google()
        oauth_url = self._google_collector.wait_for_url()

        with BrowserSession(self._config.browser) as session:
            session.open(oauth_url)
            GoogleLoginFlow(session.driver, self._config.google).complete_flow()
            session.wait_for_text("You can close this window", timeout=120)

        email_local = self._config.google.email.split("@", maxsplit=1)[0]
        final_stem = f"{email_local}+kiro"
        self._credentials.wait_and_move(final_stem, timeout=self._config.loop.wait_for_credentials)

        self._logger.info("Google iteration completed")
        self._kiro.restart()

    def _run_aws_iteration(self) -> None:
        mailbox_name = f"{self._config.aws.mailbox_prefix}-{int(time.time())}"
        mailbox = self._email_client.create_mailbox(mailbox_name)
        display_name = generate_display_name()
        password = generate_password(self._config.aws.password_length, self._config.aws.password_charset)

        self._kiro.ensure_running()
        self._kiro.click_aws()
        oauth_url = self._aws_collector.wait_for_url()

        with BrowserSession(self._config.browser) as session:
            session.open(oauth_url)
            flow = AwsBuilderFlow(session.driver, self._config.aws, self._email_client)
            flow.complete_flow(mailbox, display_name, password)
            session.wait_for_text("You can close this window", timeout=180)

        email_local = mailbox.local_part
        final_stem = append_random_suffix(f"{email_local}+kiro")
        self._credentials.wait_and_move(final_stem, timeout=self._config.loop.wait_for_credentials)

        self._logger.info("AWS iteration completed for %s", mailbox.address)
        self._kiro.restart()

    # ------------------------------------------------------------------
    def _prepare_strategies(self, raw_strategies: Iterable[str]) -> list[LoginStrategy]:
        strategies = [LoginStrategy.from_raw(item) for item in raw_strategies]
        if not strategies:
            raise ValueError("At least one login strategy must be configured")
        return strategies


def _compile_pattern(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("http"):
        return raw
    escaped = re.escape(raw)
    return rf"https?://.*{escaped}.*"
