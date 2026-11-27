import json
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from mc_helper.entities import Action, ControlRequest
from mc_helper.features.control import ControlService, ControlStore
from mc_helper.shared.errors import ControlUnavailable, InvalidInput, ServerNotResponding
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
    with pytest.raises(ServerNotResponding):
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
    ControlStore(control_dir).prune()
    assert not old.exists()
    assert (results / f"{ids[1]}.json").exists()


@pytest.mark.parametrize("action", list(Action))
def test_every_action_refused_while_status_is_stale(control_dir: Path, action: Action) -> None:
    now = datetime.now(UTC)
    (control_dir / "status.json").write_text(
        json.dumps(status_doc(updated=iso(now - timedelta(minutes=5))))
    )
    arg = {
        Action.SET_TIME: "day",
        Action.SET_WEATHER: "rain",
        Action.ALLOWLIST_ADD: "Sam",
        Action.ALLOWLIST_REMOVE: "Sam",
        Action.SET_SPAWN_HERE: "Alex",
    }.get(action)
    with pytest.raises(ServerNotResponding):
        service(control_dir, now).submit(action, arg)
    assert os.listdir(control_dir / "requests") == []


def test_every_action_refused_when_status_missing(control_dir: Path) -> None:
    with pytest.raises(ServerNotResponding):
        service(control_dir, datetime.now(UTC)).submit(Action.BACKUP_NOW, None)


def test_oversized_but_valid_documents_are_ignored(control_dir: Path) -> None:
    padding = "x" * 1_100_000
    (control_dir / "status.json").write_text(json.dumps(status_doc(server_version=padding)))
    assert ControlStore(control_dir).read_status() is None
    rid = new_id()
    doc = {"id": rid, "ok": True, "message": padding, "ts": iso(datetime.now(UTC))}
    (control_dir / "results" / f"{rid}.json").write_text(json.dumps(doc))
    assert ControlStore(control_dir).read_result(rid) is None


def test_failed_rename_leaves_no_temp_file(
    control_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(self: Path, target: str | os.PathLike[str]) -> Path:
        raise OSError("rename failed")

    monkeypatch.setattr(Path, "replace", boom)
    with pytest.raises(ControlUnavailable):
        ControlStore(control_dir).write_request(make_request())
    assert os.listdir(control_dir / "requests") == []


def test_status_drops_bad_entries_instead_of_rejecting_the_document(control_dir: Path) -> None:
    (control_dir / "status.json").write_text(
        json.dumps(
            status_doc(
                online=["Alex", 5, "n" * 101, None],
                allowlist=["Sam"] * 600,
                server_version="v" * 80,
            )
        )
    )
    status = ControlStore(control_dir).read_status()
    assert status is not None
    assert status.online == ["Alex"]
    assert len(status.allowlist) == 500
    assert len(status.server_version) == 50


def test_symlinks_are_not_followed(control_dir: Path, tmp_path: Path) -> None:
    secret = tmp_path / "outside.json"
    secret.write_text(json.dumps(status_doc()))
    link = control_dir / "status.json"
    try:
        link.symlink_to(secret)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not available")
    assert ControlStore(control_dir).read_status() is None
    rid = new_id()
    target = tmp_path / "res.json"
    target.write_text(
        json.dumps({"id": rid, "ok": True, "message": "m", "ts": iso(datetime.now(UTC))})
    )
    (control_dir / "results" / f"{rid}.json").symlink_to(target)
    assert ControlStore(control_dir).recent_results(5) == []


def test_a_directory_named_like_a_result_is_skipped(control_dir: Path) -> None:
    (control_dir / "results" / f"{new_id()}.json").mkdir()
    rid = new_id()
    doc = {"id": rid, "ok": True, "message": "m", "ts": iso(datetime.now(UTC))}
    (control_dir / "results" / f"{rid}.json").write_text(json.dumps(doc))
    assert [r.id for r in ControlStore(control_dir).recent_results(5)] == [rid]


def test_prune_removes_stale_request_temp_files_only(control_dir: Path) -> None:
    now = datetime.now(UTC).timestamp()
    requests = control_dir / "requests"
    old_temp = requests / f".tmp-{new_id()}"
    new_temp = requests / f".tmp-{new_id()}"
    pending = requests / f"{new_id()}.json"
    for path in (old_temp, new_temp, pending):
        path.write_text("{}")
    os.utime(old_temp, (now - 7200, now - 7200))
    os.utime(pending, (now - 7200, now - 7200))  # a queued request is never pruned
    ControlStore(control_dir).prune()
    assert not old_temp.exists()
    assert new_temp.exists()
    assert pending.exists()


def test_prune_logs_a_warning_when_unlink_fails(
    control_dir: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    rid = new_id()
    old = control_dir / "results" / f"{rid}.json"
    old.write_text("{}")
    now = datetime.now(UTC).timestamp()
    os.utime(old, (now - 3 * 86400, now - 3 * 86400))

    def denied(self: Path, missing_ok: bool = False) -> None:
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "unlink", denied)
    with caplog.at_level("WARNING"):
        ControlStore(control_dir).prune()
    assert [r.message for r in caplog.records].count("could not delete old control files") == 1


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def test_wait_uses_a_monotonic_deadline(control_dir: Path) -> None:
    fake = FakeClock()
    svc = ControlService(
        ControlStore(control_dir),
        requested_by="mc-helper",
        status_max_age_seconds=60,
        result_timeout_seconds=30,
        result_poll_seconds=1,
        monotonic=fake,
        sleep=fake.sleep,
    )
    assert svc.wait_for_result(new_id()) is None
    assert fake.now == 130.0  # exactly the timeout, however long each read took


def test_prune_is_throttled_with_an_injected_clock(control_dir: Path) -> None:
    fake = FakeClock()
    calls: list[int] = []

    class CountingStore(ControlStore):
        def prune(self) -> None:
            calls.append(1)

    svc = ControlService(
        CountingStore(control_dir),
        requested_by="mc-helper",
        status_max_age_seconds=60,
        result_timeout_seconds=1,
        result_poll_seconds=1,
        monotonic=fake,
        sleep=fake.sleep,
    )
    svc.prune_if_due()
    svc.prune_if_due()
    assert len(calls) == 1  # first call runs even at a tiny clock value
    fake.now += 3599
    svc.prune_if_due()
    assert len(calls) == 1
    fake.now += 2
    svc.prune_if_due()
    assert len(calls) == 2
    svc.activity(5)  # reading the activity list never prunes
    assert len(calls) == 2
