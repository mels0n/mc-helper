"""Domain documents and the argument rules. Public API of the entities layer."""

from mc_helper.entities.control import (
    GAMERTAG_HINT,
    TIMES,
    WEATHERS,
    Action,
    ActionResult,
    ControlRequest,
    check_arg,
    is_gamertag,
    parse_request_id,
)
from mc_helper.entities.status import ServerStatus

__all__ = [
    "GAMERTAG_HINT",
    "TIMES",
    "WEATHERS",
    "Action",
    "ActionResult",
    "ControlRequest",
    "ServerStatus",
    "check_arg",
    "is_gamertag",
    "parse_request_id",
]
