from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from .schemas import SandboxLaunchRequest, SandboxStatusResponse
from .utils import Account, build_cookie_filename, cookies_to_text, ensure_directory, parse_accounts

logger = logging.getLogger(__name__)


@dataclass
class SandboxStatus:
    id: str
    start_url: str
    email: Optional[str]
    created_at: datetime
    state: str = "pending"
    message: Optional[str] = None
    cookie_file: Optional[Path] = None
    domain: Optional[str] = None
    enable_google_login: bool = False
    enable_site_google_registration: bool = False
    headless: bool = False
    account: Optional[Account] = None
    task: Optional[asyncio.Task] = field(default=None, repr=False, compare=False)

    def to_response(self, base_url: str) -> SandboxStatusResponse:
        download_url: Optional[str] = None
        if self.cookie_file:
            download_url = f"{base_url}/api/sandboxes/{self.id}/cookie"
        return SandboxStatusResponse(
            id=self.id,
            email=self.email,
            start_url=self.start_url,
            domain=self.domain,
            state=self.state,
            message=self.message,
            cookie_ready=self.cookie_file is not None,
            created_at=self.created_at,
            download_url=download_url,
        )


class SandboxManager:
    def __init__(self, work_dir: Path) -> None:
        self.work_dir = work_dir
        ensure_directory(self.work_dir)
        self.cookies_dir = self.work_dir / "cookies"
        ensure_directory(self.cookies_dir)
        self.profiles_dir = self.work_dir / "profiles"
        ensure_directory(self.profiles_dir)
        self._sandboxes: Dict[str, SandboxStatus] = {}
        self._lock = asyncio.Lock()

    async def start(self, request: SandboxLaunchRequest) -> List[SandboxStatus]:
        accounts = parse_accounts(request.accounts_raw)
        if request.enable_google_login and len(accounts) < request.count:
            raise ValueError("启用谷歌登录时，需要提供不少于沙箱数量的账号信息")

        sandboxes: List[SandboxStatus] = []
        for index in range(request.count):
            account: Optional[Account] = accounts[index] if index < len(accounts) else None
            sandbox_id = str(uuid.uuid4())
            status = SandboxStatus(
                id=sandbox_id,
                start_url=str(request.start_url),
                email=account.email if account else None,
                created_at=datetime.utcnow(),
                enable_google_login=request.enable_google_login,
                enable_site_google_registration=request.enable_site_google_registration,
                headless=request.headless,
                account=account,
            )
            sandboxes.append(status)

        async with self._lock:
            for status in sandboxes:
                self._sandboxes[status.id] = status
                status.task = asyncio.create_task(self._run_sandbox(status))

        return sandboxes

    async def list_status(self) -> List[SandboxStatus]:
        async with self._lock:
            return sorted(self._sandboxes.values(), key=lambda item: item.created_at)

    async def get_status(self, sandbox_id: str) -> Optional[SandboxStatus]:
        async with self._lock:
            return self._sandboxes.get(sandbox_id)

    async def _run_sandbox(self, status: SandboxStatus) -> None:
        status.state = "running"
        try:
            await asyncio.to_thread(self._run_sandbox_sync, status)
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("sandbox %s failed", status.id)
            status.state = "failed"
            status.message = str(exc)

    def _run_sandbox_sync(self, status: SandboxStatus) -> None:
        driver: Optional[webdriver.Chrome] = None
        profile_dir = self.profiles_dir / status.id
        ensure_directory(profile_dir)
        try:
            driver = self._create_driver(profile_dir, status.headless)
            if status.enable_google_login and status.account:
                self._login_google(driver, status.account)
            driver.get(status.start_url)
            if status.enable_google_login and status.enable_site_google_registration and status.account:
                self._attempt_site_google_login(driver, status.account)
            self._wait_for_page_ready(driver)
            final_url = driver.current_url
            self._save_cookies(driver.get_cookies(), status, final_url)
            if status.state != "failed":
                status.state = "completed"
                if not status.message:
                    status.message = "Cookie 已保存"
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("sandbox %s failed during execution", status.id)
            status.state = "failed"
            status.message = str(exc)
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:  # pylint: disable=broad-except
                    pass

    def _create_driver(self, profile_dir: Path, headless: bool) -> webdriver.Chrome:
        options = webdriver.ChromeOptions()
        options.add_argument(f"--user-data-dir={profile_dir}")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--disable-extensions")
        options.add_argument("--lang=zh-CN")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        if headless:
            options.add_argument("--headless=new")
            options.add_argument("--window-size=1920,1080")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(90)
        driver.implicitly_wait(2)
        return driver

    def _wait_for_page_ready(self, driver: webdriver.Chrome, timeout: int = 30) -> None:
        end_time = time.time() + timeout
        while time.time() < end_time:
            try:
                ready_state = driver.execute_script("return document.readyState")
                if ready_state == "complete":
                    time.sleep(1.5)
                    return
            except WebDriverException:
                pass
            time.sleep(0.5)

    def _login_google(self, driver: webdriver.Chrome, account: Account) -> None:
        driver.get("https://accounts.google.com/signin/v2/identifier?flowName=GlifWebSignIn")
        wait = WebDriverWait(driver, 30)
        email_input = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='email']")))
        email_input.clear()
        email_input.send_keys(account.email)
        next_button = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "#identifierNext button, button[jsname='LgbsSe']"))
        )
        self._safe_click(driver, next_button)
        time.sleep(1.5)
        if account.password:
            password_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']")))
            password_input.clear()
            password_input.send_keys(account.password)
            password_next = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "#passwordNext button, button[jsname='LgbsSe']"))
            )
            self._safe_click(driver, password_next)
        time.sleep(2.0)
        if account.recovery_email:
            try:
                recovery_input = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='email'][name='email']"))
                )
                recovery_input.clear()
                recovery_input.send_keys(account.recovery_email)
                recovery_next = driver.find_element(By.CSS_SELECTOR, "button[jsname='LgbsSe']")
                self._safe_click(driver, recovery_next)
            except TimeoutException:
                pass
        self._wait_for_page_ready(driver, timeout=40)

    def _attempt_site_google_login(self, driver: webdriver.Chrome, account: Account) -> None:
        google_buttons = self._find_google_buttons(driver)
        if not google_buttons:
            triggers = self._find_login_triggers(driver)
            if triggers:
                self._safe_click(driver, triggers[0])
                time.sleep(1.0)
                google_buttons = self._find_google_buttons(driver)
        if not google_buttons:
            return
        original_handle = driver.current_window_handle
        handles_before = set(driver.window_handles)
        self._safe_click(driver, google_buttons[0])
        time.sleep(1.0)
        try:
            WebDriverWait(driver, 10).until(lambda d: len(d.window_handles) > len(handles_before))
        except TimeoutException:
            try:
                self._fill_google_popup(driver, account)
            except TimeoutException:
                return
            return
        new_handles = [handle for handle in driver.window_handles if handle not in handles_before]
        if not new_handles:
            return
        popup_handle = new_handles[0]
        driver.switch_to.window(popup_handle)
        try:
            self._fill_google_popup(driver, account)
        finally:
            try:
                self._wait_for_page_ready(driver, timeout=20)
            except Exception:  # pylint: disable=broad-except
                pass
            driver.close()
            driver.switch_to.window(original_handle)
            self._wait_for_page_ready(driver, timeout=30)

    def _fill_google_popup(self, driver: webdriver.Chrome, account: Account) -> None:
        wait = WebDriverWait(driver, 20)
        email_input = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='email']")))
        email_input.clear()
        email_input.send_keys(account.email)
        next_button = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "#identifierNext button, button[jsname='LgbsSe']"))
        )
        self._safe_click(driver, next_button)
        time.sleep(1.5)
        if account.password:
            try:
                password_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']")))
                password_input.clear()
                password_input.send_keys(account.password)
                password_next = wait.until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "#passwordNext button, button[jsname='LgbsSe']"))
                )
                self._safe_click(driver, password_next)
            except TimeoutException:
                pass
        if account.recovery_email:
            try:
                recovery_input = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='email'][name='email']"))
                )
                recovery_input.clear()
                recovery_input.send_keys(account.recovery_email)
                recovery_next = driver.find_element(By.CSS_SELECTOR, "button[jsname='LgbsSe']")
                self._safe_click(driver, recovery_next)
            except TimeoutException:
                pass

    def _find_google_buttons(self, driver: webdriver.Chrome):
        xpath = (
            "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'google')]"
            " | //a[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'google')]"
        )
        return driver.find_elements(By.XPATH, xpath)

    def _find_login_triggers(self, driver: webdriver.Chrome):
        xpath = (
            "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'login')]"
            " | //button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'sign in')]"
            " | //button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'sign up')]"
            " | //a[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'login')]"
            " | //a[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'sign in')]"
            " | //a[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'sign up')]"
        )
        return driver.find_elements(By.XPATH, xpath)

    def _safe_click(self, driver: webdriver.Chrome, element) -> None:
        try:
            element.click()
        except WebDriverException:
            driver.execute_script("arguments[0].click();", element)

    def _save_cookies(self, cookies: List[dict], status: SandboxStatus, final_url: str) -> None:
        if not cookies:
            status.message = "未获取到任何 Cookie"
            return
        if not status.email:
            status.email = status.account.email if status.account else "anonymous"
        cookie_filename = build_cookie_filename(status.email, final_url)
        file_path = self.cookies_dir / cookie_filename
        ensure_directory(file_path.parent)
        file_path.write_text(cookies_to_text(cookies), encoding="utf-8")
        status.cookie_file = file_path
        status.domain = urlparse(final_url).hostname
