"""The server status document written by the supervisor. Untrusted input."""

from datetime import UTC, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

Name = Annotated[str, Field(max_length=100)]


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class ServerStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    online: Annotated[list[Name], Field(max_length=500)]
    allowlist: Annotated[list[Name], Field(max_length=500)]
    server_version: Annotated[str, Field(max_length=50)]
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
