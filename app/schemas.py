from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator


class AccountCredential(BaseModel):
    email: str
    password: str
    recovery_email: Optional[str] = None


class SandboxCreateRequest(BaseModel):
    count: int = Field(gt=0, description="需要启动的沙箱数量")
    target_url: Optional[HttpUrl] = Field(None, description="默认打开的链接")
    enable_google_login: bool = Field(False, description="是否启用谷歌自动登录")
    auto_site_login: bool = Field(False, description="是否在目标网站尝试使用谷歌账号登录")
    accounts_blob: Optional[str] = Field(
        None, description="批量账号字符串，每行一个账号，可使用-或;分隔"
    )

    @field_validator("accounts_blob", mode="before")
    @classmethod
    def normalize_empty(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = value.strip()
        return stripped if stripped else None


class SandboxInfo(BaseModel):
    id: str
    status: str
    message: Optional[str] = None
    created_at: datetime
    target_url: Optional[str]
    enable_google_login: bool
    auto_site_login: bool
    account_email: Optional[str]
    cookie_file: Optional[str]
    logs: List[str]


class SandboxListResponse(BaseModel):
    sandboxes: List[SandboxInfo]


class CookieFileInfo(BaseModel):
    filename: str
    email: str
    domain: str
    url: str


class CookieListResponse(BaseModel):
    cookies: List[CookieFileInfo]
