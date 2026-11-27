"""The server status document written by the supervisor. Untrusted input."""

from datetime import UTC, datetime
from typing import Annotated, Any, cast

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StrictBool, field_validator

MAX_NAME_LENGTH = 100
MAX_NAMES = 500
MAX_VERSION_LENGTH = 50


def _names(value: Any) -> Any:
    """Keep the usable entries: drop non-strings and over-long names, cap the list."""
    if not isinstance(value, list):
        return value
    items = cast("list[object]", value)
    kept = [i for i in items if isinstance(i, str) and len(i) <= MAX_NAME_LENGTH]
    return kept[:MAX_NAMES]


def _version(value: Any) -> Any:
    return value[:MAX_VERSION_LENGTH] if isinstance(value, str) else value


Names = Annotated[list[str], BeforeValidator(_names)]


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class ServerStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    online: Names
    allowlist: Names
    server_version: Annotated[str, BeforeValidator(_version), Field(max_length=MAX_VERSION_LENGTH)]
    last_backup: datetime | None
    last_backup_ok: StrictBool
    started: datetime
    updated: datetime

    @field_validator("last_backup", "started", "updated")
    @classmethod
    def _utc_if_naive(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _aware(value)

    def is_fresh(self, now: datetime, max_age_seconds: int) -> bool:
        """Updated recently. A timestamp far in the future counts as stale too."""
        return abs((now - self.updated).total_seconds()) <= max_age_seconds
