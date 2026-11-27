import json
import re
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from mc_helper.api.views import avatar_class, initial
from mc_helper.app.main import create_app
from mc_helper.entities import is_gamertag as entity_is_gamertag
from mc_helper.shared.config import Settings
from mc_helper.shared.gamertag import is_exact_gamertag
from tests.conftest import csrf_of, log_in, new_id

EM_DASH = chr(0x2014)
GUIDE_PATHS = ["/friends-guide", "/friends-guide/print"]
FIELDS = ("server_address", "broadcast_gamertag", "server_display_name")


@pytest.mark.parametrize("path", GUIDE_PATHS)
def test_guide_requires_login(client: TestClient, path: str) -> None:
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


@pytest.mark.parametrize("path", GUIDE_PATHS)
def test_guide_shows_configured_values(
    make_settings: Callable[..., Settings], write_status: Callable[..., None], path: str
) -> None:
    client = TestClient(
        create_app(
            make_settings(
                server_address="games.example.net",
                server_port=25565,
                broadcast_gamertag="BlockPals",
                server_display_name="Block Party",
            )
        )
    )
    log_in(client)
    html = client.get(path).text
    assert "<code>games.example.net</code>" in html
    assert "<code>25565</code>" in html
    assert "<code>BlockPals</code>" in html
    assert 'data-copy="games.example.net"' in html
    assert 'data-copy="BlockPals"' in html
    assert "Block Party" in html
    assert "play.example.org" not in html
    assert "ServerFriend" not in html


def test_port_defaults_to_the_bedrock_port(logged_in: tuple[TestClient, str]) -> None:
    client, _ = logged_in
    assert "<code>19132</code>" in client.get("/friends-guide").text


@pytest.mark.parametrize("missing", FIELDS)
def test_boot_fails_when_a_server_detail_is_missing(
    make_settings: Callable[..., Settings], monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    for name in FIELDS:
        monkeypatch.delenv(name.upper(), raising=False)
    good = make_settings()
    values = {
        "control_dir": good.control_dir,
        "pin_file": good.pin_file,
        "session_secret_file": good.session_secret_file,
        "server_address": "play.example.org",
        "broadcast_gamertag": "ServerFriend",
        "server_display_name": "ExampleServer",
    }
    del values[missing]
    with pytest.raises(ValidationError) as caught:
        Settings(**values)  # pyright: ignore[reportArgumentType]
    errors = caught.value.errors()
    assert [e["loc"] for e in errors] == [(missing,)]
    assert errors[0]["type"] == "missing"


def test_guide_covers_every_device_and_the_parent_checklist(
    logged_in: tuple[TestClient, str],
) -> None:
    client, _ = logged_in
    html = client.get("/friends-guide").text
    for expected in [
        "Nintendo Switch Online",
        "Xbox and PlayStation",
        "iPhone, iPad, Android, Windows PC and Chromebook",
        "Add Server",
        "join multiplayer games",
        "play with people outside of Xbox",
        "communicating with others",
        "Java Edition",
        "Troubleshooting",
    ]:
        assert expected in html


def test_print_view_is_printable_and_has_no_app_navigation(
    logged_in: tuple[TestClient, str],
) -> None:
    client, _ = logged_in
    html = client.get("/friends-guide/print").text
    assert "print-page" in html
    assert "data-print" in html
    assert "/logout" not in html
    assert 'action="/actions/' not in html
    assert html.count("copy noprint") == 2


def test_guide_page_has_the_logout_form_with_a_csrf_field(
    logged_in: tuple[TestClient, str],
) -> None:
    client, csrf = logged_in
    html = client.get("/friends-guide").text
    assert 'action="/logout"' in html
    assert csrf_of(html) == csrf
    assert 'href="/friends-guide/print"' in html


def test_home_links_to_the_guide(logged_in: tuple[TestClient, str]) -> None:
    client, _ = logged_in
    assert 'href="/friends-guide"' in client.get("/").text


def test_first_run_prompts_to_add_yourself(
    logged_in: tuple[TestClient, str], write_status: Callable[..., None]
) -> None:
    client, _ = logged_in
    write_status(allowlist=[], online=[])
    html = client.get("/").text
    assert "Add yourself first" in html
    assert html.count('id="friend"') == 1
    write_status(allowlist=["Alex"])
    html = client.get("/").text
    assert "Add yourself first" not in html
    assert html.count('id="friend"') == 1


def test_first_run_is_not_shown_right_after_an_action(
    logged_in: tuple[TestClient, str],
    write_status: Callable[..., None],
    control_dir: Path,
) -> None:
    client, _ = logged_in
    write_status(allowlist=[])
    rid = new_id()
    doc = {"id": rid, "ok": True, "message": "Added.", "ts": "2026-11-26T10:00:00Z"}
    (control_dir / "results" / f"{rid}.json").write_text(json.dumps(doc))
    html = client.get(f"/?r={rid}").text
    assert "Add yourself first" not in html
    assert "Added." in html
    assert "it can take a few seconds to show up" in html


def test_missing_status_file_gives_a_page_without_the_first_run_card(
    logged_in: tuple[TestClient, str], control_dir: Path
) -> None:
    client, _ = logged_in
    (control_dir / "status.json").unlink()
    response = client.get("/")
    assert response.status_code == 200
    assert "Add yourself first" not in response.text
    assert "busy or not answering" in response.text


def test_first_run_prompt_is_not_shown_when_the_server_is_not_answering(
    logged_in: tuple[TestClient, str], write_status: Callable[..., None]
) -> None:
    client, _ = logged_in
    write_status(allowlist=[], updated="2020-01-01T00:00:00Z")
    html = client.get("/").text
    assert "Add yourself first" not in html
    assert 'id="friend"' not in html


def test_helper_name_is_configurable(
    make_settings: Callable[..., Settings], write_status: Callable[..., None]
) -> None:
    client = TestClient(create_app(make_settings(helper_name="Mom")))
    log_in(client)
    write_status(online=["bad;name"], allowlist=["bad;name"], last_backup_ok=False)
    html = client.get("/").text
    assert "Ask Mom" in html
    assert "Tell Mom" in html
    assert "grown-up" not in html


def test_brand_and_titles_use_the_configured_name(
    make_settings: Callable[..., Settings], write_status: Callable[..., None]
) -> None:
    client = TestClient(create_app(make_settings(server_display_name="Block Party")))
    login = client.get("/login").text
    assert "<title>Log in | Block Party</title>" in login
    assert "<h1>Block Party</h1>" in login
    assert "| Block Party</title>" in client.get("/nope").text
    log_in(client)
    for path in ("/", "/friends-guide"):
        html = client.get(path).text
        assert 'class="brand" href="/">Block Party<' in html
        assert "Our Minecraft Server" not in html


def test_no_em_dashes_on_guide_and_home_states(
    logged_in: tuple[TestClient, str], write_status: Callable[..., None]
) -> None:
    client, _ = logged_in
    pages = [client.get(path).text for path in GUIDE_PATHS]
    for allowlist in ([], ["Alex", "Sam"]):
        write_status(allowlist=allowlist)
        pages.append(client.get("/").text)
    write_status(updated="2020-01-01T00:00:00Z")
    pages.append(client.get("/").text)
    assert all(EM_DASH not in page for page in pages)


def test_no_em_dashes_in_templates_and_static_files() -> None:
    api = Path(__file__).resolve().parents[1] / "src" / "mc_helper" / "api"
    files = [*api.glob("templates/*.html"), *api.glob("static/*")]
    assert len(files) >= 8
    for path in files:
        assert EM_DASH not in path.read_text(encoding="utf-8"), path


def test_no_em_dashes_on_login_and_error_pages(client: TestClient) -> None:
    pages = [client.get("/login").text, client.get("/nope").text]
    token = csrf_of(pages[0])
    pages.append(client.post("/login", data={"pin": "0000", "csrf": token}).text)
    pages.append(client.post("/login", data={"pin": "0000", "csrf": "forged"}).text)
    assert all(EM_DASH not in page for page in pages)
    assert all(re.search("<h1>", page) for page in pages)


def test_avatar_helpers_are_stable_and_safe() -> None:
    assert avatar_class("Alex") == avatar_class("Alex")
    assert avatar_class("Alex") in {f"h{i}" for i in range(8)}
    assert initial("alex") == "A"
    assert initial("  9lives") == "9"
    assert initial("<script>") == "S"
    assert initial("é") == "?"


@pytest.mark.parametrize(
    "name", ['a" onclick="x', '"><script>alert(1)</script>', "<b>x</b>", "it's"]
)
def test_hostile_names_are_escaped_in_every_attribute(
    logged_in: tuple[TestClient, str], write_status: Callable[..., None], name: str
) -> None:
    client, _ = logged_in
    write_status(online=[name], allowlist=[name])
    html = client.get("/").text
    assert "<script>alert(1)</script>" not in html
    assert '" onclick="' not in html
    assert "<b>x</b>" not in html
    # Not usable as a button argument, so it never reaches data-confirm or an option value.
    assert f'value="{name}"' not in html
    assert f'data-confirm="Remove {name}' not in html
    assert "Ask a grown-up" in html


def test_config_and_entities_share_one_gamertag_rule(
    make_settings: Callable[..., Settings],
) -> None:
    from mc_helper.entities import control
    from mc_helper.shared import gamertag

    assert control.GAMERTAG_RE is gamertag.GAMERTAG_RE
    assert control.is_gamertag is gamertag.is_gamertag
    samples = ["Alex", " Alex", "Alex ", "   ", "a" * 16, "a" * 17, "A b", "x;y", "", "Å"]
    for sample in samples:
        try:
            make_settings(broadcast_gamertag=sample)
            accepted = True
        except ValidationError:
            accepted = False
        assert accepted == is_exact_gamertag(sample), sample
        if accepted:
            assert entity_is_gamertag(sample)


@pytest.mark.parametrize(
    ("override", "field"),
    [
        ({"server_address": "bad address"}, "server_address"),
        ({"server_address": "-bad.example"}, "server_address"),
        ({"server_address": "a..b"}, "server_address"),
        ({"server_address": "a-.b"}, "server_address"),
        ({"server_address": "a.b."}, "server_address"),
        ({"server_address": "a" * 64 + ".example"}, "server_address"),
        ({"server_address": ".".join(["a" * 60] * 5)}, "server_address"),
        ({"server_port": 0}, "server_port"),
        ({"server_port": 65536}, "server_port"),
        ({"broadcast_gamertag": 'a"; op me'}, "broadcast_gamertag"),
        ({"broadcast_gamertag": "   "}, "broadcast_gamertag"),
        ({"broadcast_gamertag": " Padded"}, "broadcast_gamertag"),
        ({"broadcast_gamertag": "a" * 17}, "broadcast_gamertag"),
        ({"server_display_name": ""}, "server_display_name"),
        ({"server_display_name": "n" * 41}, "server_display_name"),
        ({"server_display_name": " padded"}, "server_display_name"),
        ({"helper_name": ""}, "helper_name"),
    ],
)
def test_guide_settings_rejections_name_the_field(
    make_settings: Callable[..., Settings], override: dict[str, object], field: str
) -> None:
    with pytest.raises(ValidationError) as caught:
        make_settings(**override)
    assert [e["loc"] for e in caught.value.errors()] == [(field,)]


@pytest.mark.parametrize(
    "override",
    [
        {"server_port": 1},
        {"server_port": 65535},
        {"server_address": "a"},
        {"server_address": ".".join(["a" * 63] * 3 + ["a" * 61])},  # 253 characters
        {"server_address": "a-b.example.com"},
        {"server_display_name": "n" * 40},
        {"server_display_name": "n"},
        {"broadcast_gamertag": "a" * 16},
        {"broadcast_gamertag": "Two Words"},
    ],
)
def test_guide_settings_boundaries_are_accepted(
    make_settings: Callable[..., Settings], override: dict[str, object]
) -> None:
    if "server_address" in override:
        assert len(str(override["server_address"])) <= 253
    assert make_settings(**override)
