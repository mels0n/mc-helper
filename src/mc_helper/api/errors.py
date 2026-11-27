"""The single place domain errors become HTTP responses."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import RedirectResponse, Response

from mc_helper.api.pages import login_page, render
from mc_helper.shared.errors import (
    ControlUnavailable,
    CsrfFailed,
    DomainError,
    InvalidInput,
    Locked,
    LoginRequired,
    WrongPin,
)

log = logging.getLogger(__name__)


def _error_page(request: Request, status: int, title: str, message: str) -> Response:
    return render(request, "error.html", {"title": title, "message": message}, status=status)


async def _domain_error(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, DomainError)
    match exc:
        case LoginRequired():
            return RedirectResponse("/login", status_code=303)
        case WrongPin():
            return login_page(request, exc.message, status=401)
        case Locked():
            minutes = max(1, -(-exc.retry_after_s // 60))
            wait = f"{minutes} minute{'' if minutes == 1 else 's'}"
            response = login_page(request, f"Too many tries. Wait about {wait} and try again.", 429)
            response.headers["Retry-After"] = str(exc.retry_after_s)
            return response
        case CsrfFailed():
            return _error_page(request, 403, "Try again", exc.message)
        case InvalidInput():
            return _error_page(request, 400, "That did not work", exc.message)
        case ControlUnavailable():
            return _error_page(request, 503, "Server controls are away", exc.message)
        case _:
            log.error("unmapped domain error", exc_info=exc)
            return _error_page(request, 500, "Oops", "Something went wrong. Tell Dad.")


async def _bad_form(request: Request, exc: Exception) -> Response:
    return _error_page(request, 400, "That did not work", "That did not look right. Try again.")


async def _http_error(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, StarletteHTTPException)
    if exc.status_code == 404:
        return _error_page(request, 404, "Not found", "There is nothing at that address.")
    if exc.status_code == 405:
        return _error_page(request, 405, "Not allowed", "That does not work here.")
    return _error_page(request, exc.status_code, "Oops", "Something went wrong.")


async def _unexpected(request: Request, exc: Exception) -> Response:
    log.error("unhandled error", exc_info=exc)
    return _error_page(request, 500, "Oops", "Something went wrong. Tell Dad.")


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain_error)
    app.add_exception_handler(RequestValidationError, _bad_form)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(Exception, _unexpected)
