"""Login, session and CSRF decisions."""

import hmac
import logging

from mc_helper.features.auth.lockout import LoginLimiter
from mc_helper.features.auth.pin import PinVerifier
from mc_helper.features.auth.session import Session, SessionCodec
from mc_helper.shared.errors import CsrfFailed, LoginRequired, WrongPin

log = logging.getLogger(__name__)

ANONYMOUS_TTL_SECONDS = 3600


class AuthService:
    def __init__(
        self,
        pin: PinVerifier,
        limiter: LoginLimiter,
        codec: SessionCodec,
        session_days: int,
    ) -> None:
        self._pin = pin
        self._limiter = limiter
        self._codec = codec
        self._session_ttl = session_days * 86400

    def read_session(self, token: str | None) -> Session | None:
        return self._codec.read(token)

    def anonymous_session(self) -> tuple[str, Session]:
        return self._codec.issue(authed=False, ttl_seconds=ANONYMOUS_TTL_SECONDS)

    def require_login(self, token: str | None) -> Session:
        session = self._codec.read(token)
        if session is None or not session.authed:
            raise LoginRequired("Please log in first.")
        return session

    @staticmethod
    def check_csrf(session: Session, submitted: str | None) -> None:
        """Compare as bytes so a non-ASCII value fails the check instead of raising."""
        if submitted is None or not hmac.compare_digest(
            submitted.encode("utf-8"), session.csrf.encode("utf-8")
        ):
            raise CsrfFailed("That page was too old. Go back and try again.")

    def login(self, bucket: str, pin: str) -> str:
        """Return a new signed-in cookie value, or raise Locked / WrongPin."""
        self._limiter.try_acquire(bucket)
        if not self._pin.verify(pin):
            log.warning("login failed", extra={"bucket": bucket})
            raise WrongPin("That PIN is not right.")
        self._limiter.record_success(bucket)
        log.info("login ok", extra={"bucket": bucket})
        token, _ = self._codec.issue(authed=True, ttl_seconds=self._session_ttl)
        return token
