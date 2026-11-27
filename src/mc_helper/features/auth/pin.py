"""PIN check: the PIN is hashed once at boot and attempts are compared by hash."""

import hashlib
import hmac
import os

MAX_ATTEMPT_LENGTH = 128


def _hash(value: str, salt: bytes) -> bytes:
    return hashlib.scrypt(value.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)


class PinVerifier:
    def __init__(self, pin: str) -> None:
        self._salt = os.urandom(16)
        self._digest = _hash(pin, self._salt)

    def verify(self, attempt: str) -> bool:
        if len(attempt) > MAX_ATTEMPT_LENGTH:
            return False
        return hmac.compare_digest(_hash(attempt, self._salt), self._digest)
