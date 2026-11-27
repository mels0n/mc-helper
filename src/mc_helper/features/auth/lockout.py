"""Per-address lockout: too many wrong PINs inside a window blocks further tries."""

import math
import threading
import time
from collections.abc import Callable

from mc_helper.shared.errors import Locked

SWEEP_ABOVE = 1024


class LoginLimiter:
    """In-process counters, so the app must run as a single replica."""

    def __init__(
        self,
        max_failures: int,
        window_seconds: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max = max_failures
        self._window = window_seconds
        self._clock = clock
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, bucket: str, now: float) -> list[float]:
        recent = [t for t in self._failures.get(bucket, []) if now - t < self._window]
        if recent:
            self._failures[bucket] = recent
        else:
            self._failures.pop(bucket, None)
        return recent

    def try_acquire(self, bucket: str) -> None:
        """Raise Locked when the tries are used up; otherwise reserve one as a pending failure.

        The check and the reservation happen under one lock, before the PIN is hashed, so
        parallel requests cannot all slip through. A correct PIN calls `record_success`,
        which clears the bucket.
        """
        with self._lock:
            now = self._clock()
            if len(self._failures) > SWEEP_ABOVE:
                for key in list(self._failures):
                    self._recent(key, now)
            recent = self._recent(bucket, now)
            if len(recent) >= self._max:
                raise Locked(max(math.ceil(recent[0] + self._window - now), 1))
            self._failures.setdefault(bucket, []).append(now)

    def record_success(self, bucket: str) -> None:
        with self._lock:
            self._failures.pop(bucket, None)
