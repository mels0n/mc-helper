"""The one gamertag rule, used for names typed on the page and for configured values."""

import re

# At least one letter or digit, like the server supervisor: a name of only spaces is not a name.
GAMERTAG_RE = re.compile(r"(?= *[A-Za-z0-9])[A-Za-z0-9 ]{1,16}")


def is_gamertag(value: str) -> bool:
    return GAMERTAG_RE.fullmatch(value) is not None


def is_exact_gamertag(value: str) -> bool:
    """A valid gamertag with no leading or trailing spaces, for values that are shown as given."""
    return is_gamertag(value) and value == value.strip(" ")
