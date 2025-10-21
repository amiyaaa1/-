import asyncio
import os
import shutil
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver import ChromeOptions
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager


COOKIE_TEMPLATE = "{name}={value}; Domain={domain}; Path={path}; Expires={expires}; Secure={secure}; HttpOnly={httpOnly}"
UPPERCASE = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
LOWERCASE = "abcdefghijklmnopqrstuvwxyz"


@dataclass
class Sandbox:
    id: str
    default_url: str
    google_login: bool
    auto_site_login: bool
    email: Optional[str] = None
    status: str = "pending"
    log: List[str] = field(default_factory=list)
    cookie_file: Optional[str] = None
    task: Optional[asyncio.Task] = None
    user_data_dir: Optional[Path] = None
    driver: Optional[WebDriver] = None
    stop_event: Event = field(default_factory=Event)


class SandboxCancelled(Exception):
    """Raised when sandbox execution is cancelled."""
    pass


class SandboxManager:
    def __init__(self, sandboxes_root: Path, cookies_root: Path) -> None:
        self.sandboxes_root = sandboxes_root
        self.cookies_root = cookies_root
        self.sandboxes: Dict[str, Sandbox] = {}
        self._driver_path: Optional[str] = None
        self._executor: Optional[ThreadPoolExecutor] = None
        self._lock = asyncio.Lock()
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        loop = asyncio.get_running_loop()
        self._driver_path = await loop.run_in_executor(None, lambda: ChromeDriverManager().install())
        max_workers = max(4, (os.cpu_count() or 2) * 2)
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self.sandboxes_root.mkdir(parents=True, exist_ok=True)
        self.cookies_root.mkdir(parents=True, exist_ok=True)
        self._started = True

    async def stop(self) -> None:
        async with self._lock:
            sandboxes = list(self.sandboxes.values())
            self.sandboxes.clear()
        for sandbox in sandboxes:
            sandbox.stop_event.set()
            if sandbox.task and not sandbox.task.done():
                try:
                    await sandbox.task
                except Exception:
                    pass
            await self._close_sandbox(sandbox)
        if self._executor:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None
        self._driver_path = None
        self._started = False

    async def create_sandboxes(
        self,
        count: int,
        default_url: str,
        google_login: bool,
        auto_site_login: bool,
        accounts: List[Dict[str, str]],
    ) -> List[str]:
        ids: List[str] = []
        async with self._lock:
            for index in range(count):
                sandbox_id = f"sb-{uuid.uuid4().hex[:8]}-{int(time.time()*1000)}"
                sandbox = Sandbox(
                    id=sandbox_id,
                    default_url=default_url,
                    google_login=google_login,
                    auto_site_login=auto_site_login,
                )
                if google_login and index < len(accounts):
                    sandbox.email = accounts[index].get("email")
                sandbox.user_data_dir = self.sandboxes_root / sandbox_id
                sandbox.user_data_dir.mkdir(parents=True, exist_ok=True)
                self.sandboxes[sandbox_id] = sandbox
                account = accounts[index] if google_login and index < len(accounts) else None
                task = asyncio.create_task(self._run_sandbox(sandbox, account=account))
                task.add_done_callback(lambda _: setattr(sandbox, "task", None))
                sandbox.task = task
                ids.append(sandbox_id)
        return ids

    async def list_sandboxes(self) -> List[Dict[str, object]]:
        async with self._lock:
            sandboxes = list(self.sandboxes.values())
        response: List[Dict[str, object]] = []
        for sandbox in sandboxes:
            response.append(
                {
                    "id": sandbox.id,
                    "email": sandbox.email,
                    "status": sandbox.status,
                    "default_url": sandbox.default_url,
                    "google_login": sandbox.google_login,
                    "auto_site_login": sandbox.auto_site_login,
                    "cookie_file": sandbox.cookie_file,
                    "log": list(sandbox.log[-50:]),
                }
            )
        return response

    async def delete_sandbox(self, sandbox_id: str) -> bool:
        async with self._lock:
            sandbox = self.sandboxes.pop(sandbox_id, None)
        if not sandbox:
            return False
        sandbox.stop_event.set()
        if sandbox.driver:
            try:
                sandbox.driver.quit()
            except Exception:
                pass
        if sandbox.task and not sandbox.task.done():
            try:
                await sandbox.task
            except asyncio.CancelledError:
                pass
            except Exception as exc:  # pragma: no cover - defensive log
                self._append_log(sandbox, f"任务取消时出现异常: {exc}")
        await self._close_sandbox(sandbox)
        if sandbox.user_data_dir and sandbox.user_data_dir.exists():
            shutil.rmtree(sandbox.user_data_dir, ignore_errors=True)
        return True

    async def _close_sandbox(self, sandbox: Sandbox) -> None:
        if sandbox.driver:
            try:
                sandbox.driver.quit()
            except Exception as exc:  # pragma: no cover
                self._append_log(sandbox, f"关闭浏览器失败: {exc}")
        sandbox.driver = None

    def _append_log(self, sandbox: Sandbox, message: str) -> None:
        entry = f"[{time.strftime('%H:%M:%S')}] {message}"
        sandbox.log.append(entry)

    async def _run_sandbox(self, sandbox: Sandbox, account: Optional[Dict[str, str]]) -> None:
        if not self._executor or not self._driver_path:
            sandbox.status = "error"
            self._append_log(sandbox, "Chrome 驱动未准备好")
            return
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                self._executor,
                self._run_sandbox_sync,
                sandbox,
                account,
            )
        except asyncio.CancelledError:
            sandbox.status = "cancelled"
            self._append_log(sandbox, "沙箱任务已被取消")
            raise
        except Exception as exc:
            sandbox.status = "error"
            self._append_log(sandbox, f"沙箱运行失败: {exc}")

    def _run_sandbox_sync(self, sandbox: Sandbox, account: Optional[Dict[str, str]]) -> None:
        driver: Optional[WebDriver] = None
        try:
            self._ensure_not_cancelled(sandbox)
            sandbox.status = "initializing"
            self._append_log(sandbox, "正在创建独立浏览器实例")
            driver = self._launch_driver(sandbox)
            sandbox.driver = driver
            self._ensure_not_cancelled(sandbox)
            if sandbox.google_login and account:
                self._login_google_sync(sandbox, driver, account)
                self._ensure_not_cancelled(sandbox)
            self._open_default_url_sync(sandbox, driver)
            self._ensure_not_cancelled(sandbox)
            if sandbox.google_login and sandbox.auto_site_login:
                self._attempt_site_google_login_sync(sandbox, driver)
                self._ensure_not_cancelled(sandbox)
            self._store_cookies_sync(sandbox, driver)
            sandbox.status = "ready"
            self._append_log(sandbox, "沙箱已完成启动流程")
        except SandboxCancelled:
            sandbox.status = "cancelled"
            self._append_log(sandbox, "沙箱任务已被取消")
        except Exception as exc:
            sandbox.status = "error"
            self._append_log(sandbox, f"沙箱运行失败: {exc}")
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
            sandbox.driver = None

    def _ensure_not_cancelled(self, sandbox: Sandbox) -> None:
        if sandbox.stop_event.is_set():
            raise SandboxCancelled()

    def _launch_driver(self, sandbox: Sandbox) -> WebDriver:
        if not self._driver_path:
            raise RuntimeError("Chrome 驱动未准备好")
        options = ChromeOptions()
        if sandbox.user_data_dir:
            options.add_argument(f"--user-data-dir={os.fspath(sandbox.user_data_dir)}")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--window-size=1280,720")
        options.add_argument("--lang=zh-CN")
        options.add_argument("--headless=new")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        binary_location = os.getenv("CHROME_BINARY")
        if binary_location:
            options.binary_location = binary_location
        service = Service(self._driver_path)
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(60)
        return driver

    def _login_google_sync(self, sandbox: Sandbox, driver: WebDriver, account: Dict[str, str]) -> None:
        sandbox.status = "google_login"
        self._append_log(sandbox, f"正在登录 Google: {account.get('email')}")
        try:
            driver.get("https://accounts.google.com/signin/v2/identifier")
            wait = WebDriverWait(driver, 20)
            email_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='email']")))
            email_input.clear()
            email_input.send_keys(account.get("email", ""))
            first_step = [
                (By.ID, "identifierNext"),
                (By.XPATH, "//button[contains(., '下一步')]"),
                (By.XPATH, "//button[contains(., 'Next')]"),
            ]
            self._click_candidates(sandbox, driver, wait, first_step)
            password_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']")))
            password_input.clear()
            password_input.send_keys(account.get("password", ""))
            second_step = [
                (By.ID, "passwordNext"),
                (By.XPATH, "//button[contains(., '下一步')]"),
                (By.XPATH, "//button[contains(., 'Next')]"),
            ]
            self._click_candidates(sandbox, driver, wait, second_step)
            try:
                wait.until(lambda drv: "accounts.google.com" not in drv.current_url or "signin" not in drv.current_url)
            except TimeoutException:
                self._append_log(sandbox, "等待 Google 登录完成超时，继续后续流程")
        except TimeoutException as exc:
            self._append_log(sandbox, f"Google 登录操作超时: {exc}")
        except WebDriverException as exc:
            self._append_log(sandbox, f"Google 登录时出现错误: {exc}")
        else:
            self._append_log(sandbox, "Google 登录步骤已执行")

    def _open_default_url_sync(self, sandbox: Sandbox, driver: WebDriver) -> None:
        sandbox.status = "navigating"
        self._append_log(sandbox, f"正在打开默认链接: {sandbox.default_url}")
        try:
            driver.get(sandbox.default_url)
            self._wait_for_page_ready(driver)
        except WebDriverException as exc:
            self._append_log(sandbox, f"打开默认链接失败: {exc}")
        else:
            self._append_log(sandbox, "默认页面加载完成")

    def _attempt_site_google_login_sync(self, sandbox: Sandbox, driver: WebDriver) -> None:
        sandbox.status = "site_login"
        self._append_log(sandbox, "尝试识别站点中的 Google 登录入口")
        login_texts = [
            "login",
            "log in",
            "sign in",
            "sign up",
            "注册",
            "登录",
            "登入",
            "加入",
        ]
        google_texts = [
            "google",
            "使用 google",
            "continue with google",
            "sign in with google",
            "log in with google",
            "login with google",
            "谷歌",
        ]
        try:
            for text in login_texts:
                self._ensure_not_cancelled(sandbox)
                if self._click_by_text(driver, text):
                    time.sleep(1)
            clicked_google = False
            for text in google_texts:
                self._ensure_not_cancelled(sandbox)
                if self._click_by_text(driver, text):
                    clicked_google = True
                    break
            if clicked_google:
                self._append_log(sandbox, "已点击站点中的 Google 登录入口")
                self._handle_possible_popup(sandbox, driver)
            else:
                self._append_log(sandbox, "未在页面上找到 Google 登录选项")
        except TimeoutException:
            self._append_log(sandbox, "等待站点登录流程时超时")
        except WebDriverException as exc:
            self._append_log(sandbox, f"站点登录过程中出现错误: {exc}")

    def _store_cookies_sync(self, sandbox: Sandbox, driver: WebDriver) -> None:
        sandbox.status = "saving_cookies"
        try:
            cookies = driver.get_cookies()
            current_url = driver.current_url or sandbox.default_url
            domain = urlparse(current_url).netloc or "unknown"
            safe_domain = domain.replace(":", "_")
            prefix = sandbox.email or "anonymous"
            filename = f"{prefix}-{safe_domain}.txt"
            path = self.cookies_root / filename
            with path.open("w", encoding="utf-8") as handler:
                for cookie in cookies:
                    expires = cookie.get("expiry") or cookie.get("expires", "")
                    handler.write(
                        COOKIE_TEMPLATE.format(
                            name=cookie.get("name", ""),
                            value=cookie.get("value", ""),
                            domain=cookie.get("domain", ""),
                            path=cookie.get("path", ""),
                            expires=expires,
                            secure=cookie.get("secure", False),
                            httpOnly=cookie.get("httpOnly", False),
                        )
                        + "\n"
                    )
            sandbox.cookie_file = path.name
            self._append_log(sandbox, f"Cookie 已保存到 {filename}")
        except Exception as exc:
            self._append_log(sandbox, f"保存 Cookie 失败: {exc}")

    def _click_candidates(
        self,
        sandbox: Sandbox,
        driver: WebDriver,
        wait: WebDriverWait,
        candidates: List[Tuple[str, str]],
    ) -> None:
        for by, value in candidates:
            self._ensure_not_cancelled(sandbox)
            try:
                element = wait.until(EC.element_to_be_clickable((by, value)))
            except TimeoutException:
                continue
            try:
                element.click()
                return
            except WebDriverException:
                continue

    def _click_by_text(self, driver: WebDriver, keyword: str) -> bool:
        lowered = keyword.lower()
        tags = ["button", "a", "div", "span"]
        for tag in tags:
            xpath = (
                f"//{tag}[contains(translate(normalize-space(.), '{UPPERCASE}', "
                f"'{LOWERCASE}'), '{lowered}')]"
            )
            try:
                elements = driver.find_elements(By.XPATH, xpath)
            except WebDriverException:
                continue
            for element in elements:
                if not element.is_displayed():
                    continue
                try:
                    element.click()
                    return True
                except WebDriverException:
                    continue
        return False

    def _handle_possible_popup(self, sandbox: Sandbox, driver: WebDriver) -> None:
        main_handle = driver.current_window_handle
        initial_handles = set(driver.window_handles)
        end_time = time.time() + 20
        popup_handle: Optional[str] = None
        while time.time() < end_time:
            self._ensure_not_cancelled(sandbox)
            handles = set(driver.window_handles)
            new_handles = handles - initial_handles
            if new_handles:
                popup_handle = new_handles.pop()
                break
            time.sleep(1)
        if popup_handle:
            try:
                driver.switch_to.window(popup_handle)
                self._wait_for_page_ready(driver, timeout=30)
                time.sleep(2)
            except WebDriverException:
                pass
            finally:
                try:
                    driver.switch_to.window(main_handle)
                    self._wait_for_page_ready(driver, timeout=20)
                except WebDriverException:
                    pass
        else:
            try:
                self._wait_for_page_ready(driver, timeout=20)
            except WebDriverException:
                pass

    def _wait_for_page_ready(self, driver: WebDriver, timeout: int = 20) -> None:
        end_time = time.time() + timeout
        while time.time() < end_time:
            try:
                ready_state = driver.execute_script("return document.readyState")
                if ready_state == "complete":
                    return
            except WebDriverException:
                time.sleep(1)
            else:
                time.sleep(0.5)
        raise TimeoutException("等待页面加载完成超时")
