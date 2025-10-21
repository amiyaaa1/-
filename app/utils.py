from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional
from urllib.parse import urlparse


EMAIL_PATTERN = re.compile(r"([A-Za-z0-9_.+\-]+@[A-Za-z0-9_.\-]+)")
SEPARATOR_PATTERN = re.compile(r"[;\s\|,]+|\s*-\s*")


@dataclass
class Account:
    email: str
    password: Optional[str] = None
    recovery_email: Optional[str] = None


def parse_accounts(raw: str) -> List[Account]:
    accounts: List[Account] = []
    for line in raw.splitlines():
        candidate = line.strip()
        if not candidate:
            continue
        match = EMAIL_PATTERN.search(candidate)
        if not match:
            continue
        email = match.group(1)
        remainder = candidate[: match.start()] + candidate[match.end() :]
        tokens = [token for token in SEPARATOR_PATTERN.split(remainder) if token]
        password = tokens[0] if tokens else None
        recovery_email: Optional[str] = None
        if len(tokens) >= 2 and EMAIL_PATTERN.fullmatch(tokens[1]):
            recovery_email = tokens[1]
        elif len(tokens) >= 2:
            recovery_email = tokens[1]
        accounts.append(Account(email=email, password=password, recovery_email=recovery_email))
    return accounts


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def slugify_filename(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", value)
    return safe


def build_cookie_filename(email: str, url: str) -> str:
    parsed = urlparse(url)
    domain = parsed.hostname or "unknown"
    return f"{slugify_filename(email)}-{domain}.txt"


def cookies_to_text(cookies: Iterable[dict]) -> str:
    lines = []
    for cookie in cookies:
        name = cookie.get("name", "")
        value = cookie.get("value", "")
        parts = [f"{name}={value}"]
        domain = cookie.get("domain")
        if domain:
            parts.append(f"domain={domain}")
        path = cookie.get("path")
        if path:
            parts.append(f"path={path}")
        expires = cookie.get("expires") or cookie.get("expiry")
        if expires:
            parts.append(f"expires={expires}")
        secure = cookie.get("secure")
        if secure is not None:
            parts.append(f"secure={secure}")
        http_only = cookie.get("httpOnly")
        if http_only is not None:
            parts.append(f"httpOnly={http_only}")
        same_site = cookie.get("sameSite")
        if same_site:
            parts.append(f"sameSite={same_site}")
        lines.append("; ".join(parts))
    return "\n".join(lines)
