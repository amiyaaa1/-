"""Custom exceptions for the automation project."""

from __future__ import annotations


class AutomationError(Exception):
    """Base exception for automation-specific errors."""


class AuthUrlTimeoutError(AutomationError):
    """Raised when the OAuth URL cannot be captured in time."""


class CredentialTimeoutError(AutomationError):
    """Raised when new credentials are not produced within the expected window."""


class VerificationCodeTimeoutError(AutomationError):
    """Raised when the verification email never arrives."""
