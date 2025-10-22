"""Browser automation helpers using Selenium."""

from __future__ import annotations

import contextlib
import time
from typing import Callable, Optional, Sequence, Tuple

from selenium.webdriver import Chrome, ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from .exceptions import BrowserError
from .logging_utils import get_logger

LOGGER = get_logger(__name__)


class BrowserSession:
    """Wrapper around Selenium Chrome driver with sane defaults."""

    def __init__(
        self,
        incognito: bool = True,
        headless: bool = False,
        implicit_wait: float = 2.0,
        driver_factory: Optional[Callable[[], Chrome]] = None,
    ) -> None:
        self.incognito = incognito
        self.headless = headless
        self.implicit_wait = implicit_wait
        self._driver_factory = driver_factory
        self._driver: Optional[Chrome] = None

    def __enter__(self) -> "BrowserSession":  # pragma: no cover - context manager wiring
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - context manager wiring
        self.stop()

    # Driver management -------------------------------------------------
    def start(self) -> Chrome:
        if self._driver:
            return self._driver
        if self._driver_factory:
            driver = self._driver_factory()
        else:
            driver = self._create_default_driver()
        driver.implicitly_wait(self.implicit_wait)
        self._driver = driver
        return driver

    def stop(self) -> None:
        if self._driver:
            LOGGER.info("Closing browser session")
            with contextlib.suppress(Exception):
                self._driver.quit()
            self._driver = None

    def _create_default_driver(self) -> Chrome:
        options = ChromeOptions()
        if self.incognito:
            options.add_argument("--incognito")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--start-maximized")
        if self.headless:
            options.add_argument("--headless=new")
        try:
            driver = Chrome(options=options)
        except Exception as exc:
            raise BrowserError(f"Failed to start Chrome WebDriver: {exc}") from exc
        return driver

    # High level helpers -----------------------------------------------
    @property
    def driver(self) -> Chrome:
        if not self._driver:
            return self.start()
        return self._driver

    def open(self, url: str) -> None:
        LOGGER.info("Navigating to %s", url)
        self.driver.get(url)

    def wait_for_text(self, text: str, timeout: float = 60.0) -> None:
        LOGGER.debug("Waiting for text '%s'", text)
        WebDriverWait(self.driver, timeout).until(EC.text_to_be_present_in_element((By.TAG_NAME, "body"), text))

    def click(self, by: By, value: str, timeout: float = 30.0) -> None:
        LOGGER.debug("Waiting for clickable element %s=%s", by, value)
        element = WebDriverWait(self.driver, timeout).until(EC.element_to_be_clickable((by, value)))
        element.click()

    def fill(self, by: By, value: str, text: str, clear: bool = True, timeout: float = 30.0) -> None:
        LOGGER.debug("Filling element %s=%s", by, value)
        element = WebDriverWait(self.driver, timeout).until(EC.presence_of_element_located((by, value)))
        if clear:
            element.clear()
        element.send_keys(text)

    def click_first(self, selectors: Sequence[Tuple[By, str]], timeout: float = 30.0) -> None:
        last_error: Optional[Exception] = None
        for by, value in selectors:
            try:
                self.click(by, value, timeout=timeout)
                return
            except Exception as exc:
                last_error = exc
        raise BrowserError(f"Unable to click any selector from list: {selectors}") from last_error

    def fill_first(self, selectors: Sequence[Tuple[By, str]], text: str, clear: bool = True, timeout: float = 30.0) -> None:
        last_error: Optional[Exception] = None
        for by, value in selectors:
            try:
                self.fill(by, value, text=text, clear=clear, timeout=timeout)
                return
            except Exception as exc:
                last_error = exc
        raise BrowserError(f"Unable to fill any selector from list: {selectors}") from last_error

    def wait_for_url_contains(self, fragment: str, timeout: float = 60.0) -> None:
        LOGGER.debug("Waiting for URL containing %s", fragment)
        WebDriverWait(self.driver, timeout).until(EC.url_contains(fragment))

    def wait_until(self, predicate: Callable[[Chrome], bool], timeout: float = 60.0, poll: float = 1.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate(self.driver):
                return
            time.sleep(poll)
        raise BrowserError("Condition not met before timeout")
