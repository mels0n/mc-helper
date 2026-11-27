"""Turn domain objects into the plain values the templates show."""

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from mc_helper.entities import ActionResult, is_gamertag


def is_usable_name(name: str) -> bool:
    """Whether a name from the status file can safely be sent back as a button argument."""
    return is_gamertag(name) and name == name.strip(" ")


def initial(name: str) -> str:
    """The first letter or digit of a name, for an avatar circle."""
    for char in name:
        if char.isascii() and char.isalnum():
            return char.upper()
    return "?"


def avatar_class(name: str) -> str:
    """One of eight colour classes, the same for a given name every time."""
    return f"h{sum(name.encode('utf-8')) % 8}"


def local_time(moment: datetime, tz: ZoneInfo) -> str:
    local = moment.astimezone(tz)
    return f"{local:%a} {int(f'{local:%I}')}:{local:%M} {local:%p}"


def ago(moment: datetime, now: datetime) -> str:
    seconds = max(int((now - moment).total_seconds()), 0)
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} minute{'' if minutes == 1 else 's'} ago"
    if seconds < 86400:
        hours = seconds // 3600
        return f"{hours} hour{'' if hours == 1 else 's'} ago"
    days = seconds // 86400
    return f"{days} day{'' if days == 1 else 's'} ago"


@dataclass(frozen=True)
class ActivityRow:
    ok: bool
    message: str
    when: str


def activity_rows(results: list[ActionResult], tz: ZoneInfo) -> list[ActivityRow]:
    return [ActivityRow(r.ok, r.message, local_time(r.ts, tz)) for r in results]


@dataclass(frozen=True)
class Notice:
    kind: str  # "ok", "fail" or "pending"
    title: str
    text: str


def notice_for(result: ActionResult | None) -> Notice:
    if result is None:
        return Notice(
            "pending",
            "Waiting for the server",
            "The server has not picked this up yet. It is lined up and will happen when the "
            "server is back, so please do not press the button again.",
        )
    if result.ok:
        return Notice("ok", "Done!", result.message)
    return Notice("fail", "That did not work", result.message)
