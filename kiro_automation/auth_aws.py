"""Automation routines for the "Sign in with AWS Builder ID" flow."""

from __future__ import annotations

import random
import string
from typing import Optional

from selenium.webdriver.common.by import By

from .auth_base import AuthResult
from .browser import BrowserSession
from .config import AwsPasswordRule, TempMailConfig
from .exceptions import BrowserError
from .logging_utils import get_logger
from .password import generate_password
from .temp_mail import TempMailClient

LOGGER = get_logger(__name__)


class AwsAuthenticator:
    """Drive the AWS Builder ID OAuth flow."""

    def __init__(
        self,
        browser: BrowserSession,
        password_rule: AwsPasswordRule,
        temp_mail_config: TempMailConfig,
        temp_mail_client: Optional[TempMailClient] = None,
    ) -> None:
        self.browser = browser
        self.password_rule = password_rule
        self.temp_mail_config = temp_mail_config
        self.temp_mail_client = temp_mail_client or TempMailClient(
            base_url=temp_mail_config.base_url,
            api_key=temp_mail_config.api_key,
            default_domain=temp_mail_config.default_domain,
        )

    def perform_login(self, auth_url: str) -> AuthResult:
        mailbox = self.temp_mail_client.create_mailbox(
            name=self.temp_mail_config.mailbox_prefix,
            expiry_time=self.temp_mail_config.expiry_time,
        )
        password = generate_password(self.password_rule)
        display_name = self._generate_display_name()

        LOGGER.info("Starting AWS authentication for %s", mailbox.address)
        self.browser.open(auth_url)
        self._accept_cookies_if_present()
        self._start_registration(mailbox.address)
        self._enter_profile_information(display_name)
        self._verify_email(mailbox.id)
        self._set_password(password)
        self._complete_authorisation()

        LOGGER.info("AWS authentication completed for %s", mailbox.address)
        return AuthResult(
            email=mailbox.address,
            provider="aws",
            metadata={"email_id": mailbox.id, "display_name": display_name},
            password=password,
        )

    def _accept_cookies_if_present(self) -> None:
        try:
            self.browser.click_first(
                [
                    (By.ID, "awsccc-cb-btn-accept"),
                    (By.XPATH, "//button[contains(., 'Accept all cookies')]")
                ],
                timeout=5.0,
            )
            LOGGER.info("Accepted AWS cookie banner")
        except BrowserError:
            LOGGER.debug("Cookie banner not displayed")

    def _start_registration(self, email: str) -> None:
        self.browser.fill_first(
            [
                (By.CSS_SELECTOR, "input[type='email']"),
                (By.ID, "email"),
                (By.NAME, "email"),
            ],
            text=email,
        )
        self.browser.click_first(
            [
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.ID, "continue"),
                (By.XPATH, "//button[contains(., 'Continue')]")
            ]
        )

    def _enter_profile_information(self, name: str) -> None:
        self.browser.fill_first(
            [
                (By.NAME, "firstName"),
                (By.CSS_SELECTOR, "input[name='firstName']"),
            ],
            text=name.split()[0],
        )
        self.browser.fill_first(
            [
                (By.NAME, "lastName"),
                (By.CSS_SELECTOR, "input[name='lastName']"),
            ],
            text=name.split()[-1],
        )
        self.browser.click_first(
            [
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.XPATH, "//button[contains(., 'Continue')]")
            ]
        )

    def _verify_email(self, email_id: str) -> None:
        LOGGER.info("Waiting for AWS verification email for %s", email_id)
        code = self.temp_mail_client.wait_for_code(
            email_id=email_id,
            subject_keywords=["AWS", "Builder"],
            pattern=r"([0-9]{6})",
            timeout=300,
            poll_interval=5.0,
        )
        self.browser.fill_first(
            [
                (By.NAME, "code"),
                (By.CSS_SELECTOR, "input[name='code']"),
                (By.CSS_SELECTOR, "input[autocomplete='one-time-code']"),
            ],
            text=code,
        )
        self.browser.click_first(
            [
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.XPATH, "//button[contains(., 'Verify code')]")
            ]
        )

    def _set_password(self, password: str) -> None:
        for selector in [
            (By.NAME, "password"),
            (By.ID, "password"),
        ]:
            try:
                self.browser.fill(selector[0], selector[1], password)
                break
            except Exception:
                continue
        for selector in [
            (By.NAME, "confirmPassword"),
            (By.ID, "confirmPassword"),
        ]:
            try:
                self.browser.fill(selector[0], selector[1], password)
                break
            except Exception:
                continue
        self.browser.click_first(
            [
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.XPATH, "//button[contains(., 'Continue')]")
            ]
        )

    def _complete_authorisation(self) -> None:
        self.browser.click_first(
            [
                (By.XPATH, "//button[contains(., 'Allow access')]")
            ],
            timeout=60.0,
        )
        self.browser.wait_for_text("You can close this window", timeout=120.0)

    def _generate_display_name(self) -> str:
        first = self._random_string(5).capitalize()
        last = self._random_string(7).capitalize()
        return f"{first} {last}"

    def _random_string(self, length: int) -> str:
        return "".join(random.choice(string.ascii_lowercase) for _ in range(length))
