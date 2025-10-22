"""Common models for the authentication workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class AuthResult:
    """Result of a successful authentication flow."""

    email: str
    provider: str
    metadata: Dict[str, str]
    password: Optional[str] = None
