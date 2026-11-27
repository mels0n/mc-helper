"""Signed session cookie with a CSRF token. Anonymous sessions give the login form one."""

import base64
import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Session:
    csrf: str
    authed: bool
    expires: float


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class SessionCodec:
    def __init__(self, secret: str, pin: str, clock: Callable[[], float] = time.time) -> None:
        # The key depends on both secrets, so changing the PIN invalidates every session.
        self._key = hmac.new(
            secret.encode("utf-8"), b"mch-session" + b"\x00" + pin.encode("utf-8"), hashlib.sha256
        ).digest()
        self._clock = clock

    def _sign(self, body: str) -> str:
        return _b64(hmac.new(self._key, body.encode("ascii"), hashlib.sha256).digest())

    def issue(self, *, authed: bool, ttl_seconds: int) -> tuple[str, Session]:
        session = Session(
            csrf=secrets.token_urlsafe(24), authed=authed, expires=self._clock() + ttl_seconds
        )
        payload = json.dumps({"c": session.csrf, "a": session.authed, "e": session.expires})
        body = _b64(payload.encode("utf-8"))
        return f"{body}.{self._sign(body)}", session

    def read(self, token: str | None) -> Session | None:
        """The session if the token is genuine and unexpired, else None."""
        if not token or token.count(".") != 1 or len(token) > 1024:
            return None
        body, signature = token.split(".")
        try:
            if not hmac.compare_digest(self._sign(body), signature):
                return None
            data = json.loads(_unb64(body))
            session = Session(
                csrf=str(data["c"]), authed=data["a"] is True, expires=float(data["e"])
            )
        except (ValueError, KeyError, TypeError):
            return None
        if session.expires <= self._clock():
            return None
        return session
