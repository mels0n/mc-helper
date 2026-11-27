from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mc_helper.api.routes import WEATHER_BUTTONS
from mc_helper.app.main import create_app
from mc_helper.entities import WEATHERS
from mc_helper.features.control import ControlService
from mc_helper.shared.config import Settings
from tests.conftest import PIN, csrf_of, new_id

EM_DASH = chr(0x2014)
ALL_ACTIONS = [
    "restart",
    "backup_now",
    "set_time",
    "set_weather",
    "allowlist_add",
    "allowlist_remove",
    "set_spawn_here",
]


def test_weather_buttons_match_the_allowed_values() -> None:
    assert [value for value, _ in WEATHER_BUTTONS] == list(WEATHERS)


def test_non_ascii_csrf_is_a_403_not_a_crash(logged_in: tuple[TestClient, str]) -> None:
    client, _ = logged_in
    response = client.post("/actions/restart", data={"csrf": "éè"})
    assert response.status_code == 403


def test_forms_are_hidden_and_actions_refused_while_not_answering(
    logged_in: tuple[TestClient, str],
    write_status: Callable[..., None],
    control_dir: Path,
) -> None:
    client, csrf = logged_in
    write_status(updated="2020-01-01T00:00:00Z")
    html = client.get("/").text
    assert "busy or not answering" in html
    for action in ALL_ACTIONS:
        assert f"/actions/{action}" not in html
    assert "/logout" in html
    response = client.post("/actions/restart", data={"csrf": csrf}, follow_redirects=False)
    assert response.status_code == 503
    assert list((control_dir / "requests").iterdir()) == []


def test_forms_are_shown_when_the_server_answers(logged_in: tuple[TestClient, str]) -> None:
    client, _ = logged_in
    html = client.get("/").text
    for action in ALL_ACTIONS:
        assert f"/actions/{action}" in html


def test_names_that_cannot_be_sent_back_get_ask_dad(
    logged_in: tuple[TestClient, str], write_status: Callable[..., None]
) -> None:
    client, _ = logged_in
    write_status(online=["Alex", " lead", "bad;name"], allowlist=["Sam", " lead", "bad;name"])
    html = client.get("/").text
    assert html.count("Ask a grown-up") == 2
    assert html.count('action="/actions/allowlist_remove"') == 1
    assert 'value="Alex"' in html
    assert 'value=" lead"' not in html
    assert "bad;name</option>" not in html


def test_session_cookie_attributes(
    make_settings: Callable[..., Settings], write_status: Callable[..., None]
) -> None:
    secure = TestClient(create_app(make_settings(cookie_secure=True, session_days=3)))
    anon = secure.get("/login").headers["set-cookie"].lower()
    assert "secure" in anon
    assert "samesite=lax" in anon
    assert "path=/" in anon
    assert "max-age=3600" in anon
    assert "httponly" in anon

    plain = TestClient(create_app(make_settings(cookie_secure=False, session_days=3)))
    page = plain.get("/login")
    assert "secure" not in page.headers["set-cookie"].lower()
    response = plain.post(
        "/login", data={"pin": PIN, "csrf": csrf_of(page.text)}, follow_redirects=False
    )
    authed = response.headers["set-cookie"].lower()
    assert "max-age=259200" in authed
    assert "samesite=lax" in authed
    assert "path=/" in authed
    assert "httponly" in authed

    https = TestClient(create_app(make_settings(cookie_secure=True)), base_url="https://testserver")
    page = https.get("/login")
    response = https.post(
        "/login", data={"pin": PIN, "csrf": csrf_of(page.text)}, follow_redirects=False
    )
    assert "secure" in response.headers["set-cookie"].lower()


def test_lockout_behind_trusted_proxy_counts_the_forwarded_client(
    make_settings: Callable[..., Settings], write_status: Callable[..., None]
) -> None:
    app = create_app(make_settings(trusted_proxies="10.0.0.0/24"))
    proxy = TestClient(app, client=("10.0.0.5", 50000))

    def attempt(pin: str, client_address: str) -> int:
        headers = {"X-Forwarded-For": client_address}
        page = proxy.get("/login", headers=headers)
        return proxy.post(
            "/login",
            data={"pin": pin, "csrf": csrf_of(page.text)},
            headers=headers,
            follow_redirects=False,
        ).status_code

    for _ in range(5):
        assert attempt("0000", "192.0.2.50") == 401
    assert attempt(PIN, "192.0.2.50") == 429  # that client is locked out
    assert attempt(PIN, "192.0.2.51") == 303  # another client behind the proxy is not
    # A forged claim ahead of the real address does not help: the right-most one counts.
    for _ in range(5):
        attempt("0000", "203.0.113.1, 192.0.2.60")
    assert attempt(PIN, "203.0.113.2, 192.0.2.60") == 429


def test_unhandled_error_still_carries_headers(
    logged_in: tuple[TestClient, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(self: ControlService) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(ControlService, "server_state", broken)
    client, _ = logged_in
    quiet = TestClient(client.app, raise_server_exceptions=False)
    quiet.cookies.update(client.cookies)
    response = quiet.get("/", headers={"X-Request-ID": "trace-abcd-1234"})
    assert response.status_code == 500
    assert response.headers["x-request-id"] == "trace-abcd-1234"
    assert "frame-ancestors" in response.headers["content-security-policy"]
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "Tell a grown-up" in response.text


def test_no_em_dashes_in_any_rendered_page(
    logged_in: tuple[TestClient, str],
    write_status: Callable[..., None],
    control_dir: Path,
    supervisor: Callable[..., None],
) -> None:
    client, csrf = logged_in
    pages = [client.get("/").text]
    supervisor(False, "no")
    pages.append(client.post("/actions/backup_now", data={"csrf": csrf}).text)
    pages.append(client.post("/actions/restart", data={"csrf": "bad"}).text)
    pages.append(client.post("/actions/set_time", data={"csrf": csrf, "arg": "x"}).text)
    pages.append(client.post("/actions/nope", data={"csrf": csrf}).text)
    pages.append(client.get("/nope").text)
    pages.append(client.get("/", params={"r": new_id()}).text)
    write_status(updated="2020-01-01T00:00:00Z")
    pages.append(client.get("/").text)
    pages.append(client.post("/actions/restart", data={"csrf": csrf}).text)
    write_status()
    for leftover in (control_dir / "requests").iterdir():
        leftover.unlink()
    (control_dir / "requests").rmdir()
    pages.append(client.post("/actions/restart", data={"csrf": csrf}).text)
    anonymous = TestClient(client.app)
    pages.append(anonymous.get("/login").text)
    pages.append(anonymous.post("/login", data={"pin": "0000", "csrf": "x"}).text)
    assert all(EM_DASH not in text for text in pages)


def test_no_em_dashes_in_source_strings() -> None:
    root = Path(__file__).resolve().parents[1] / "src"
    for path in root.rglob("*"):
        if path.is_file() and path.suffix in {".py", ".html", ".js", ".css"}:
            assert EM_DASH not in path.read_text(encoding="utf-8"), path
