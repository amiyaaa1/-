"""Integration with the ZyraMail temporary email API."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Callable, Optional

import requests

from .config_manager import AwsBuilderConfig, EmailServiceConfig
from .exceptions import VerificationCodeTimeoutError


@dataclass(slots=True)
class Mailbox:
    """Represents a generated temporary mailbox."""

    email_id: str
    address: str
    expiry: Optional[int]

    @property
    def local_part(self) -> str:
        return self.address.split("@", maxsplit=1)[0]


@dataclass(slots=True)
class MessageMetadata:
    """Metadata for a message returned by the ZyraMail API."""

    message_id: str
    subject: str


class ZyraMailClient:
    """Simple ZyraMail API wrapper used for AWS Builder ID verification."""

    def __init__(
        self,
        config: EmailServiceConfig,
        aws_config: AwsBuilderConfig,
        session: Optional[requests.Session] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._config = config
        self._aws_config = aws_config
        self._session = session or requests.Session()
        self._logger = logger or logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # API helpers
    # ------------------------------------------------------------------
    def create_mailbox(self, name: str) -> Mailbox:
        payload = {
            "name": name,
            "expiryTime": self._aws_config.mailbox_expiry,
            "domain": self._aws_config.domain,
        }
        response = self._session.post(
            f"{self._config.base_url}/api/emails/generate",
            json=payload,
            headers=self._headers,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        email_id = data.get("emailId") or data.get("id")
        if not email_id:
            raise RuntimeError(f"Unexpected response when creating mailbox: {data}")
        address = data.get("address") or data.get("email")
        if not address:
            raise RuntimeError(f"Mailbox address missing in response: {data}")
        return Mailbox(email_id=email_id, address=address, expiry=data.get("expiryTime"))

    def list_messages(self, email_id: str, cursor: Optional[str] = None) -> list[MessageMetadata]:
        params = {"cursor": cursor} if cursor else None
        response = self._session.get(
            f"{self._config.base_url}/api/emails/{email_id}",
            headers=self._headers,
            params=params,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        messages: list[MessageMetadata] = []
        for raw in data.get("messages", data):
            message_id = raw.get("messageId") or raw.get("id")
            if not message_id:
                continue
            subject = raw.get("subject", "")
            messages.append(MessageMetadata(message_id=message_id, subject=subject))
        return messages

    def fetch_message(self, email_id: str, message_id: str) -> str:
        response = self._session.get(
            f"{self._config.base_url}/api/emails/{email_id}/{message_id}",
            headers=self._headers,
            timeout=15,
        )
        response.raise_for_status()
        raw = response.json()
        return raw.get("body", "") or raw.get("html", "")

    # ------------------------------------------------------------------
    # Convenience features
    # ------------------------------------------------------------------
    def wait_for_message(
        self,
        mailbox: Mailbox,
        predicate: Callable[[MessageMetadata], bool],
    ) -> MessageMetadata:
        deadline = time.time() + self._aws_config.poll_timeout
        cursor: Optional[str] = None
        seen_ids: set[str] = set()

        while time.time() < deadline:
            for message in self.list_messages(mailbox.email_id, cursor=cursor):
                if message.message_id in seen_ids:
                    continue
                seen_ids.add(message.message_id)
                if predicate(message):
                    self._logger.info("Verification email received: %s", message.subject)
                    return message
            self._logger.debug("No verification email yet for %s", mailbox.address)
            time.sleep(self._aws_config.poll_interval)

        raise VerificationCodeTimeoutError(
            f"Timed out waiting for verification email for {mailbox.address}"
        )

    def wait_for_code(self, mailbox: Mailbox, pattern: str) -> str:
        code_regex = re.compile(pattern)

        def matches_subject(message: MessageMetadata) -> bool:
            return "AWS" in message.subject or "构建者 ID" in message.subject

        message = self.wait_for_message(mailbox, matches_subject)
        body = self.fetch_message(mailbox.email_id, message.message_id)
        match = code_regex.search(body)
        if not match:
            raise VerificationCodeTimeoutError("Could not locate verification code in email body")
        code = match.group(1)
        self._logger.info("Extracted verification code %s for %s", code, mailbox.address)
        return code

    # ------------------------------------------------------------------
    @property
    def _headers(self) -> dict[str, str]:
        return {"X-API-Key": self._config.api_key}
