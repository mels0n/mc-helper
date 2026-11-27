"""Filesystem access to the shared control folder."""

import contextlib
import errno
import logging
import os
import stat
import time
from pathlib import Path

from pydantic import ValidationError

from mc_helper.entities import ActionResult, ControlRequest, ServerStatus, parse_request_id
from mc_helper.shared.errors import ControlUnavailable, InvalidInput

log = logging.getLogger(__name__)

MAX_DOC_BYTES = 1_000_000
RESULT_MAX_AGE_SECONDS = 24 * 3600
TEMP_MAX_AGE_SECONDS = 3600
SCAN_LIMIT = 200

# Never follow a symlink and never block on a FIFO. The flags do not exist on every platform.
_OPEN_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_NONBLOCK", 0)
    | getattr(os, "O_BINARY", 0)
)


def _read_small(path: Path) -> bytes | None:
    """Bytes of a small regular file, or None when missing, unreadable, special or oversized."""
    try:
        fd = os.open(path, _OPEN_FLAGS)
    except OSError as exc:
        if exc.errno != errno.ENOENT:
            log.warning("cannot open control file", extra={"file": path.name, "errno": exc.errno})
        return None
    try:
        with os.fdopen(fd, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                return None
            data = handle.read(MAX_DOC_BYTES + 1)
    except OSError as exc:
        log.warning("cannot read control file", extra={"file": path.name, "errno": exc.errno})
        return None
    return None if len(data) > MAX_DOC_BYTES else data


def _regular_files(directory: Path, suffix: str | None) -> list[tuple[float, Path]]:
    """(mtime, path) of regular, non-symlink entries. A bad entry is skipped, never fatal."""
    found: list[tuple[float, Path]] = []
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                try:
                    if suffix is not None and not entry.name.endswith(suffix):
                        continue
                    info = entry.stat(follow_symlinks=False)
                    if stat.S_ISREG(info.st_mode):
                        found.append((info.st_mtime, Path(entry.path)))
                except OSError:
                    continue
    except OSError as exc:
        if exc.errno != errno.ENOENT:
            log.warning("cannot list control folder", extra={"dir": directory.name})
    return found


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
        files = [
            (mtime, path)
            for mtime, path in _regular_files(self._results, ".json")
            if not path.name.startswith(".")
        ]
        files.sort(reverse=True)
        found: list[ActionResult] = []
        for _, path in files[:SCAN_LIMIT]:
            try:
                stem = parse_request_id(path.name.removesuffix(".json"))
            except InvalidInput:
                continue
            result = self._parse_result(path, stem)
            if result is not None:
                found.append(result)
                if len(found) == limit:
                    break
        return found

    def prune(self) -> None:
        """Delete result files older than a day and abandoned request temp files older than an hour.

        A failure other than "already gone" is logged once per sweep.
        """
        now = time.time()
        old = [
            path
            for mtime, path in _regular_files(self._results, ".json")
            if now - mtime > RESULT_MAX_AGE_SECONDS
        ]
        old += [
            path
            for mtime, path in _regular_files(self._requests, None)
            if path.name.startswith(".tmp-") and now - mtime > TEMP_MAX_AGE_SECONDS
        ]
        failed = 0
        for path in old:
            try:
                path.unlink()
            except FileNotFoundError:
                continue
            except OSError:
                failed += 1
        if failed:
            log.warning("could not delete old control files", extra={"count": failed})

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
