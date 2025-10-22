"""Utilities for generating AWS Builder ID compatible passwords."""

from __future__ import annotations

import random
import string
from typing import Iterable

from .config import AwsPasswordRule


def generate_password(rule: AwsPasswordRule, extra_symbols: Iterable[str] | None = None) -> str:
    """Generate a password satisfying the provided rule."""

    symbols = set("!@#$%^&*-_=+?" if extra_symbols is None else extra_symbols)
    if not symbols:
        symbols = set("!@#$%")

    choices = []
    if rule.include_upper:
        choices.append(random.choice(string.ascii_uppercase))
    if rule.include_lower:
        choices.append(random.choice(string.ascii_lowercase))
    if rule.include_digit:
        choices.append(random.choice(string.digits))
    if rule.include_symbol:
        choices.append(random.choice(list(symbols)))

    remaining_length = max(rule.min_length - len(choices), 0)
    alphabet = ""
    if rule.include_upper:
        alphabet += string.ascii_uppercase
    if rule.include_lower:
        alphabet += string.ascii_lowercase
    if rule.include_digit:
        alphabet += string.digits
    if rule.include_symbol:
        alphabet += "".join(symbols)
    if not alphabet:
        alphabet = string.ascii_letters + string.digits

    choices.extend(random.choice(alphabet) for _ in range(remaining_length))
    random.shuffle(choices)
    return "".join(choices)
