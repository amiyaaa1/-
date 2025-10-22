"""Configuration loader for the Kiro automation project."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import tomllib
from typing import Any, Iterable, Optional


@dataclass(slots=True)
class PathsConfig:
    """Static filesystem paths required by the automation."""

    kiro_executable: Path
    sso_cache_dir: Path
    credential_destination: Path


@dataclass(slots=True)
class BrowserPatterns:
    """URL patterns used to validate captured authentication links."""

    google_auth: str
    aws_auth: str


@dataclass(slots=True)
class BrowserConfig:
    """Settings for the Selenium-controlled Chrome instance."""

    driver_path: Optional[Path]
    binary_path: Optional[Path]
    incognito: bool = True
    headless: bool = False
    window_size: Optional[tuple[int, int]] = None
    debugger_address: Optional[str] = None
    extra_arguments: tuple[str, ...] = ()
    patterns: BrowserPatterns | None = None


@dataclass(slots=True)
class GoogleConfig:
    """Credentials used for the Google authentication path."""

    email: str
    password: str
    enabled: bool = True
    clipboard_timeout: float = 90.0


@dataclass(slots=True)
class AwsBuilderConfig:
    """Settings for the AWS Builder ID onboarding flow."""

    domain: str
    mailbox_prefix: str = "kiro"
    mailbox_expiry: int = 3_600_000
    poll_interval: float = 5.0
    poll_timeout: float = 180.0
    password_length: int = 16
    password_charset: str = (
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789"
        "!@#$%^&*()-_=+[]{}"  # noqa: WPS221 - compact literal
    )


@dataclass(slots=True)
class EmailServiceConfig:
    """API configuration for ZyraMail."""

    base_url: str
    api_key: str


@dataclass(slots=True)
class LoopConfig:
    """Controls iteration behaviour of the orchestrator."""

    strategies: tuple[str, ...]
    max_iterations: Optional[int] = None
    delay_seconds: float = 10.0
    continue_on_error: bool = True
    wait_for_credentials: float = 60.0


@dataclass(slots=True)
class LoggingConfig:
    """Logging output configuration."""

    level: str = "INFO"
    log_directory: Optional[Path] = None


@dataclass(slots=True)
class AuthConfig:
    """Authentication helper configuration."""

    clipboard_poll_interval: float = 1.0
    clipboard_timeout: float = 120.0


@dataclass(slots=True)
class AppConfig:
    """Root configuration object for the application."""

    paths: PathsConfig
    browser: BrowserConfig
    google: GoogleConfig
    aws: AwsBuilderConfig
    email_service: EmailServiceConfig
    loop: LoopConfig
    logging: LoggingConfig
    auth: AuthConfig


class ConfigManager:
    """Utility that reads and validates project configuration."""

    def __init__(self, config_path: Path | str) -> None:
        self._config_path = Path(config_path)

    def load(self) -> AppConfig:
        """Load and parse the TOML configuration file."""

        if not self._config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self._config_path}")

        with self._config_path.open("rb") as handle:
            raw = tomllib.load(handle)

        resolved = _resolve_env_in_mapping(raw)

        paths = self._parse_paths(resolved.get("paths", {}))
        browser = self._parse_browser(resolved.get("browser", {}))
        google = self._parse_google(resolved.get("google", {}))
        aws = self._parse_aws(resolved.get("aws", {}))
        email_service = self._parse_email_service(resolved.get("email_service", {}))
        loop = self._parse_loop(resolved.get("loop", {}))
        logging_config = self._parse_logging(resolved.get("logging", {}))
        auth = self._parse_auth(resolved.get("auth", {}), google)

        return AppConfig(
            paths=paths,
            browser=browser,
            google=google,
            aws=aws,
            email_service=email_service,
            loop=loop,
            logging=logging_config,
            auth=auth,
        )

    def _parse_paths(self, section: dict[str, Any]) -> PathsConfig:
        return PathsConfig(
            kiro_executable=Path(section["kiro_executable"]).expanduser(),
            sso_cache_dir=Path(section["sso_cache_dir"]).expanduser(),
            credential_destination=Path(section["credential_destination"]).expanduser(),
        )

    def _parse_browser(self, section: dict[str, Any]) -> BrowserConfig:
        window_size = None
        if size := section.get("window_size"):
            if isinstance(size, str):
                width, height = (int(part.strip()) for part in size.split(",", maxsplit=1))
            else:
                width, height = size
            window_size = (width, height)

        patterns_section = section.get("patterns") or {}
        patterns = None
        if patterns_section:
            patterns = BrowserPatterns(
                google_auth=patterns_section.get("google_auth", "accounts.google.com"),
                aws_auth=patterns_section.get("aws_auth", "amazoncognito.com"),
            )

        extra_args: Iterable[str] = section.get("extra_arguments", [])

        return BrowserConfig(
            driver_path=_optional_path(section.get("driver_path")),
            binary_path=_optional_path(section.get("binary_path")),
            incognito=section.get("incognito", True),
            headless=section.get("headless", False),
            window_size=window_size,
            debugger_address=section.get("debugger_address"),
            extra_arguments=tuple(extra_args),
            patterns=patterns,
        )

    def _parse_google(self, section: dict[str, Any]) -> GoogleConfig:
        return GoogleConfig(
            email=section["email"],
            password=section["password"],
            enabled=section.get("enabled", True),
            clipboard_timeout=float(section.get("clipboard_timeout", section.get("timeout", 90.0))),
        )

    def _parse_aws(self, section: dict[str, Any]) -> AwsBuilderConfig:
        return AwsBuilderConfig(
            domain=section["domain"],
            mailbox_prefix=section.get("mailbox_prefix", "kiro"),
            mailbox_expiry=int(section.get("mailbox_expiry", 3_600_000)),
            poll_interval=float(section.get("poll_interval", 5.0)),
            poll_timeout=float(section.get("poll_timeout", 180.0)),
            password_length=int(section.get("password_length", 16)),
            password_charset=section.get("password_charset")
            or AwsBuilderConfig.password_charset,
        )

    def _parse_email_service(self, section: dict[str, Any]) -> EmailServiceConfig:
        return EmailServiceConfig(
            base_url=section["base_url"],
            api_key=section["api_key"],
        )

    def _parse_loop(self, section: dict[str, Any]) -> LoopConfig:
        strategies = tuple(section.get("strategies", ("google", "aws")))
        max_iterations = section.get("max_iterations")
        if max_iterations is not None:
            max_iterations = int(max_iterations)

        return LoopConfig(
            strategies=strategies,
            max_iterations=max_iterations,
            delay_seconds=float(section.get("delay_seconds", 10.0)),
            continue_on_error=bool(section.get("continue_on_error", True)),
            wait_for_credentials=float(section.get("wait_for_credentials", 60.0)),
        )

    def _parse_logging(self, section: dict[str, Any]) -> LoggingConfig:
        directory = _optional_path(section.get("log_directory"))
        return LoggingConfig(
            level=section.get("level", "INFO"),
            log_directory=directory,
        )

    def _parse_auth(self, section: dict[str, Any], google: GoogleConfig) -> AuthConfig:
        return AuthConfig(
            clipboard_poll_interval=float(section.get("clipboard_poll_interval", 1.0)),
            clipboard_timeout=float(section.get("clipboard_timeout", google.clipboard_timeout)),
        )


def _optional_path(raw: Any) -> Optional[Path]:
    if not raw:
        return None
    return Path(str(raw)).expanduser()


def _resolve_env_in_mapping(data: Any) -> Any:
    """Recursively replace ``env:`` tagged strings with environment variables."""

    if isinstance(data, dict):
        return {key: _resolve_env_in_mapping(value) for key, value in data.items()}

    if isinstance(data, (list, tuple)):
        container_type = type(data)
        return container_type(_resolve_env_in_mapping(item) for item in data)

    if isinstance(data, str) and data.startswith("env:"):
        env_name = data.split(":", maxsplit=1)[1]
        try:
            return os.environ[env_name]
        except KeyError as exc:
            raise KeyError(f"Environment variable '{env_name}' not set") from exc

    return data
