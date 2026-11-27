"""Correlation id, access log and security headers."""

import logging
import time
from typing import cast

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from mc_helper.shared.logging import new_request_id, request_id_var

log = logging.getLogger("mc_helper.access")

CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
    "form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
)


def apply_headers(response: Response, request_id: str, path: str, versioned: bool = False) -> None:
    """Headers every response carries, including the ones for an unhandled error."""
    response.headers["X-Request-ID"] = request_id
    response.headers["Content-Security-Policy"] = CSP
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    if not path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store"
    elif versioned:
        # The URL carries a content hash, so a changed file is always a new URL.
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    else:
        response.headers["Cache-Control"] = "no-cache"


def _current_version(request: Request, response: Response) -> bool:
    """True only for a 200 or 304 static response whose ?v= is the file's current hash."""
    if response.status_code not in (200, 304) or not request.url.path.startswith("/static/"):
        return False
    versions = cast("dict[str, str]", getattr(request.app.state, "static_versions", {}))
    name = request.url.path.removeprefix("/static/")
    version = request.query_params.get("v")
    return version is not None and version == versions.get(name)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = new_request_id(request.headers.get("x-request-id"))
        request.state.request_id = request_id
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        apply_headers(response, request_id, request.url.path, _current_version(request, response))
        log.info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "ms": round((time.perf_counter() - started) * 1000),
                "request_id": request_id,
            },
        )
        return response
