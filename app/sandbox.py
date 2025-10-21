from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

from playwright.async_api import BrowserContext, Error as PlaywrightError, Page, async_playwright

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

    _context: Optional[BrowserContext] = field(default=None, init=False, repr=False)
    _page: Optional[Page] = field(default=None, init=False, repr=False)
    _task: Optional[asyncio.Task] = field(default=None, init=False, repr=False)
    _stop_event: asyncio.Event = field(default_factory=asyncio.Event, init=False, repr=False)

    async def start(self, playwright, headless: bool) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._run(playwright, headless))

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        if self._page:
            with contextlib.suppress(PlaywrightError):
                await self._page.close()
        if self._context:
            with contextlib.suppress(PlaywrightError):
                await self._context.close()
        if self.profile_dir.exists():
            with contextlib.suppress(Exception):
                shutil.rmtree(self.profile_dir, ignore_errors=True)
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

    async def _run(self, playwright, headless: bool) -> None:
        try:
            ensure_directory(self.profile_dir)
            self._update_status("launching", "正在启动浏览器沙箱")
            launch_args = ["--disable-dev-shm-usage"]
            if os.geteuid() == 0:
                launch_args.append("--no-sandbox")

            browser_type = playwright.chromium
            channel = config.BROWSER_CHANNEL if config.BROWSER_CHANNEL != "chromium" else None
            if channel:
                self.log(f"使用浏览器通道: {channel}")

            self._context = await browser_type.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                headless=headless,
                channel=channel,
                args=launch_args,
            )
            self._page = await self._context.new_page()
            self._update_status("launched", "浏览器沙箱已启动")

            if self.enable_google_login and self.account:
                logged_in = await self._perform_google_login()
            else:
                logged_in = False

            if self.target_url:
                await self._open_target_url()
                if (
                    self.auto_site_login
                    and self.enable_google_login
                    and logged_in
                    and self.account is not None
                ):
                    await self._try_site_google_login()

            if self._page:
                await self._page.wait_for_load_state("networkidle")
                await asyncio.sleep(2)
                await self._save_cookies()
            self._update_status("ready", "自动化流程完成，沙箱保持运行")
        except asyncio.CancelledError:
            self.log("沙箱任务被取消")
            raise
        except Exception as exc:
            self._update_status("error", f"沙箱运行失败: {exc}")
            self.log(f"错误: {exc}")
        finally:
            self._stop_event.set()

    def _update_status(self, status: str, message: Optional[str] = None) -> None:
        self.status = status
        if message:
            self.message = message
            self.log(message)

    async def _perform_google_login(self) -> bool:
        assert self._page is not None
        self._update_status("google_login", "正在尝试谷歌登录")
        page = self._page
        try:
            await page.goto(
                "https://accounts.google.com/signin/v2/identifier?hl=zh-CN&flowName=GlifWebSignIn",
                wait_until="domcontentloaded",
            )
            await page.fill('input[type="email"]', self.account.email)
            await page.click('#identifierNext button, #identifierNext div[role="button"], #identifierNext')
            await page.wait_for_timeout(1000)
            await page.wait_for_selector('input[type="password"]', timeout=30000)
            await page.fill('input[type="password"]', self.account.password)
            await page.click('#passwordNext button, #passwordNext div[role="button"], #passwordNext')
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(1)

            # 处理可能的恢复邮箱验证
            try:
                recovery_selector = 'input[type="email"]'
                recovery_box = page.locator(recovery_selector)
                if await recovery_box.count() > 0:
                    body_text = await page.locator("body").inner_text()
                    if re.search("恢复邮箱|recovery email|verify", body_text, re.IGNORECASE):
                        if self.account.recovery_email:
                            await recovery_box.fill(self.account.recovery_email)
                            await page.click('button:has-text("下一步"), button:has-text("Next"), div[role="button"]:has-text("Next")')
                            await page.wait_for_load_state("networkidle", timeout=30000)
            except PlaywrightError as recovery_err:
                self.log(f"恢复邮箱步骤跳过: {recovery_err}")

            self.log("谷歌账号登录完成")
            return True
        except Exception as exc:
            self.log(f"谷歌登录失败: {exc}")
            return False

    async def _open_target_url(self) -> None:
        assert self._page is not None
        if not self.target_url:
            return
        self._update_status("opening", f"正在打开: {self.target_url}")
        try:
            await self._page.goto(self.target_url, wait_until="domcontentloaded")
            await self._page.wait_for_load_state("networkidle")
            self.log("目标页面加载完成")
        except Exception as exc:
            self.log(f"打开目标页面失败: {exc}")

    async def _try_site_google_login(self) -> None:
        assert self._page is not None
        self._update_status("site_login", "检测目标站点的谷歌登录入口")
        page = self._page
        try:
            triggered = await self._trigger_login_options(page)
            if triggered:
                await page.wait_for_timeout(1500)
            await self._click_google_login(page)
        except Exception as exc:
            self.log(f"站点谷歌登录过程失败: {exc}")

    async def _trigger_login_options(self, page: Page) -> bool:
        triggered = False
        for keyword in SITE_TRIGGER_KEYWORDS:
            try:
                locator = page.get_by_role("link", name=re.compile(keyword, re.IGNORECASE))
                if await locator.count() == 0:
                    locator = page.get_by_role("button", name=re.compile(keyword, re.IGNORECASE))
                if await locator.count() == 0:
                    locator = page.locator(f"text=/.*{re.escape(keyword)}.*/i")
                if await locator.count() > 0:
                    await locator.first.click()
                    await page.wait_for_timeout(800)
                    triggered = True
                    self.log(f"点击触发元素: {keyword}")
                    break
            except PlaywrightError:
                continue
        return triggered

    async def _click_google_login(self, page: Page) -> None:
        google_popup: Optional[Page] = None
        async def wait_for_popup():
            nonlocal google_popup
            try:
                google_popup = await page.context.wait_for_event("page", timeout=8000)
            except PlaywrightError:
                google_popup = None

        popup_task = asyncio.create_task(wait_for_popup())
        clicked = False
        for keyword in GOOGLE_LOGIN_KEYWORDS:
            locator = page.get_by_role("button", name=re.compile(keyword, re.IGNORECASE))
            if await locator.count() == 0:
                locator = page.locator(f"text=/.*{re.escape(keyword)}.*/i")
            if await locator.count() > 0:
                await locator.first.click()
                clicked = True
                self.log(f"点击Google登录按钮: {keyword}")
                break
        if not clicked:
            popup_task.cancel()
            return

        try:
            await popup_task
        except asyncio.CancelledError:
            pass

        if google_popup:
            await google_popup.wait_for_load_state("domcontentloaded")
            await self._handle_google_popup(google_popup)
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(1)

    async def _handle_google_popup(self, popup: Page) -> None:
        try:
            locator = popup.locator('div[data-identifier], div[role="link"]')
            if await locator.count() > 0 and self.account:
                matching = locator.filter(has_text=re.compile(re.escape(self.account.email), re.IGNORECASE))
                if await matching.count() > 0:
                    await matching.first.click()
                    self.log("在弹窗中选择了谷歌账号")
                else:
                    await locator.first.click()
                    self.log("在弹窗中选择默认谷歌账号")
            await popup.wait_for_timeout(2000)
        except PlaywrightError as exc:
            self.log(f"弹窗处理失败: {exc}")
        finally:
            try:
                await popup.close()
            except PlaywrightError:
                pass

    async def _save_cookies(self) -> None:
        assert self._context is not None and self._page is not None
        cookies = await self._context.cookies()
        url = self._page.url
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
        self._playwright = None
        self._sandboxes: Dict[str, SandboxSession] = {}
        self._lock = asyncio.Lock()

    async def startup(self) -> None:
        if self._playwright is None:
            self._playwright = await async_playwright().start()
            logger.info("Playwright 已启动")

    async def shutdown(self) -> None:
        async with self._lock:
            sandboxes = list(self._sandboxes.values())
            self._sandboxes.clear()
        for sandbox in sandboxes:
            await sandbox.stop()
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
            logger.info("Playwright 已关闭")

    async def create_sandboxes(
        self,
        count: int,
        target_url: Optional[str],
        enable_google_login: bool,
        auto_site_login: bool,
        accounts_blob: Optional[str],
    ) -> List[SandboxSession]:
        if self._playwright is None:
            raise RuntimeError("Playwright 尚未初始化")

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
            await sandbox.start(self._playwright, config.HEADLESS)

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
