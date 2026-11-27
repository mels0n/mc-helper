"""Submit actions to the supervisor and read back what it reports."""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from mc_helper.entities import Action, ActionResult, ControlRequest, ServerStatus
from mc_helper.features.control.store import ControlStore
from mc_helper.shared.errors import InvalidInput

log = logging.getLogger(__name__)

PRUNE_EVERY_SECONDS = 3600


@dataclass(frozen=True)
class ServerState:
    """The latest status document and whether it is recent enough to believe."""

    status: ServerStatus | None
    responding: bool


class ControlService:
    def __init__(
        self,
        store: ControlStore,
        *,
        requested_by: str,
        status_max_age_seconds: int,
        result_timeout_seconds: float,
        result_poll_seconds: float,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._store = store
        self._requested_by = requested_by
        self._max_age = status_max_age_seconds
        self._timeout = result_timeout_seconds
        self._poll = result_poll_seconds
        self._clock = clock
        self._sleep = sleep
        self._last_prune = 0.0

    def server_state(self) -> ServerState:
        status = self._store.read_status()
        responding = status is not None and status.is_fresh(self._clock(), self._max_age)
        return ServerState(status=status, responding=responding)

    def submit(self, action: Action, arg: str | None) -> str:
        """Validate and queue one action; returns the request id."""
        if action is Action.SET_SPAWN_HERE:
            state = self.server_state()
            online = state.status.online if state.status and state.responding else []
            if arg not in online:
                raise InvalidInput("I can't see you in the game. Join the server and try again.")
        request = ControlRequest.create(action, arg, self._requested_by, self._clock())
        self._store.write_request(request)
        log.info("request queued", extra={"action": action.value, "arg": arg, "id": request.id})
        return request.id

    def wait_for_result(self, request_id: str) -> ActionResult | None:
        """Poll until the supervisor answers or the timeout passes (None)."""
        waited = 0.0
        while True:
            result = self._store.read_result(request_id)
            if result is not None or waited >= self._timeout:
                return result
            self._sleep(self._poll)
            waited += self._poll

    def result(self, request_id: str) -> ActionResult | None:
        return self._store.read_result(request_id)

    def activity(self, limit: int = 20) -> list[ActionResult]:
        self._maybe_prune()
        return self._store.recent_results(limit)

    def _maybe_prune(self) -> None:
        now = time.monotonic()
        if now - self._last_prune >= PRUNE_EVERY_SECONDS:
            self._last_prune = now
            self._store.prune_results()
