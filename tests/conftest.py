import json
import re
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mc_helper.app.main import create_app
from mc_helper.shared.config import Settings

PIN = "2468"
SECRET = "s" * 40


def iso(moment: datetime) -> str:
    return moment.isoformat()


def status_doc(**overrides: object) -> dict[str, object]:
    now = datetime.now(UTC)
    doc: dict[str, object] = {
        "online": ["Alex"],
        "allowlist": ["Alex", "Sam"],
        "server_version": "1.26.60",
        "last_backup": iso(now - timedelta(hours=2)),
        "last_backup_ok": True,
        "started": iso(now - timedelta(days=1)),
        "updated": iso(now),
    }
    doc.update(overrides)
    return doc


@pytest.fixture
def control_dir(tmp_path: Path) -> Path:
    root = tmp_path / "control"
    (root / "requests").mkdir(parents=True)
    (root / "results").mkdir()
    return root


@pytest.fixture
def write_status(control_dir: Path) -> Callable[..., None]:
    def write(**overrides: object) -> None:
        (control_dir / "status.json").write_text(json.dumps(status_doc(**overrides)))

    write()
    return write


@pytest.fixture
def make_settings(tmp_path: Path, control_dir: Path) -> Callable[..., Settings]:
    pin_file = tmp_path / "pin"
    pin_file.write_text(PIN + "\n")
    secret_file = tmp_path / "secret"
    secret_file.write_text(SECRET)

    def build(**overrides: object) -> Settings:
        values: dict[str, object] = {
            "control_dir": control_dir,
            "pin_file": pin_file,
            "session_secret_file": secret_file,
            "cookie_secure": False,
            "result_timeout_seconds": 0.3,
            "result_poll_seconds": 0.02,
            "server_address": "play.example.org",
            "broadcast_gamertag": "ServerFriend",
            "server_display_name": "ExampleServer",
        }
        values.update(overrides)
        return Settings(**values)  # pyright: ignore[reportArgumentType]

    return build


@pytest.fixture
def client(make_settings: Callable[..., Settings], write_status: Callable[..., None]) -> TestClient:
    return TestClient(create_app(make_settings()))


def csrf_of(html: str) -> str:
    match = re.search(r'name="csrf" value="([^"]+)"', html)
    assert match, "no csrf field on the page"
    return match.group(1)


def log_in(client: TestClient, pin: str = PIN) -> str:
    page = client.get("/login")
    response = client.post(
        "/login", data={"pin": pin, "csrf": csrf_of(page.text)}, follow_redirects=False
    )
    assert response.status_code == 303, response.text
    return csrf_of(client.get("/").text)


@pytest.fixture
def logged_in(client: TestClient) -> tuple[TestClient, str]:
    return client, log_in(client)


@pytest.fixture
def supervisor(control_dir: Path) -> Iterator[Callable[..., None]]:
    """A stand-in supervisor: answers every request it sees."""
    stop = threading.Event()

    def run(ok: bool, message: str) -> None:
        def loop() -> None:
            seen: set[str] = set()
            while not stop.is_set():
                for path in (control_dir / "requests").glob("*.json"):
                    if path.name in seen:
                        continue
                    seen.add(path.name)
                    request = json.loads(path.read_text())
                    result = {
                        "id": request["id"],
                        "ok": ok,
                        "message": message,
                        "ts": iso(datetime.now(UTC)),
                    }
                    target = control_dir / "results" / f"{request['id']}.json"
                    target.write_text(json.dumps(result))
                time.sleep(0.01)

        threading.Thread(target=loop, daemon=True).start()

    yield run
    stop.set()


def new_id() -> str:
    return str(uuid.uuid4())
