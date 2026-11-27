import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from mc_helper.entities import Action, ActionResult, ControlRequest, check_arg, is_gamertag
from mc_helper.shared.errors import InvalidInput

HOSTILE = [
    'a"; op me',
    "Alex\n",
    "Alex\nop me",
    "\nAlex",
    "A" * 17,
    "Ålex",
    "Alex‮",
    "Alex\x00",
    "١٢٣",  # arabic-indic digits
    "Alex;stop",
    "../etc",
    "",
    "<script>",
]


@pytest.mark.parametrize("value", HOSTILE)
def test_gamertag_rejects_injection(value: str) -> None:
    assert not is_gamertag(value)
    for action in (Action.ALLOWLIST_ADD, Action.ALLOWLIST_REMOVE, Action.SET_SPAWN_HERE):
        with pytest.raises(InvalidInput):
            check_arg(action, value)


@pytest.mark.parametrize("value", ["Alex", "A", "a" * 16, "Cool Kid 99", "  x"])
def test_gamertag_accepts_valid(value: str) -> None:
    assert is_gamertag(value)


def test_gamertag_required() -> None:
    with pytest.raises(InvalidInput):
        check_arg(Action.ALLOWLIST_ADD, None)


@pytest.mark.parametrize("value", ["day", "noon", "night", "midnight"])
def test_time_values(value: str) -> None:
    assert check_arg(Action.SET_TIME, value) == value


@pytest.mark.parametrize("value", ["Day", "dawn", "day;stop", "day\n", None])
def test_time_rejects(value: str | None) -> None:
    with pytest.raises(InvalidInput):
        check_arg(Action.SET_TIME, value)


@pytest.mark.parametrize("value", ["clear", "rain", "thunder"])
def test_weather_values(value: str) -> None:
    assert check_arg(Action.SET_WEATHER, value) == value


@pytest.mark.parametrize("value", ["storm", "Clear", "rain\n", None])
def test_weather_rejects(value: str | None) -> None:
    with pytest.raises(InvalidInput):
        check_arg(Action.SET_WEATHER, value)


@pytest.mark.parametrize("action", [Action.BACKUP_NOW, Action.RESTART])
def test_no_arg_actions(action: Action) -> None:
    assert check_arg(action, None) is None
    with pytest.raises(InvalidInput):
        check_arg(action, "x")


def test_request_model_enforces_rules_itself() -> None:
    with pytest.raises(InvalidInput):
        ControlRequest.create(Action.ALLOWLIST_ADD, 'a"; op me', "mc-helper", datetime.now(UTC))


def test_result_rejects_bad_documents() -> None:
    good = '{"id":"%s","ok":true,"message":"hi","ts":"2026-11-26T10:00:00Z"}'
    uid = "7d0bb8c6-1b1f-4a85-9d6e-0d5a0f2b9c11"
    assert ActionResult.model_validate_json(good % uid).ok
    with pytest.raises((ValidationError, InvalidInput)):
        ActionResult.model_validate_json(good % "../../x")
    with pytest.raises(ValidationError):
        ActionResult.model_validate_json(
            json.dumps({"id": uid, "ok": "yes", "message": "hi", "ts": "2026-11-26T10:00:00Z"})
        )
