import re
from typing import List, Dict


ACCOUNT_PATTERN = re.compile(r"^\s*([^\s;,|]+@[^\s;,|]+)")
SEPARATOR_PATTERN = re.compile(r"^[\s\-;,|]+")
SPLIT_PATTERN = re.compile(r"[\s\-;,|]+")


def parse_accounts(raw: str) -> List[Dict[str, str]]:
    """Parse flexible account text into structured dictionaries.

    Supports inputs like:
    - email-password-recovery
    - email;password;recovery
    - email password recovery
    """
    accounts: List[Dict[str, str]] = []
    if not raw:
        return accounts

    for line in raw.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        match = ACCOUNT_PATTERN.match(cleaned)
        if not match:
            continue
        email = match.group(1).strip()
        remainder = cleaned[match.end():]
        if remainder:
            remainder = SEPARATOR_PATTERN.sub("", remainder)
        parts = [p for p in SPLIT_PATTERN.split(remainder) if p]
        password = parts[0] if len(parts) >= 1 else ""
        recovery = parts[1] if len(parts) >= 2 else ""
        accounts.append({
            "email": email,
            "password": password,
            "recovery": recovery,
        })
    return accounts
