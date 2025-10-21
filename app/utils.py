from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from .schemas import AccountCredential


def _split_with_primary_delimiter(text: str) -> List[str]:
    parts = re.split(r"[;；]\s*", text)
    if len(parts) >= 3:
        return [p.strip() for p in parts if p.strip()]

    trimmed = text.strip()
    email_match = re.match(r"\s*(?P<email>[^\s;]+@[^\s;]+)", trimmed)
    if not email_match:
        return [p.strip() for p in re.split(r"\s+", trimmed) if p.strip()]
    email = email_match.group("email")
    rest = trimmed[email_match.end():].lstrip(" -；;\t")
    if not rest:
        return [email]

    password, recovery = None, None
    # 优先按“-”拆分两次，避免邮箱中的-
    if "-" in rest:
        password_part, recovery_part = rest.split("-", 1)
        password = password_part.strip()
        recovery = recovery_part.strip()
    elif "；" in rest:
        password_part, recovery_part = rest.split("；", 1)
        password = password_part.strip()
        recovery = recovery_part.strip()
    elif ";" in rest:
        password_part, recovery_part = rest.split(";", 1)
        password = password_part.strip()
        recovery = recovery_part.strip()

    if password is None:
        parts = [seg.strip() for seg in rest.split() if seg.strip()]
        if parts:
            password = parts[0]
            recovery = parts[1] if len(parts) > 1 else ""

    if recovery and ("-" in recovery or ";" in recovery) and "@" not in recovery:
        recovery = recovery.replace("-", "").replace(";", "").strip()

    return [email, password or "", recovery or ""]


def parse_accounts_blob(blob: Optional[str]) -> List[AccountCredential]:
    if not blob:
        return []

    accounts: List[AccountCredential] = []
    for raw_line in blob.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = _split_with_primary_delimiter(line)
        if len(parts) < 3:
            raise ValueError(f"账号行无法识别: {raw_line}")
        email, password, recovery = parts[0], parts[1], parts[2]
        accounts.append(
            AccountCredential(email=email.strip(), password=password.strip(), recovery_email=recovery.strip())
        )
    return accounts


def sanitize_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9@._-]+", "_", name)


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
