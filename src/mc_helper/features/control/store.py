"""Filesystem access to the shared control folder."""

import contextlib
import os
import time
from pathlib import Path

from pydantic import ValidationError

from mc_helper.entities import ActionResult, ControlRequest, ServerStatus, parse_request_id
from mc_helper.shared.errors import ControlUnavailable, InvalidInput

MAX_DOC_BYTES = 1_000_000
RESULT_MAX_AGE_SECONDS = 24 * 3600
SCAN_LIMIT = 200


def _read_small(path: Path) -> bytes | None:
    """File bytes, or None when missing, unreadable or oversized."""
    try:
        with path.open("rb") as handle:
            data = handle.read(MAX_DOC_BYTES + 1)
    except OSError:
        return None
    return None if len(data) > MAX_DOC_BYTES else data


class ControlStore:
    def __init__(self, root: Path) -> None:
        self._requests = root / "requests"
        self._results = root / "results"
        self._status = root / "status.json"

    def write_request(self, request: ControlRequest) -> None:
        """Write to a dot-prefixed temp file, then rename, so readers never see a partial file."""
        temp = self._requests / f".tmp-{request.id}"
        final = self._requests / f"{request.id}.json"
        try:
            with temp.open("x", encoding="utf-8") as handle:
                handle.write(request.model_dump_json())
                handle.flush()
                os.fsync(handle.fileno())
            temp.replace(final)
        except OSError:
            with contextlib.suppress(OSError):
                temp.unlink()
            raise ControlUnavailable(
                "I can't reach the server controls right now. Tell Dad."
            ) from None

    def read_result(self, request_id: str) -> ActionResult | None:
        name = parse_request_id(request_id)
        return self._parse_result(self._results / f"{name}.json", name)

    def recent_results(self, limit: int) -> list[ActionResult]:
        """Newest results first, skipping files that are not valid result documents."""
        try:
            with os.scandir(self._results) as entries:
                files = [
                    (entry.stat().st_mtime, entry.name)
                    for entry in entries
                    if entry.name.endswith(".json") and not entry.name.startswith(".")
                ]
        except OSError:
            return []
        files.sort(reverse=True)
        found: list[ActionResult] = []
        for _, name in files[:SCAN_LIMIT]:
            try:
                stem = parse_request_id(name.removesuffix(".json"))
            except InvalidInput:
                continue
            result = self._parse_result(self._results / name, stem)
            if result is not None:
                found.append(result)
                if len(found) == limit:
                    break
        return found

    def prune_results(self) -> None:
        """Delete result files older than a day. Failures are ignored."""
        cutoff = time.time() - RESULT_MAX_AGE_SECONDS
        try:
            with os.scandir(self._results) as entries:
                old = [
                    Path(entry.path)
                    for entry in entries
                    if entry.name.endswith(".json") and entry.stat().st_mtime < cutoff
                ]
        except OSError:
            return
        for path in old:
            with contextlib.suppress(OSError):
                path.unlink()

    def read_status(self) -> ServerStatus | None:
        data = _read_small(self._status)
        if data is None:
            return None
        try:
            return ServerStatus.model_validate_json(data)
        except ValidationError:
            return None

    @staticmethod
    def _parse_result(path: Path, expected_id: str) -> ActionResult | None:
        data = _read_small(path)
        if data is None:
            return None
        try:
            result = ActionResult.model_validate_json(data)
        except (ValidationError, InvalidInput):
            return None
        return result if result.id == expected_id else None
