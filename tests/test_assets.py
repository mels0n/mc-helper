import hashlib
import re
from collections.abc import Callable
from pathlib import Path
from typing import cast

from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

from mc_helper.api import configure_templates
from mc_helper.shared.config import Settings

API = Path(__file__).resolve().parents[1] / "src" / "mc_helper" / "api"


def _static_url(templates: Jinja2Templates) -> Callable[[str], str]:
    return cast(
        "Callable[[str], str]", cast("dict[str, object]", templates.env.globals)["static_url"]
    )


def test_pages_link_assets_with_a_content_hash(client: TestClient) -> None:
    html = client.get("/login").text
    for name in ("app.css", "app.js"):
        expected = hashlib.sha256((API / "static" / name).read_bytes()).hexdigest()[:10]
        assert f"/static/{name}?v={expected}" in html


def test_versioned_assets_are_cached_for_a_year_and_unversioned_are_revalidated(
    client: TestClient,
) -> None:
    html = client.get("/login").text
    url = re.search(r'href="(/static/app\.css\?v=[0-9a-f]+)"', html)
    assert url
    versioned = client.get(url.group(1))
    assert versioned.status_code == 200
    assert versioned.headers["cache-control"] == "public, max-age=31536000, immutable"
    plain = client.get("/static/app.css")
    assert plain.headers["cache-control"] == "no-cache"
    assert client.get("/login").headers["cache-control"] == "no-store"


def test_the_version_changes_when_a_file_changes(
    make_settings: Callable[..., Settings], tmp_path: Path
) -> None:
    static = tmp_path / "static"
    static.mkdir()
    (static / "app.css").write_text("a { color: red }")
    first = Jinja2Templates(directory=API / "templates")
    configure_templates(first, make_settings(), static)
    (static / "app.css").write_text("a { color: blue }")
    second = Jinja2Templates(directory=API / "templates")
    configure_templates(second, make_settings(), static)
    url_a = _static_url(first)("app.css")
    url_b = _static_url(second)("app.css")
    assert url_a != url_b


def test_copy_script_resets_its_label_and_reports_failures() -> None:
    script = (API / "static" / "app.js").read_text(encoding="utf-8")
    assert "clearTimeout" in script
    assert ".catch(" in script
    assert "Copy failed" in script
    # The label is captured once per button, outside the click handler.
    assert script.index("const label = button.textContent") < script.index(".writeText(")


def test_copy_and_print_buttons_are_hidden_when_printing() -> None:
    css = (API / "static" / "app.css").read_text(encoding="utf-8")
    print_block = css[css.index("@media print") :]
    assert ".copy" in print_block
    assert "[data-print]" in print_block
    assert "display: none" in print_block


def test_a_wrong_or_missing_file_version_is_not_cached_for_a_year(client: TestClient) -> None:
    wrong = client.get("/static/app.css?v=notthehash")
    assert wrong.status_code == 200
    assert wrong.headers["cache-control"] == "no-cache"
    missing = client.get("/static/nope.css?v=abc")
    assert missing.status_code == 404
    assert "immutable" not in missing.headers.get("cache-control", "")
