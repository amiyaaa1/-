"""Utility helpers for generating random credentials."""

from __future__ import annotations

import random
import secrets
import string
from typing import Iterable


def generate_display_name() -> str:
    """Generate a simple random display name suitable for AWS Builder ID."""

    first_names = [
        "Alex",
        "Casey",
        "Jamie",
        "Morgan",
        "Riley",
        "Taylor",
        "Jordan",
        "Quinn",
    ]
    last_names = [
        "Anderson",
        "Carter",
        "Lee",
        "Parker",
        "Walker",
        "Brooks",
        "Murphy",
        "Hayes",
    ]
    return f"{random.choice(first_names)} {random.choice(last_names)}"


def generate_password(length: int, charset: Iterable[str] | str | None = None) -> str:
    """Generate a password that satisfies AWS Builder ID requirements."""

    if length < 12:
        length = 12
    if charset is None:
        charset = string.ascii_letters + string.digits + "!@#$%^&*()-_=+[]{}"
    pool = list(dict.fromkeys(charset))
    if not pool:
        raise ValueError("Charset must not be empty")

    categories = [
        set(string.ascii_lowercase),
        set(string.ascii_uppercase),
        set(string.digits),
        set("!@#$%^&*()-_=+[]{}"),
    ]

    password_chars: list[str] = []
    available = set(pool)
    for category in categories:
        intersection = list(category & available)
        if intersection:
            password_chars.append(secrets.choice(intersection))
        else:
            password_chars.append(secrets.choice(pool))

    while len(password_chars) < length:
        password_chars.append(secrets.choice(pool))

    random.shuffle(password_chars)
    return "".join(password_chars[:length])


def append_random_suffix(base: str, digits: int = 2) -> str:
    """Append a numeric suffix to match the AWS credential naming scheme."""

    suffix = ''.join(secrets.choice(string.digits) for _ in range(max(1, digits)))
    return f"{base}{suffix}"
