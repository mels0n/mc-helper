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

    def check(self, bucket: str) -> None:
        """Raise Locked while the bucket has used up its tries."""
        with self._lock:
            now = self._clock()
            recent = self._recent(bucket, now)
            if len(recent) >= self._max:
                retry = math.ceil(recent[0] + self._window - now)
                raise Locked(max(retry, 1))

    def record_failure(self, bucket: str) -> None:
        with self._lock:
            now = self._clock()
            if len(self._failures) > SWEEP_ABOVE:
                for key in list(self._failures):
                    self._recent(key, now)
            self._recent(bucket, now)
            self._failures.setdefault(bucket, []).append(now)

    def record_success(self, bucket: str) -> None:
        with self._lock:
            self._failures.pop(bucket, None)
