"""Automation routines for the "Sign in with Google" flow."""

from __future__ import annotations

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from .auth_base import AuthResult
from .browser import BrowserSession
from .config import GoogleAccount
from .logging_utils import get_logger

LOGGER = get_logger(__name__)


class GoogleAuthenticator:
    """Drive the OAuth flow for Google accounts."""

    def __init__(
        self,
        browser: BrowserSession,
        account: GoogleAccount,
        knowledge_button_text: str = "我了解",
    ) -> None:
        self.browser = browser
        self.account = account
        self.knowledge_button_text = knowledge_button_text

    def perform_login(self, auth_url: str) -> AuthResult:
        LOGGER.info("Starting Google authentication for %s", self.account.email)
        self.browser.open(auth_url)
        self.browser.fill(By.ID, "identifierId", self.account.email)
        self.browser.click(By.ID, "identifierNext")
        self.browser.fill(By.NAME, "Passwd", self.account.password)
        self.browser.click(By.ID, "passwordNext")

        self._maybe_acknowledge_new_account_prompt()
        self.browser.wait_for_url_contains("amazoncognito")
        self.browser.click(By.XPATH, "//button[.//span[contains(text(), 'Continue')]]")
        self.browser.wait_for_text("You can close this window", timeout=90.0)

        LOGGER.info("Google authentication completed for %s", self.account.email)
        return AuthResult(
            email=self.account.email,
            provider="google",
            metadata={"email": self.account.email},
        )

    def _maybe_acknowledge_new_account_prompt(self) -> None:
        if not self.knowledge_button_text:
            return
        try:
            LOGGER.debug("Checking for knowledge confirmation button")
            element = WebDriverWait(self.browser.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, f"//button[.//span[contains(text(), '{self.knowledge_button_text}')]]"))
            )
            element.click()
            LOGGER.info("Acknowledged new account prompt")
        except Exception:
            LOGGER.debug("Knowledge prompt not displayed; continuing")
