"""Boot-validated settings. The only module that reads environment variables or secret files."""

import ipaddress
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, PrivateAttr, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

PIN_MIN_LENGTH = 4
SESSION_SECRET_MIN_LENGTH = 32


def _read_secret_file(path: Path, what: str) -> str:
    """Read a one-line secret file; strips a BOM and whitespace. Errors never echo contents."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise ValueError(f"{what} file could not be read") from None
    value = text.lstrip("﻿").strip()
    if not value:
        raise ValueError(f"{what} file is empty")
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", hide_input_in_errors=True)

    control_dir: Path = Path("/control")
    pin_file: Path
    session_secret_file: Path
    # IPs or CIDRs of reverse proxies whose X-Forwarded-For is believed; comma-separated in env.
    trusted_proxies: Annotated[list[str], NoDecode] = []
    cookie_secure: bool = True
    session_days: int = Field(default=7, ge=1, le=90)
    login_max_failures: int = Field(default=5, ge=1)
    login_window_seconds: int = Field(default=300, ge=1)
    result_timeout_seconds: float = Field(default=30.0, ge=0)
    result_poll_seconds: float = Field(default=0.25, gt=0)
    status_max_age_seconds: int = Field(default=60, ge=1)
    requested_by: str = Field(default="mc-helper", pattern=r"^[A-Za-z0-9._-]{1,64}$")
    display_timezone: str = "America/Chicago"
    log_level: str = "INFO"

    # Read only from their files; deliberately not env-settable fields.
    _pin: SecretStr = PrivateAttr()
    _session_secret: SecretStr = PrivateAttr()

    @property
    def pin(self) -> SecretStr:
        return self._pin

    @property
    def session_secret(self) -> SecretStr:
        return self._session_secret

    @field_validator("trusted_proxies", mode="before")
    @classmethod
    def _split_networks(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("trusted_proxies")
    @classmethod
    def _check_networks(cls, value: list[str]) -> list[str]:
        for entry in value:
            try:
                ipaddress.ip_network(entry, strict=False)
            except ValueError:
                raise ValueError("trusted_proxies holds an invalid IP or CIDR") from None
        return value

    @field_validator("display_timezone")
    @classmethod
    def _check_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("display_timezone is not a known time zone") from None
        return value

    @field_validator("log_level")
    @classmethod
    def _check_level(cls, value: str) -> str:
        upper = value.upper()
        if upper not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
            raise ValueError("log_level must be DEBUG, INFO, WARNING or ERROR")
        return upper

    @model_validator(mode="after")
    def _resolve_secret_files(self) -> Self:
        pin = _read_secret_file(self.pin_file, "pin")
        if len(pin) < PIN_MIN_LENGTH:
            raise ValueError(f"pin must be at least {PIN_MIN_LENGTH} characters")
        secret = _read_secret_file(self.session_secret_file, "session secret")
        if len(secret) < SESSION_SECRET_MIN_LENGTH:
            raise ValueError(
                f"session secret must be at least {SESSION_SECRET_MIN_LENGTH} characters"
            )
        self._pin = SecretStr(pin)
        self._session_secret = SecretStr(secret)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]
