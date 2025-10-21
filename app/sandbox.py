from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from . import config
from .schemas import AccountCredential, SandboxInfo
from .utils import ensure_directory, parse_accounts_blob, sanitize_filename

logger = logging.getLogger(__name__)

SITE_TRIGGER_KEYWORDS = [
    "登录",
    "登入",
    "注册",
    "Sign in",
    "Sign up",
    "Log in",
    "Join",
]

GOOGLE_LOGIN_KEYWORDS = [
    "使用 Google 登录",
    "使用 Google 继续",
    "使用 Google 账号",
    "Sign in with Google",
    "Continue with Google",
    "Google 登录",
    "Google",
]


@dataclass
class SandboxSession:
    target_url: Optional[str]
    enable_google_login: bool
    auto_site_login: bool
    account: Optional[AccountCredential]
    profile_dir: Path

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.utcnow)
    status: str = "pending"
    message: Optional[str] = None
    logs: List[str] = field(default_factory=list)
    cookie_file: Optional[str] = None

    _task: Optional[asyncio.Task] = field(default=None, init=False, repr=False)
    _driver: Optional[webdriver.Chrome] = field(default=None, init=False, repr=False)
    _stop_flag: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _log_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    async def start(self, headless: bool) -> None:
        if self._task and not self._task.done():
            return
        self._stop_flag.clear()
        self._task = asyncio.create_task(self._run_async(headless=headless))

    async def stop(self) -> None:
        self._stop_flag.set()
        driver = self._driver
        if driver is not None:
            await asyncio.to_thread(self._safe_quit_driver)
        if self._task:
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self.profile_dir.exists():
            await asyncio.to_thread(shutil.rmtree, self.profile_dir, True)
        self.status = "stopped"
        self.message = "沙箱已停止"
        self.log("沙箱已停止")

    async def wait_finished(self) -> None:
        if self._task:
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    def log(self, text: str) -> None:
        timestamp = datetime.utcnow().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {text}"
        with self._log_lock:
            self.logs.append(entry)
            if len(self.logs) > 200:
                self.logs = self.logs[-200:]
        logger.info("%s: %s", self.id, text)

    def to_dict(self) -> SandboxInfo:
        return SandboxInfo(
            id=self.id,
            status=self.status,
            message=self.message,
            created_at=self.created_at,
            target_url=self.target_url,
            enable_google_login=self.enable_google_login,
            auto_site_login=self.auto_site_login,
            account_email=self.account.email if self.account else None,
            cookie_file=self.cookie_file,
            logs=list(self.logs[-20:]),
        )

    async def _run_async(self, headless: bool) -> None:
        try:
            await asyncio.to_thread(self._run_blocking, headless)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if not self._stop_flag.is_set():
                self._update_status("error", f"沙箱运行失败: {exc}")
                self.log(f"错误: {exc}")

    def _run_blocking(self, headless: bool) -> None:
        driver: Optional[webdriver.Chrome] = None
        try:
            ensure_directory(self.profile_dir)
            self._update_status("launching", "正在启动浏览器沙箱")
            options = ChromeOptions()
            options.add_argument(f"--user-data-dir={self.profile_dir}")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1280,720")
            if headless:
                options.add_argument("--headless=new")
            if os.name != "nt":
                try:
                    if os.geteuid() == 0:
                        options.add_argument("--no-sandbox")
                except AttributeError:
                    pass
            if config.CHROME_BINARY:
                options.binary_location = config.CHROME_BINARY
                self.log(f"使用自定义 Chrome 路径: {config.CHROME_BINARY}")

            driver = webdriver.Chrome(options=options)
            driver.set_page_load_timeout(90)
            self._driver = driver
            self._update_status("launched", "浏览器沙箱已启动")

            logged_in = False
            if self.enable_google_login and self.account and not self._stop_flag.is_set():
                logged_in = self._perform_google_login(driver)

            if self.target_url and not self._stop_flag.is_set():
                self._open_target_url(driver)
                if (
                    self.auto_site_login
                    and self.enable_google_login
                    and logged_in
                    and self.account is not None
                    and not self._stop_flag.is_set()
                ):
                    self._try_site_google_login(driver)

            if not self._stop_flag.is_set():
                self._save_cookies(driver)
                self._update_status("ready", "自动化流程完成，沙箱保持运行")

            while not self._stop_flag.wait(timeout=1):
                if self._driver is None:
                    break
        except WebDriverException as exc:
            if not self._stop_flag.is_set():
                self._update_status("error", f"浏览器异常: {exc}")
                self.log(f"浏览器异常: {exc}")
        except Exception as exc:
            if not self._stop_flag.is_set():
                self._update_status("error", f"沙箱运行失败: {exc}")
                self.log(f"错误: {exc}")
        finally:
            if driver is not None:
                with contextlib.suppress(Exception):
                    driver.quit()
            self._driver = None

    def _safe_quit_driver(self) -> None:
        driver = self._driver
        if driver is not None:
            with contextlib.suppress(Exception):
                driver.quit()
        self._driver = None

    def _update_status(self, status: str, message: Optional[str] = None) -> None:
        self.status = status
        if message:
            self.message = message
            self.log(message)

    def _perform_google_login(self, driver: webdriver.Chrome) -> bool:
        assert self.account is not None
        try:
            self._update_status("google_login", "正在尝试谷歌登录")
            driver.get(
                "https://accounts.google.com/signin/v2/identifier?hl=zh-CN&flowName=GlifWebSignIn"
            )
            wait = WebDriverWait(driver, 30)
            email_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="email"]')))
            email_input.clear()
            email_input.send_keys(self.account.email)
            wait.until(EC.element_to_be_clickable((By.ID, "identifierNext"))).click()
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="password"]')))
            password_input = driver.find_element(By.CSS_SELECTOR, 'input[type="password"]')
            password_input.clear()
            password_input.send_keys(self.account.password)
            wait.until(EC.element_to_be_clickable((By.ID, "passwordNext"))).click()
            time.sleep(2)

            if self.account.recovery_email:
                try:
                    recovery_input = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="email"]'))
                    )
                    page_text = driver.page_source.lower()
                    if "恢复" in page_text or "recovery" in page_text:
                        recovery_input.clear()
                        recovery_input.send_keys(self.account.recovery_email)
                        recovery_input.send_keys(Keys.ENTER)
                        time.sleep(2)
                except TimeoutException:
                    pass

            try:
                wait.until(lambda d: "signin" not in d.current_url or self._stop_flag.is_set())
            except TimeoutException:
                pass
            self.log("谷歌账号登录完成")
            return True
        except Exception as exc:
            if not self._stop_flag.is_set():
                self.log(f"谷歌登录失败: {exc}")
            return False

    def _open_target_url(self, driver: webdriver.Chrome) -> None:
        assert self.target_url is not None
        self._update_status("opening", f"正在打开: {self.target_url}")
        try:
            driver.get(self.target_url)
            WebDriverWait(driver, 30).until(lambda d: d.execute_script("return document.readyState") == "complete")
            time.sleep(1)
            self.log("目标页面加载完成")
        except Exception as exc:
            if not self._stop_flag.is_set():
                self.log(f"打开目标页面失败: {exc}")

    def _try_site_google_login(self, driver: webdriver.Chrome) -> None:
        self._update_status("site_login", "检测目标站点的谷歌登录入口")
        try:
            triggered = self._trigger_login_options(driver)
            if triggered:
                time.sleep(1.5)
            self._click_google_login(driver)
        except Exception as exc:
            if not self._stop_flag.is_set():
                self.log(f"站点谷歌登录过程失败: {exc}")

    def _trigger_login_options(self, driver: webdriver.Chrome) -> bool:
        clickable = driver.find_elements(By.CSS_SELECTOR, "a, button, [role='button']")
        for element in clickable:
            if not element.is_displayed():
                continue
            label = (element.text or "").strip()
            if not label:
                label = (element.get_attribute("aria-label") or "").strip()
            if not label:
                continue
            label_lower = label.lower()
            for keyword in SITE_TRIGGER_KEYWORDS:
                key_lower = keyword.lower()
                if key_lower in label_lower or keyword in label:
                    try:
                        element.click()
                        self.log(f"点击触发元素: {keyword}")
                        return True
                    except (ElementClickInterceptedException, WebDriverException):
                        continue
        return False

    def _find_clickable_by_keyword(self, driver: webdriver.Chrome, keyword: str):
        locator_css = [
            (By.CSS_SELECTOR, "button"),
            (By.CSS_SELECTOR, "a"),
            (By.CSS_SELECTOR, "[role='button']"),
        ]
        keyword_lower = keyword.lower()
        for by, selector in locator_css:
            elements = driver.find_elements(by, selector)
            for element in elements:
                if not element.is_displayed():
                    continue
                text = (element.text or "").strip()
                if not text:
                    text = (element.get_attribute("aria-label") or "").strip()
                if not text:
                    continue
                text_lower = text.lower()
                if keyword_lower in text_lower or keyword in text:
                    return element
        return None

    def _click_google_login(self, driver: webdriver.Chrome) -> None:
        original_handle = driver.current_window_handle
        handles_before = set(driver.window_handles)
        clicked = False
        for keyword in GOOGLE_LOGIN_KEYWORDS:
            element = self._find_clickable_by_keyword(driver, keyword)
            if element is None:
                continue
            try:
                element.click()
                self.log(f"点击Google登录按钮: {keyword}")
                clicked = True
                break
            except (ElementClickInterceptedException, WebDriverException) as exc:
                self.log(f"点击 Google 登录按钮失败 ({keyword}): {exc}")
        if not clicked:
            return

        time.sleep(2)
        handles_after = set(driver.window_handles)
        new_handles = [handle for handle in handles_after if handle not in handles_before]
        for handle in new_handles:
            self._handle_google_popup(driver, handle, original_handle)

        driver.switch_to.window(original_handle)
        try:
            WebDriverWait(driver, 15).until(lambda d: d.current_url != "about:blank")
        except TimeoutException:
            pass

    def _handle_google_popup(self, driver: webdriver.Chrome, popup_handle: str, original_handle: str) -> None:
        try:
            driver.switch_to.window(popup_handle)
            time.sleep(1)
            if self.account:
                selectors = [
                    (By.XPATH, f"//div[contains(@data-identifier, '{self.account.email}')]"),
                    (By.XPATH, f"//div[contains(text(), '{self.account.email}')]"),
                    (By.CSS_SELECTOR, 'div[role="link"]'),
                ]
                for by, selector in selectors:
                    try:
                        candidates = driver.find_elements(by, selector)
                    except NoSuchElementException:
                        candidates = []
                    if candidates:
                        candidates[0].click()
                        self.log("在弹窗中选择了谷歌账号")
                        break
            time.sleep(2)
        except WebDriverException as exc:
            if not self._stop_flag.is_set():
                self.log(f"弹窗处理失败: {exc}")
        finally:
            with contextlib.suppress(WebDriverException):
                driver.close()
            driver.switch_to.window(original_handle)

    def _save_cookies(self, driver: webdriver.Chrome) -> None:
        try:
            cookies = driver.get_cookies()
        except WebDriverException as exc:
            if not self._stop_flag.is_set():
                self.log(f"获取 Cookie 失败: {exc}")
            return
        url = driver.current_url
        parsed = urlparse(url)
        domain = parsed.hostname or "unknown"
        email_part = self.account.email if self.account else "anonymous"
        filename = f"{sanitize_filename(email_part)}-{sanitize_filename(domain)}.txt"
        file_path = config.COOKIE_DIR / filename
        data = {
            "email": email_part,
            "domain": domain,
            "url": url,
            "cookies": cookies,
            "timestamp": datetime.utcnow().isoformat(),
        }
        file_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.cookie_file = filename
        self.log(f"已保存Cookie文件: {filename}")


class SandboxManager:
    def __init__(self) -> None:
        self._sandboxes: Dict[str, SandboxSession] = {}
        self._lock = asyncio.Lock()

    async def startup(self) -> None:
        logger.info("SandboxManager 启动完成")

    async def shutdown(self) -> None:
        async with self._lock:
            sandboxes = list(self._sandboxes.values())
            self._sandboxes.clear()
        for sandbox in sandboxes:
            await sandbox.stop()
        logger.info("SandboxManager 已关闭")

    async def create_sandboxes(
        self,
        count: int,
        target_url: Optional[str],
        enable_google_login: bool,
        auto_site_login: bool,
        accounts_blob: Optional[str],
    ) -> List[SandboxSession]:
        accounts = parse_accounts_blob(accounts_blob)
        if enable_google_login and len(accounts) < count:
            raise ValueError("谷歌账号数量不足以分配给所有沙箱")

        created: List[SandboxSession] = []
        async with self._lock:
            for index in range(count):
                account = accounts[index] if enable_google_login else None
                profile_dir = config.PROFILE_DIR / f"sandbox_{uuid.uuid4().hex}"
                sandbox = SandboxSession(
                    target_url=target_url,
                    enable_google_login=enable_google_login,
                    auto_site_login=auto_site_login,
                    account=account,
                    profile_dir=profile_dir,
                )
                self._sandboxes[sandbox.id] = sandbox
                created.append(sandbox)

        for sandbox in created:
            await sandbox.start(config.HEADLESS)

        return created

    async def remove_sandbox(self, sandbox_id: str) -> None:
        async with self._lock:
            sandbox = self._sandboxes.pop(sandbox_id, None)
        if sandbox is None:
            raise KeyError("指定的沙箱不存在")
        await sandbox.stop()

    async def list_sandboxes(self) -> List[SandboxSession]:
        async with self._lock:
            return list(self._sandboxes.values())

    async def get_sandbox(self, sandbox_id: str) -> SandboxSession:
        async with self._lock:
            sandbox = self._sandboxes.get(sandbox_id)
        if sandbox is None:
            raise KeyError("指定的沙箱不存在")
        return sandbox


manager = SandboxManager()
