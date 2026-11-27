"""Page rendering shared by routes and the error mapping."""

from typing import Any

from fastapi import Request
from starlette.responses import Response

from mc_helper.api.deps import SESSION_COOKIE, current_session, services
from mc_helper.features.auth import ANONYMOUS_TTL_SECONDS


def render(request: Request, name: str, context: dict[str, Any], status: int = 200) -> Response:
    return services(request).templates.TemplateResponse(request, name, context, status_code=status)


def set_session_cookie(request: Request, response: Response, token: str, max_age: int) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=services(request).settings.cookie_secure,
        path="/",
    )


def login_page(request: Request, message: str | None, status: int = 200) -> Response:
    """The login form, with a CSRF token from the current session or a fresh anonymous one."""
    svc = services(request)
    session = current_session(request)
    token: str | None = None
    if session is None:
        token, session = svc.auth.anonymous_session()
    response = render(
        request, "login.html", {"csrf": session.csrf, "message": message}, status=status
    )
    if token is not None:
        set_session_cookie(request, response, token, ANONYMOUS_TTL_SECONDS)
    return response
