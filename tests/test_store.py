import json
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from mc_helper.entities import Action, ControlRequest
from mc_helper.features.control import ControlService, ControlStore
from mc_helper.shared.errors import ControlUnavailable, InvalidInput
from tests.conftest import iso, new_id, status_doc


def make_request(action: Action = Action.BACKUP_NOW, arg: str | None = None) -> ControlRequest:
    return ControlRequest.create(action, arg, "mc-helper", datetime.now(UTC))


def test_request_is_written_atomically_and_valid(control_dir: Path) -> None:
    store = ControlStore(control_dir)
    request = make_request(Action.ALLOWLIST_ADD, "Sam")
    store.write_request(request)
    names = os.listdir(control_dir / "requests")
    assert names == [f"{request.id}.json"]  # no temp file left behind
    doc = json.loads((control_dir / "requests" / names[0]).read_text())
    assert set(doc) == {"id", "action", "arg", "requested_by", "ts"}
    assert doc["action"] == "allowlist_add"
    assert doc["arg"] == "Sam"
    assert doc["requested_by"] == "mc-helper"
    datetime.fromisoformat(doc["ts"])


def test_temp_file_is_dot_prefixed_and_renamed(
    control_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []
    real_replace = Path.replace

    def spy(self: Path, target: str | os.PathLike[str]) -> Path:
        seen.append(f"{self.name}->{Path(target).name}")
        assert self.exists()
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", spy)
    request = make_request()
    ControlStore(control_dir).write_request(request)
    assert seen == [f".tmp-{request.id}->{request.id}.json"]


def test_failed_write_leaves_no_partial_file(control_dir: Path) -> None:
    (control_dir / "requests").rmdir()
    with pytest.raises(ControlUnavailable):
        ControlStore(control_dir).write_request(make_request())
    assert not (control_dir / "requests").exists()  # a missing mount is never created


def test_status_missing_and_malformed(control_dir: Path) -> None:
    store = ControlStore(control_dir)
    assert store.read_status() is None
    path = control_dir / "status.json"
    for text in ["", "not json", "[]", '{"online": "x"}', '{"online":[1],"allowlist":[]}']:
        path.write_text(text)
        assert store.read_status() is None
    path.write_text(json.dumps(status_doc(updated="yesterday")))
    assert store.read_status() is None
    path.write_text("x" * 2_000_000)
    assert store.read_status() is None


def test_status_valid_and_naive_times_are_utc(control_dir: Path) -> None:
    (control_dir / "status.json").write_text(
        json.dumps(status_doc(updated="2026-11-26T10:00:00", extra_key=1))
    )
    status = ControlStore(control_dir).read_status()
    assert status is not None
    assert status.updated.tzinfo is not None


def service(control_dir: Path, now: datetime) -> ControlService:
    return ControlService(
        ControlStore(control_dir),
        requested_by="mc-helper",
        status_max_age_seconds=60,
        result_timeout_seconds=0.1,
        result_poll_seconds=0.01,
        clock=lambda: now,
    )


def test_stale_status_means_not_responding(control_dir: Path) -> None:
    now = datetime.now(UTC)
    (control_dir / "status.json").write_text(
        json.dumps(status_doc(updated=iso(now - timedelta(seconds=61))))
    )
    state = service(control_dir, now).server_state()
    assert state.status is not None
    assert not state.responding


def test_fresh_and_far_future_status(control_dir: Path) -> None:
    now = datetime.now(UTC)
    path = control_dir / "status.json"
    path.write_text(json.dumps(status_doc(updated=iso(now - timedelta(seconds=59)))))
    assert service(control_dir, now).server_state().responding
    path.write_text(json.dumps(status_doc(updated=iso(now + timedelta(hours=1)))))
    assert not service(control_dir, now).server_state().responding


def test_spawn_requires_online_player(control_dir: Path, write_status: Callable[..., None]) -> None:
    svc = service(control_dir, datetime.now(UTC))
    with pytest.raises(InvalidInput):
        svc.submit(Action.SET_SPAWN_HERE, "Sam")  # allowed but not online
    assert os.listdir(control_dir / "requests") == []
    request_id = svc.submit(Action.SET_SPAWN_HERE, "Alex")
    assert os.listdir(control_dir / "requests") == [f"{request_id}.json"]


def test_spawn_refused_when_status_stale(control_dir: Path) -> None:
    now = datetime.now(UTC)
    (control_dir / "status.json").write_text(
        json.dumps(status_doc(updated=iso(now - timedelta(minutes=5))))
    )
    with pytest.raises(InvalidInput):
        service(control_dir, now).submit(Action.SET_SPAWN_HERE, "Alex")


def test_results_wait_activity_and_prune(control_dir: Path) -> None:
    now = datetime.now(UTC)
    svc = service(control_dir, now)
    results = control_dir / "results"
    ids = [new_id() for _ in range(25)]
    for index, rid in enumerate(ids):
        path = results / f"{rid}.json"
        path.write_text(
            json.dumps({"id": rid, "ok": index % 2 == 0, "message": "m", "ts": iso(now)})
        )
        os.utime(path, (now.timestamp() + index, now.timestamp() + index))
    (results / "junk.json").write_text("{}")
    (results / f"{new_id()}.json").write_text("not json")
    (results / ".tmp-x").write_text("x")
    mismatch = new_id()
    (results / f"{mismatch}.json").write_text(
        json.dumps({"id": new_id(), "ok": True, "message": "m", "ts": iso(now)})
    )
    os.utime(results / f"{mismatch}.json", (now.timestamp() + 99, now.timestamp() + 99))

    activity = svc.activity(20)
    assert len(activity) == 20
    assert activity[0].id == ids[-1]  # newest first
    assert svc.wait_for_result(new_id()) is None  # times out
    assert svc.wait_for_result(ids[3]) is not None

    old = results / f"{ids[0]}.json"
    os.utime(old, (now.timestamp() - 2 * 86400, now.timestamp() - 2 * 86400))
    ControlStore(control_dir).prune_results()
    assert not old.exists()
    assert (results / f"{ids[1]}.json").exists()
