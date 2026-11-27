"""The request and result documents exchanged with the server supervisor.

The argument rules here are identical to the supervisor's. They are the only place
those rules are written down in this app.
"""

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)

from mc_helper.shared.errors import InvalidInput
from mc_helper.shared.gamertag import GAMERTAG_RE as GAMERTAG_RE  # re-exported
from mc_helper.shared.gamertag import is_gamertag as is_gamertag  # re-exported

TIMES = ("day", "noon", "night", "midnight")
WEATHERS = ("clear", "rain", "thunder")
MESSAGE_MAX = 300

GAMERTAG_HINT = "Use letters, numbers and spaces only, up to 16 characters."


class Action(StrEnum):
    ALLOWLIST_ADD = "allowlist_add"
    ALLOWLIST_REMOVE = "allowlist_remove"
    BACKUP_NOW = "backup_now"
    RESTART = "restart"
    SET_TIME = "set_time"
    SET_WEATHER = "set_weather"
    SET_SPAWN_HERE = "set_spawn_here"


def parse_request_id(value: str) -> str:
    """Canonical lowercase UUID text, or InvalidInput."""
    try:
        parsed = uuid.UUID(value)
    except ValueError:
        raise InvalidInput("That request number is not valid.") from None
    if str(parsed) != value.lower():
        raise InvalidInput("That request number is not valid.")
    return str(parsed)


def check_arg(action: Action, arg: str | None) -> str | None:
    """Return the argument if it is legal for the action, else raise InvalidInput."""
    match action:
        case Action.ALLOWLIST_ADD | Action.ALLOWLIST_REMOVE | Action.SET_SPAWN_HERE:
            if arg is None or not is_gamertag(arg):
                raise InvalidInput(f"That name does not work. {GAMERTAG_HINT}")
        case Action.SET_TIME:
            if arg not in TIMES:
                raise InvalidInput("Pick day, noon, night or midnight.")
        case Action.SET_WEATHER:
            if arg not in WEATHERS:
                raise InvalidInput("Pick clear, rain or storm.")
        case Action.BACKUP_NOW | Action.RESTART:
            if arg is not None:
                raise InvalidInput("That button does not take anything extra.")
    return arg


class ControlRequest(BaseModel):
    """What the app writes to /control/requests."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    action: Action
    arg: str | None
    requested_by: str = Field(pattern=r"^[A-Za-z0-9._-]{1,64}$")
    ts: datetime

    @field_validator("id")
    @classmethod
    def _id_is_uuid(cls, value: str) -> str:
        return parse_request_id(value)

    @model_validator(mode="after")
    def _arg_fits_action(self) -> Self:
        # InvalidInput is not a ValueError, so pydantic lets it through unwrapped.
        check_arg(self.action, self.arg)
        return self

    @classmethod
    def create(cls, action: Action, arg: str | None, requested_by: str, now: datetime) -> Self:
        return cls(id=str(uuid.uuid4()), action=action, arg=arg, requested_by=requested_by, ts=now)


def _trim(value: str) -> str:
    return value[:MESSAGE_MAX]


class ActionResult(BaseModel):
    """What the supervisor writes to /control/results. Untrusted input."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    id: str
    ok: StrictBool
    message: Annotated[str, AfterValidator(_trim)]
    ts: datetime

    @field_validator("id")
    @classmethod
    def _id_is_uuid(cls, value: str) -> str:
        return parse_request_id(value)

    @field_validator("ts")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=UTC)
