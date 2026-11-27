"""Shared request helpers: the service container, client address and session cookie."""

from dataclasses import dataclass
from zoneinfo import ZoneInfo

from fastapi import Request
from fastapi.templating import Jinja2Templates

from mc_helper.features.auth import AuthService, Session
from mc_helper.features.control import ControlService
from mc_helper.shared.clientip import IPNetwork, bucket_key, client_ip
from mc_helper.shared.config import Settings

SESSION_COOKIE = "mch_session"


@dataclass(frozen=True)
class Services:
    settings: Settings
    control: ControlService
    auth: AuthService
    templates: Jinja2Templates
    trusted: tuple[IPNetwork, ...]
    timezone: ZoneInfo


def services(request: Request) -> Services:
    found: Services = request.app.state.services
    return found


def login_bucket(request: Request) -> str:
    peer = request.client.host if request.client else None
    forwarded = request.headers.getlist("x-forwarded-for")
    return bucket_key(client_ip(peer, forwarded, services(request).trusted))


def current_session(request: Request) -> Session | None:
    return services(request).auth.read_session(request.cookies.get(SESSION_COOKIE))
