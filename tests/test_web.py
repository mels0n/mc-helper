import json
import re
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mc_helper.app.main import create_app
from mc_helper.shared.config import Settings
from tests.conftest import PIN, csrf_of, new_id

EM_DASH = chr(0x2014)


def test_health_is_open(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_home_requires_login(client: TestClient) -> None:
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_login_page_and_headers(client: TestClient) -> None:
    response = client.get("/login")
    assert response.status_code == 200
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["x-request-id"])
    assert response.cookies.get("mch_session")
    assert "httponly" in response.headers["set-cookie"].lower()


def test_request_id_reused_when_well_formed(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "abcd-1234-efgh"})
    assert response.headers["x-request-id"] == "abcd-1234-efgh"
    response = client.get("/health", headers={"X-Request-ID": "bad id"})
    assert response.headers["x-request-id"] != "bad id"


def test_wrong_pin_then_lockout(client: TestClient) -> None:
    csrf = csrf_of(client.get("/login").text)
    for _ in range(5):
        response = client.post("/login", data={"pin": "0000", "csrf": csrf})
        assert response.status_code == 401
    locked = client.post("/login", data={"pin": PIN, "csrf": csrf})
    assert locked.status_code == 429
    assert int(locked.headers["retry-after"]) > 0
    assert client.get("/", follow_redirects=False).status_code == 303


def test_forged_forwarded_for_does_not_dodge_lockout(
    make_settings: Callable[..., Settings], write_status: Callable[..., None]
) -> None:
    # No trusted proxy is configured, so X-Forwarded-For must be ignored.
    c = TestClient(create_app(make_settings()))
    csrf = csrf_of(c.get("/login").text)
    for index in range(5):
        c.post(
            "/login",
            data={"pin": "0000", "csrf": csrf},
            headers={"X-Forwarded-For": f"9.9.9.{index}"},
        )
    response = c.post(
        "/login", data={"pin": PIN, "csrf": csrf}, headers={"X-Forwarded-For": "9.9.9.200"}
    )
    assert response.status_code == 429


def test_login_without_session_is_csrf_failure(client: TestClient) -> None:
    response = client.post("/login", data={"pin": PIN, "csrf": "x"})
    assert response.status_code == 403


def test_login_with_wrong_csrf_rejected(client: TestClient) -> None:
    client.get("/login")
    response = client.post("/login", data={"pin": PIN, "csrf": "forged"})
    assert response.status_code == 403


def test_posts_require_csrf_token(logged_in: tuple[TestClient, str], control_dir: Path) -> None:
    client, _ = logged_in
    for path, data in [
        ("/actions/restart", {}),
        ("/actions/backup_now", {"csrf": "forged"}),
        ("/actions/allowlist_remove", {"arg": "Sam", "csrf": ""}),
        ("/logout", {"csrf": "forged"}),
    ]:
        response = client.post(path, data=data, follow_redirects=False)
        assert response.status_code in (400, 403), path
    assert list((control_dir / "requests").iterdir()) == []
    assert client.get("/").status_code == 200  # still logged in


def test_post_without_login_goes_to_login(client: TestClient, control_dir: Path) -> None:
    response = client.post("/actions/restart", data={"csrf": "x"}, follow_redirects=False)
    assert response.status_code == 303
    assert list((control_dir / "requests").iterdir()) == []


def test_action_flow_done(
    logged_in: tuple[TestClient, str], supervisor: Callable[..., None], control_dir: Path
) -> None:
    client, csrf = logged_in
    supervisor(True, "Backup saved.")
    response = client.post("/actions/backup_now", data={"csrf": csrf}, follow_redirects=True)
    assert response.status_code == 200
    assert "Done!" in response.text
    assert "Backup saved." in response.text
    assert "What happened lately" in response.text
    request = json.loads(next((control_dir / "requests").glob("*.json")).read_text())
    assert request["action"] == "backup_now"
    assert request["arg"] is None


def test_action_flow_failure_message(
    logged_in: tuple[TestClient, str], supervisor: Callable[..., None]
) -> None:
    client, csrf = logged_in
    supervisor(False, "Server said no.")
    response = client.post(
        "/actions/set_weather", data={"csrf": csrf, "arg": "rain"}, follow_redirects=True
    )
    assert "That did not work" in response.text
    assert "Server said no." in response.text


def test_action_flow_still_working(logged_in: tuple[TestClient, str]) -> None:
    client, csrf = logged_in
    response = client.post("/actions/restart", data={"csrf": csrf}, follow_redirects=True)
    assert "Still working on it" in response.text
    assert "Check again" in response.text


def test_invalid_arguments_never_reach_supervisor(
    logged_in: tuple[TestClient, str], control_dir: Path
) -> None:
    client, csrf = logged_in
    bad = [
        ("allowlist_add", 'a"; op me'),
        ("allowlist_add", "Alex\nop me"),
        ("allowlist_add", "A" * 17),
        ("allowlist_add", "Ålex"),
        ("allowlist_remove", "x;y"),
        ("set_time", "dawn"),
        ("set_weather", "storm"),
        ("set_spawn_here", "NotOnline"),
        ("restart", "extra"),
    ]
    for action, arg in bad:
        response = client.post(
            f"/actions/{action}", data={"csrf": csrf, "arg": arg}, follow_redirects=False
        )
        assert response.status_code == 400, (action, arg)
    unknown = client.post("/actions/format_disk", data={"csrf": csrf}, follow_redirects=False)
    assert unknown.status_code == 400
    assert list((control_dir / "requests").iterdir()) == []


def test_allowlist_add_trims_spaces(logged_in: tuple[TestClient, str], control_dir: Path) -> None:
    client, csrf = logged_in
    client.post("/actions/allowlist_add", data={"csrf": csrf, "arg": " Cool Kid "})
    request = json.loads(next((control_dir / "requests").glob("*.json")).read_text())
    assert request["arg"] == "Cool Kid"


def test_spawn_for_online_player(logged_in: tuple[TestClient, str], control_dir: Path) -> None:
    client, csrf = logged_in
    client.post("/actions/set_spawn_here", data={"csrf": csrf, "arg": "Alex"})
    request = json.loads(next((control_dir / "requests").glob("*.json")).read_text())
    assert request["action"] == "set_spawn_here"
    assert request["arg"] == "Alex"


def test_hostile_status_is_escaped(
    logged_in: tuple[TestClient, str], write_status: Callable[..., None]
) -> None:
    client, _ = logged_in
    evil = "<script>alert(1)</script>"
    attr = '"><img src=x onerror=alert(2)>'
    write_status(online=[evil, attr], allowlist=[evil, attr], server_version="<b>1</b>")
    html = client.get("/").text
    assert "<script>alert" not in html
    assert "<img src=x" not in html
    assert "<b>1</b>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "&lt;b&gt;1&lt;/b&gt;" in html
    assert "&#34;&gt;&lt;img src=x onerror=alert(2)&gt;" in html


def test_hostile_result_message_is_escaped(
    logged_in: tuple[TestClient, str], control_dir: Path
) -> None:
    client, _ = logged_in
    rid = new_id()
    doc = {"id": rid, "ok": True, "message": "<script>x</script>", "ts": "2026-11-26T10:00:00Z"}
    (control_dir / "results" / f"{rid}.json").write_text(json.dumps(doc))
    html = client.get(f"/?r={rid}").text
    assert "<script>x</script>" not in html
    assert "&lt;script&gt;x&lt;/script&gt;" in html


def test_bad_result_id_in_query_is_ignored(logged_in: tuple[TestClient, str]) -> None:
    client, _ = logged_in
    for value in ["../../etc/passwd", "x", "%00", "7d0bb8c6"]:
        assert client.get("/", params={"r": value}).status_code == 200


def test_stale_status_shows_not_responding(
    logged_in: tuple[TestClient, str], write_status: Callable[..., None]
) -> None:
    client, _ = logged_in
    write_status(updated="2020-01-01T00:00:00Z")
    assert "not answering" in client.get("/").text


def test_malformed_status_shows_not_responding(
    logged_in: tuple[TestClient, str], control_dir: Path
) -> None:
    client, _ = logged_in
    (control_dir / "status.json").write_text("{broken")
    assert "not answering" in client.get("/").text


def test_logout_clears_session(logged_in: tuple[TestClient, str]) -> None:
    client, csrf = logged_in
    response = client.post("/logout", data={"csrf": csrf}, follow_redirects=False)
    assert response.status_code == 303
    assert client.get("/", follow_redirects=False).status_code == 303


def test_no_em_dashes_in_visible_pages(logged_in: tuple[TestClient, str]) -> None:
    client, _ = logged_in
    assert EM_DASH not in client.get("/").text
    assert EM_DASH not in client.get("/nope").text


def test_unknown_path_is_friendly_404(client: TestClient) -> None:
    response = client.get("/nope")
    assert response.status_code == 404
    assert "nothing at that address" in response.text


def test_control_dir_missing_gives_503(
    logged_in: tuple[TestClient, str], control_dir: Path
) -> None:
    client, csrf = logged_in
    (control_dir / "requests").rmdir()
    response = client.post("/actions/restart", data={"csrf": csrf}, follow_redirects=False)
    assert response.status_code == 503


def test_config_rejects_bad_secrets(make_settings: Callable[..., Settings], tmp_path: Path) -> None:
    short = tmp_path / "short"
    short.write_text("abc")
    with pytest.raises(ValueError, match="pin must be"):
        make_settings(pin_file=short)
    with pytest.raises(ValueError, match="session secret must be"):
        make_settings(session_secret_file=short)
    with pytest.raises(ValueError, match="could not be read"):
        make_settings(pin_file=tmp_path / "missing")
    with pytest.raises(ValueError, match="invalid IP"):
        make_settings(trusted_proxies="nonsense")
