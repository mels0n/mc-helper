"""Template globals: versioned static URLs and the configured names."""

import hashlib
from pathlib import Path
from typing import cast

from fastapi.templating import Jinja2Templates

from mc_helper.shared.config import Settings


def _versions(directory: Path) -> dict[str, str]:
    """A short content hash for every static file, computed once at startup."""
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()[:10]
        for path in directory.iterdir()
        if path.is_file()
    }


def configure_templates(
    templates: Jinja2Templates, settings: Settings, static_dir: Path
) -> dict[str, str]:
    """Install the template globals; returns the static file hashes."""
    versions = _versions(static_dir)

    def static_url(name: str) -> str:
        return f"/static/{name}?v={versions[name]}"

    names = cast("dict[str, object]", templates.env.globals)
    names["static_url"] = static_url
    names["server_name"] = settings.server_display_name
    names["helper_name"] = settings.helper_name
    return versions
