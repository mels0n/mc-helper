"""Submit actions to the supervisor and read back what it reports."""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from mc_helper.entities import Action, ActionResult, ControlRequest, ServerStatus
from mc_helper.features.control.store import ControlStore
from mc_helper.shared.errors import InvalidInput, ServerNotResponding

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
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._store = store
        self._requested_by = requested_by
        self._max_age = status_max_age_seconds
        self._timeout = result_timeout_seconds
        self._poll = result_poll_seconds
        self._clock = clock
        self._monotonic = monotonic
        self._sleep = sleep
        self._last_prune = float("-inf")

    def server_state(self) -> ServerState:
        status = self._store.read_status()
        responding = status is not None and status.is_fresh(self._clock(), self._max_age)
        return ServerState(status=status, responding=responding)

    def submit(self, action: Action, arg: str | None) -> str:
        """Validate and queue one action; returns the request id.

        Nothing is accepted while the server is not answering. A request the server has not
        picked up yet is not withdrawn: it stays queued and runs later.
        """
        state = self.server_state()
        if not state.responding or state.status is None:
            raise ServerNotResponding(
                "The server is busy or not answering, so I can't do that right now. "
                "Try again in a bit."
            )
        if action is Action.SET_SPAWN_HERE and arg not in state.status.online:
            raise InvalidInput("I can't see you in the game. Join the server and try again.")
        request = ControlRequest.create(action, arg, self._requested_by, self._clock())
        self._store.write_request(request)
        log.info("request queued", extra={"action": action.value, "arg": arg, "id": request.id})
        return request.id

    def wait_for_result(self, request_id: str) -> ActionResult | None:
        """Poll until the supervisor answers or the timeout passes (None)."""
        deadline = self._monotonic() + self._timeout
        while True:
            result = self._store.read_result(request_id)
            if result is not None or self._monotonic() >= deadline:
                return result
            self._sleep(self._poll)

    def result(self, request_id: str) -> ActionResult | None:
        return self._store.read_result(request_id)

    def activity(self, limit: int = 20) -> list[ActionResult]:
        return self._store.recent_results(limit)

    def prune_if_due(self) -> None:
        """Clean old files at most once an hour."""
        now = self._monotonic()
        if now - self._last_prune >= PRUNE_EVERY_SECONDS:
            self._last_prune = now
            self._store.prune()
