"""HTTP handlers. Thin: parse the request, call a feature, render."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from starlette.responses import RedirectResponse, Response

from mc_helper.api.deps import SESSION_COOKIE, Services, current_session, login_bucket, services
from mc_helper.api.pages import login_page, render, set_session_cookie
from mc_helper.api.views import (
    activity_rows,
    ago,
    avatar_class,
    initial,
    is_usable_name,
    local_time,
    notice_for,
)
from mc_helper.entities import GAMERTAG_HINT, TIMES, WEATHERS, Action, parse_request_id
from mc_helper.features.auth import Session
from mc_helper.shared.errors import CsrfFailed, InvalidInput

router = APIRouter()

WEATHER_LABELS = {"clear": "Clear", "rain": "Rain", "thunder": "Storm"}
WEATHER_BUTTONS = tuple((name, WEATHER_LABELS[name]) for name in WEATHERS)
TIME_BUTTONS = tuple((name, name.capitalize()) for name in TIMES)

Svc = Annotated[Services, Depends(services)]


def signed_in(request: Request, svc: Svc) -> Session:
    return svc.auth.require_login(request.cookies.get(SESSION_COOKIE))


Auth = Annotated[Session, Depends(signed_in)]


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/login")
def login_form(request: Request) -> Response:
    session = current_session(request)
    if session is not None and session.authed:
        return RedirectResponse("/", status_code=303)
    return login_page(request, None)


@router.post("/login")
def login(
    request: Request,
    svc: Svc,
    pin: Annotated[str, Form(max_length=200)],
    csrf: Annotated[str | None, Form(max_length=200)] = None,
) -> Response:
    session = current_session(request)
    if session is None:
        raise CsrfFailed("That page was too old. Go back and try again.")
    svc.auth.check_csrf(session, csrf)
    token = svc.auth.login(login_bucket(request), pin)
    response = RedirectResponse("/", status_code=303)
    set_session_cookie(request, response, token, svc.settings.session_days * 86400)
    return response


@router.post("/logout")
def logout(
    request: Request,
    svc: Svc,
    session: Auth,
    csrf: Annotated[str | None, Form(max_length=200)] = None,
) -> Response:
    svc.auth.check_csrf(session, csrf)
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@router.get("/")
def home(request: Request, svc: Svc, session: Auth, r: str | None = None) -> Response:
    svc.control.prune_if_due()
    now_state = svc.control.server_state()
    status = now_state.status
    activity = svc.control.activity(20)
    # Read after the activity scan: on a shared mount the scan refreshes the directory cache.
    notice = None
    check_id = None
    if r is not None:
        try:
            check_id = parse_request_id(r)
        except InvalidInput:
            check_id = None
    if check_id is not None:
        notice = notice_for(svc.control.result(check_id))
    now = datetime.now(UTC)
    context = {
        "csrf": session.csrf,
        "responding": now_state.responding,
        "status": status,
        "notice": notice,
        "check_id": check_id,
        "last_backup": (
            f"{ago(status.last_backup, now)} ({local_time(status.last_backup, svc.timezone)})"
            if status and status.last_backup
            else None
        ),
        "activity": activity_rows(activity, svc.timezone),
        "usable": is_usable_name,
        "avatar_class": avatar_class,
        "initial": initial,
        # Right after an action the list may not have caught up yet, so no first-run prompt.
        "first_run": (
            now_state.responding
            and status is not None
            and not status.allowlist
            and check_id is None
        ),
        "spawn_names": [n for n in status.online if is_usable_name(n)] if status else [],
        "time_buttons": TIME_BUTTONS,
        "weather_buttons": WEATHER_BUTTONS,
        "hint": GAMERTAG_HINT,
    }
    return render(request, "home.html", context)


@router.post("/actions/{action}")
def do_action(
    action: Action,
    svc: Svc,
    session: Auth,
    csrf: Annotated[str | None, Form(max_length=200)] = None,
    arg: Annotated[str | None, Form(max_length=200)] = None,
) -> Response:
    svc.auth.check_csrf(session, csrf)
    cleaned = arg.strip(" ") if arg is not None else None
    if cleaned == "":
        cleaned = None
    request_id = svc.control.submit(action, cleaned)
    svc.control.wait_for_result(request_id)
    return RedirectResponse(f"/?r={request_id}", status_code=303)


def _guide_context(svc: Svc, session: Session) -> dict[str, object]:
    settings = svc.settings
    return {
        "csrf": session.csrf,
        "server_name": settings.server_display_name,
        "address": settings.server_address,
        "port": settings.server_port,
        "broadcast": settings.broadcast_gamertag,
    }


@router.get("/friends-guide")
def friends_guide(request: Request, svc: Svc, session: Auth) -> Response:
    return render(request, "guide.html", _guide_context(svc, session))


@router.get("/friends-guide/print")
def friends_guide_print(request: Request, svc: Svc, session: Auth) -> Response:
    return render(request, "guide_print.html", _guide_context(svc, session))
