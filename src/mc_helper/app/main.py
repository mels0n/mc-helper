"""Application factory: wires settings, features and the HTTP layer together."""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from mc_helper import api as api_package
from mc_helper.api import RequestContextMiddleware, Services, install_error_handlers, router
from mc_helper.features.auth import AuthService, LoginLimiter, PinVerifier, SessionCodec
from mc_helper.features.control import ControlService, ControlStore
from mc_helper.shared.clientip import parse_networks
from mc_helper.shared.config import Settings, get_settings
from mc_helper.shared.logging import configure_logging


def create_app(
    settings: Settings | None = None,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    api_dir = Path(api_package.__file__).parent

    control = ControlService(
        ControlStore(settings.control_dir),
        requested_by=settings.requested_by,
        status_max_age_seconds=settings.status_max_age_seconds,
        result_timeout_seconds=settings.result_timeout_seconds,
        result_poll_seconds=settings.result_poll_seconds,
        clock=clock,
    )
    auth = AuthService(
        PinVerifier(settings.pin.get_secret_value()),
        LoginLimiter(settings.login_max_failures, settings.login_window_seconds),
        SessionCodec(settings.session_secret.get_secret_value(), settings.pin.get_secret_value()),
        settings.session_days,
    )

    app = FastAPI(title="mc-helper", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.services = Services(
        settings=settings,
        control=control,
        auth=auth,
        templates=Jinja2Templates(directory=api_dir / "templates"),
        trusted=parse_networks(settings.trusted_proxies),
        timezone=ZoneInfo(settings.display_timezone),
    )
    app.add_middleware(RequestContextMiddleware)
    install_error_handlers(app)
    app.include_router(router)
    app.mount("/static", StaticFiles(directory=api_dir / "static"), name="static")
    return app
