from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, HttpUrl, validator


class SandboxLaunchRequest(BaseModel):
    count: int = Field(gt=0, description="需要启动的沙箱数量")
    start_url: HttpUrl = Field(description="默认打开的链接")
    accounts_raw: str = Field(default="", description="账号原始文本")
    enable_google_login: bool = Field(default=False, description="是否启用谷歌自动登录")
    enable_site_google_registration: bool = Field(
        default=False,
        description="是否在目标站点自动触发谷歌登录/注册",
    )
    headless: bool = Field(default=False, description="是否以无头模式运行浏览器")

    @validator("accounts_raw")
    def normalize_accounts(cls, value: str) -> str:
        return value or ""


class SandboxStatusResponse(BaseModel):
    id: str
    email: Optional[str]
    start_url: str
    domain: Optional[str]
    state: str
    message: Optional[str]
    cookie_ready: bool
    created_at: datetime
    download_url: Optional[str]


class SandboxListResponse(BaseModel):
    items: List[SandboxStatusResponse]


class SandboxStartResponse(BaseModel):
    items: List[SandboxStatusResponse]
