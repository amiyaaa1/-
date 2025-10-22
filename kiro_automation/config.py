"""Configuration models and loader for the Kiro automation project."""

from __future__ import annotations

import dataclasses
import pathlib
from dataclasses import dataclass, field
from typing import List, Literal, Optional

import yaml


class ConfigError(RuntimeError):
    """Raised when the configuration file is missing required values."""


@dataclass
class GoogleAccount:
    """Credentials for a Google sign-in flow."""

    email: str
    password: str


@dataclass
class AwsPasswordRule:
    """Password policy used when creating AWS Builder ID accounts."""

    min_length: int = 12
    include_upper: bool = True
    include_lower: bool = True
    include_digit: bool = True
    include_symbol: bool = True


@dataclass
class TempMailConfig:
    """Configuration for the ZyraMail API wrapper."""

    base_url: str
    api_key: str
    default_domain: str
    mailbox_prefix: str = "test"
    expiry_time: int = 3_600_000


@dataclass
class Config:
    """Top-level configuration for the automation workflow."""

    kiro_exe_path: str
    cache_dir: str
    archive_dir: str
    login_mode: Literal["google", "aws"]
    google_accounts: List[GoogleAccount] = field(default_factory=list)
    aws_password_rule: AwsPasswordRule = field(default_factory=AwsPasswordRule)
    temp_mail: Optional[TempMailConfig] = None
    cycle_sleep: float = 8.0
    max_cycles: Optional[int] = None

    def ensure_valid(self) -> None:
        """Validate required invariants."""

        if self.login_mode == "google" and not self.google_accounts:
            raise ConfigError("At least one Google account must be provided for google login mode.")
        if self.login_mode == "aws" and self.temp_mail is None:
            raise ConfigError("temp_mail configuration is required for aws login mode.")


def _load_yaml(path: pathlib.Path) -> dict:
    if not path.exists():
        raise ConfigError(f"Configuration file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ConfigError("Configuration root must be a mapping")
    return data


def _parse_google_accounts(config: dict) -> List[GoogleAccount]:
    accounts_data = config.get("google_accounts", [])
    if not accounts_data:
        return []
    accounts: List[GoogleAccount] = []
    for raw in accounts_data:
        if not isinstance(raw, dict):
            raise ConfigError("Each google_accounts entry must be a mapping")
        email = raw.get("email")
        password = raw.get("password")
        if not email or not password:
            raise ConfigError("Google account entries require email and password")
        accounts.append(GoogleAccount(email=email, password=password))
    return accounts


def _parse_temp_mail(config: dict) -> Optional[TempMailConfig]:
    temp_mail_raw = config.get("temp_mail")
    if temp_mail_raw is None:
        return None
    if not isinstance(temp_mail_raw, dict):
        raise ConfigError("temp_mail must be a mapping")
    required_fields = ["base_url", "api_key", "default_domain"]
    for field_name in required_fields:
        if not temp_mail_raw.get(field_name):
            raise ConfigError(f"temp_mail.{field_name} is required")
    return TempMailConfig(
        base_url=temp_mail_raw["base_url"],
        api_key=temp_mail_raw["api_key"],
        default_domain=temp_mail_raw["default_domain"],
        mailbox_prefix=temp_mail_raw.get("mailbox_prefix", "test"),
        expiry_time=int(temp_mail_raw.get("expiry_time", 3_600_000)),
    )


def load_config(path: str | pathlib.Path) -> Config:
    """Load :class:`Config` from the given YAML file."""

    path = pathlib.Path(path)
    data = _load_yaml(path)

    config = Config(
        kiro_exe_path=data.get("kiro_exe_path", ""),
        cache_dir=data.get("cache_dir", ""),
        archive_dir=data.get("archive_dir", ""),
        login_mode=data.get("login_mode", "google"),
        google_accounts=_parse_google_accounts(data),
        aws_password_rule=AwsPasswordRule(**data.get("aws_password_rule", {})),
        temp_mail=_parse_temp_mail(data),
        cycle_sleep=float(data.get("cycle_sleep", 8.0)),
        max_cycles=data.get("max_cycles"),
    )

    if isinstance(config.max_cycles, str) and config.max_cycles.strip():
        try:
            config.max_cycles = int(config.max_cycles)
        except ValueError as exc:
            raise ConfigError("max_cycles must be an integer if provided") from exc
    elif config.max_cycles is not None:
        config.max_cycles = int(config.max_cycles)

    config.ensure_valid()
    return config


def dump_config(config: Config, path: str | pathlib.Path) -> None:
    """Persist the config to disk (useful for debugging)."""

    path = pathlib.Path(path)
    payload = dataclasses.asdict(config)
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(payload, fh, sort_keys=False, allow_unicode=True)
