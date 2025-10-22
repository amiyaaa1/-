"""Custom exception hierarchy for the Kiro automation package."""

from __future__ import annotations


class AutomationError(RuntimeError):
    """Base class for automation related failures."""


class BrowserError(AutomationError):
    """Issues related to browser automation."""


class TempMailError(AutomationError):
    """Errors raised when interacting with the temporary mail API."""


class CredentialTimeoutError(AutomationError):
    """Raised when credential files are not produced within the expected time."""


class UnsupportedPlatformError(AutomationError):
    """Raised when a Windows-specific feature is invoked on another OS."""
