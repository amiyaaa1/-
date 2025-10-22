"""Selenium based browser automation helpers."""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass
from typing import Iterable, Optional

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver import Chrome
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from .config_manager import AwsBuilderConfig, BrowserConfig, GoogleConfig
from .email_service import Mailbox, ZyraMailClient

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class BrowserSession:
    """Thin context manager around Selenium's Chrome driver."""

    config: BrowserConfig
    headless_override: Optional[bool] = None

    def __post_init__(self) -> None:  # pragma: no cover - simple attribute setup
        self._driver: Optional[Chrome] = None

    def __enter__(self) -> "BrowserSession":
        if self._driver:
            return self
        options = Options()
        if self.config.binary_path:
            options.binary_location = str(self.config.binary_path)
        if self.config.incognito:
            options.add_argument("--incognito")
        if self.headless_override if self.headless_override is not None else self.config.headless:
            options.add_argument("--headless=new")
        if self.config.window_size:
            width, height = self.config.window_size
            options.add_argument(f"--window-size={width},{height}")
        if self.config.debugger_address:
            options.add_experimental_option("debuggerAddress", self.config.debugger_address)
        for argument in self.config.extra_arguments:
            options.add_argument(argument)

        service = Service(str(self.config.driver_path)) if self.config.driver_path else Service()
        self._driver = webdriver.Chrome(service=service, options=options)
        self._driver.set_page_load_timeout(120)
        LOGGER.debug("Launched Chrome session")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - resource cleanup
        if self._driver:
            with contextlib.suppress(Exception):
                self._driver.quit()
            LOGGER.debug("Closed Chrome session")
        self._driver = None

    @property
    def driver(self) -> Chrome:
        if not self._driver:
            raise RuntimeError("BrowserSession not initialised")
        return self._driver

    def open(self, url: str) -> None:
        LOGGER.info("Opening URL %s", url)
        self.driver.get(url)

    def wait_for_text(self, text: str, timeout: float = 60.0) -> None:
        WebDriverWait(self.driver, timeout).until(lambda d: text in d.page_source)


class GoogleLoginFlow:
    """Encapsulates the Google OAuth steps required by Kiro."""

    def __init__(self, driver: Chrome, config: GoogleConfig, timeout: float = 120.0) -> None:
        self._driver = driver
        self._config = config
        self._wait = WebDriverWait(driver, timeout)

    def complete_flow(self) -> None:
        LOGGER.info("Completing Google authentication for %s", self._config.email)
        self._enter_email()
        self._enter_password()
        self._handle_additional_prompts()
        self._accept_consent()
        LOGGER.info("Google authentication flow submitted")

    # ------------------------------------------------------------------
    def _enter_email(self) -> None:
        email_input = self._wait.until(EC.element_to_be_clickable((By.ID, "identifierId")))
        email_input.clear()
        email_input.send_keys(self._config.email)
        email_input.send_keys(Keys.ENTER)

    def _enter_password(self) -> None:
        password_input = self._wait.until(
            EC.element_to_be_clickable((By.NAME, "Passwd"))
        )
        password_input.clear()
        password_input.send_keys(self._config.password)
        password_input.send_keys(Keys.ENTER)

    def _handle_additional_prompts(self) -> None:
        # Example prompt: new account acknowledgement
        for text in ("I understand", "我了解", "Continue"):
            with contextlib.suppress(TimeoutException, NoSuchElementException):
                button = self._wait.until(
                    EC.element_to_be_clickable((By.XPATH, f"//button//*[contains(text(), '{text}')]"))
                )
                button.click()
                LOGGER.debug("Clicked acknowledgement button: %s", text)

    def _accept_consent(self) -> None:
        for locator in self._consent_locators():
            with contextlib.suppress(TimeoutException, NoSuchElementException):
                button = self._wait.until(EC.element_to_be_clickable(locator))
                button.click()
                LOGGER.info("Accepted Google consent page")
                break

    @staticmethod
    def _consent_locators() -> Iterable[tuple[str, str]]:
        return (
            (By.XPATH, "//button//*[contains(text(), 'Continue')]"),
            (By.XPATH, "//button//*[contains(text(), '继续')]"),
            (By.XPATH, "//button//*[contains(text(), '允许')]"),
        )


class AwsBuilderFlow:
    """Automates the AWS Builder ID onboarding flow."""

    def __init__(
        self,
        driver: Chrome,
        aws_config: AwsBuilderConfig,
        email_client: ZyraMailClient,
        timeout: float = 240.0,
    ) -> None:
        self._driver = driver
        self._aws_config = aws_config
        self._email_client = email_client
        self._wait = WebDriverWait(driver, timeout)

    def complete_flow(self, mailbox: Mailbox, display_name: str, password: str) -> None:
        LOGGER.info("Starting AWS Builder ID onboarding for %s", mailbox.address)
        self._accept_cookies()
        self._submit_email(mailbox.address)
        self._submit_profile(display_name)
        verification_code = self._email_client.wait_for_code(mailbox, r"(\d{6})")
        self._submit_verification_code(verification_code)
        self._set_password(password)
        self._allow_access()
        LOGGER.info("AWS Builder ID onboarding submitted")

    # ------------------------------------------------------------------
    def _accept_cookies(self) -> None:
        for text in ("Accept", "同意", "允许"):
            with contextlib.suppress(TimeoutException, NoSuchElementException):
                button = self._wait.until(
                    EC.element_to_be_clickable((By.XPATH, f"//button//*[contains(text(), '{text}')]"))
                )
                button.click()
                LOGGER.debug("Accepted cookies banner via %s", text)
                break

    def _submit_email(self, address: str) -> None:
        email_input = self._wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='email']"))
        )
        email_input.clear()
        email_input.send_keys(address)
        email_input.send_keys(Keys.ENTER)

    def _submit_profile(self, display_name: str) -> None:
        name_input = self._wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "input[name*='name'], input[autocomplete='name']"))
        )
        name_input.clear()
        name_input.send_keys(display_name)
        name_input.send_keys(Keys.ENTER)

    def _submit_verification_code(self, code: str) -> None:
        code_input = self._wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='tel'], input[name*='code']"))
        )
        code_input.clear()
        code_input.send_keys(code)
        code_input.send_keys(Keys.ENTER)

    def _set_password(self, password: str) -> None:
        password_inputs = self._wait.until(
            lambda driver: driver.find_elements(By.CSS_SELECTOR, "input[type='password']")
        )
        if not password_inputs:
            raise TimeoutException("Could not locate password inputs")
        password_inputs[0].clear()
        password_inputs[0].send_keys(password)
        target_inputs = password_inputs[1:] or [password_inputs[0]]
        for input_box in target_inputs:
            input_box.clear()
            input_box.send_keys(password)
        target_inputs[-1].send_keys(Keys.ENTER)

    def _allow_access(self) -> None:
        for text in ("Allow access", "允许访问", "Allow"):
            with contextlib.suppress(TimeoutException, NoSuchElementException):
                button = self._wait.until(
                    EC.element_to_be_clickable((By.XPATH, f"//button//*[contains(text(), '{text}')]"))
                )
                button.click()
                LOGGER.debug("Confirmed AWS consent via button %s", text)
                break
