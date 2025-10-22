"""Wrapper around the ZyraMail API used for temporary email addresses."""

from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass
from typing import Dict, Iterable, Optional

import requests

from .exceptions import TempMailError
from .logging_utils import get_logger

LOGGER = get_logger(__name__)


@dataclass
class Mailbox:
    """Representation of a temporary mailbox."""

    id: str
    address: str


@dataclass
class Message:
    """Representation of a message returned by ZyraMail."""

    id: str
    subject: str
    sender: str
    body: str
    created_at: str


class TempMailClient:
    """Client for the ZyraMail REST API."""

    def __init__(self, base_url: str, api_key: str, default_domain: str, timeout: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_domain = default_domain
        self.timeout = timeout

    # Internal helpers -------------------------------------------------
    def _headers(self) -> Dict[str, str]:
        return {"X-API-Key": self.api_key, "Content-Type": "application/json"}

    def _request(self, method: str, endpoint: str, **kwargs) -> Dict:
        url = f"{self.base_url}{endpoint}"
        try:
            response = requests.request(method, url, headers=self._headers(), timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:  # pragma: no cover - network failures in CI
            raise TempMailError(f"Failed to call ZyraMail API: {exc}") from exc
        if response.status_code >= 400:
            raise TempMailError(f"ZyraMail API error {response.status_code}: {response.text}")
        try:
            return response.json()
        except ValueError as exc:  # pragma: no cover - unexpected format
            raise TempMailError("ZyraMail API returned non-JSON payload") from exc

    # Public API -------------------------------------------------------
    def create_mailbox(self, name: Optional[str] = None, expiry_time: int = 3_600_000, domain: Optional[str] = None) -> Mailbox:
        payload = {
            "name": name or self._generate_name(),
            "expiryTime": expiry_time,
            "domain": domain or self.default_domain,
        }
        data = self._request("POST", "/api/emails/generate", json=payload)
        return Mailbox(id=data["id"], address=data["address"])

    def list_messages(self, email_id: str, cursor: Optional[str] = None) -> Dict:
        endpoint = f"/api/emails/{email_id}"
        if cursor:
            endpoint = f"{endpoint}?cursor={cursor}"
        return self._request("GET", endpoint)

    def get_message(self, email_id: str, message_id: str) -> Message:
        endpoint = f"/api/emails/{email_id}/{message_id}"
        data = self._request("GET", endpoint)
        return Message(
            id=data["id"],
            subject=data.get("subject", ""),
            sender=data.get("from", ""),
            body=data.get("text", ""),
            created_at=data.get("createdAt", ""),
        )

    def wait_for_code(
        self,
        email_id: str,
        subject_keywords: Iterable[str],
        pattern: str,
        timeout: int = 300,
        poll_interval: float = 5.0,
    ) -> str:
        """Poll the inbox until a verification code matching *pattern* is found."""

        deadline = time.time() + timeout
        compiled = re.compile(pattern)
        cursor: Optional[str] = None
        while time.time() < deadline:
            payload = self.list_messages(email_id, cursor)
            messages = payload.get("messages", [])
            for item in messages:
                subject = item.get("subject", "")
                if not any(keyword.lower() in subject.lower() for keyword in subject_keywords):
                    continue
                message_id = item.get("id")
                if not message_id:
                    continue
                msg = self.get_message(email_id, message_id)
                match = compiled.search(msg.body)
                if match:
                    code = match.group(1)
                    LOGGER.info("Received verification code from %s: %s", msg.sender or "unknown", code)
                    return code
            cursor = payload.get("nextCursor")
            time.sleep(poll_interval)
        raise TempMailError("Timed out waiting for verification email")

    # Utilities --------------------------------------------------------
    def _generate_name(self) -> str:
        suffix = random.randint(1000, 9999)
        return f"auto{suffix}"


def extract_code_from_text(text: str, pattern: str) -> Optional[str]:
    """Helper used by tests to confirm regex extraction logic."""

    compiled = re.compile(pattern)
    match = compiled.search(text)
    return match.group(1) if match else None
