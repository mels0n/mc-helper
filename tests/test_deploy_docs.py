import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _yml_env_keys() -> list[str]:
    """The keys under `environment:` in deploy/mc-helper.yml."""
    keys: list[str] = []
    inside = False
    for line in (ROOT / "deploy" / "mc-helper.yml").read_text(encoding="utf-8").splitlines():
        if line.strip() == "environment:":
            inside = True
            continue
        if inside:
            match = re.match(r"^ {6}([A-Z_]+):", line)
            if not match:
                break
            keys.append(match.group(1))
    return keys


def test_the_service_description_lists_environment_keys() -> None:
    assert len(_yml_env_keys()) >= 7


def test_every_environment_key_in_the_yml_is_in_the_create_command_and_the_readme() -> None:
    deploy = (ROOT / "docs" / "how-to" / "deploy.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for key in _yml_env_keys():
        assert f"--env {key}=" in deploy, f"deploy.md create command is missing {key}"
        assert f"-e {key}=" in readme, f"README docker run is missing {key}"
