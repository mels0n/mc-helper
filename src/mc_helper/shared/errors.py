"""Typed domain errors. The API layer maps these to HTTP in one place (api/errors.py)."""


class DomainError(Exception):
    """An expected failure. `message` is written for the child using the page."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidInput(DomainError):
    """A value failed the same rules the server supervisor applies."""


class LoginRequired(DomainError):
    """There is no signed-in session."""


class WrongPin(DomainError):
    """The PIN did not match."""


class Locked(DomainError):
    """Too many wrong PINs from one address."""

    def __init__(self, retry_after_s: int) -> None:
        super().__init__("Too many tries.")
        self.retry_after_s = retry_after_s


class CsrfFailed(DomainError):
    """The form did not carry the token that belongs to the session."""


class ControlUnavailable(DomainError):
    """The shared control folder could not be read or written."""
