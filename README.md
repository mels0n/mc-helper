# mc-helper

## What this is
A small web page that lets a child manage a family Minecraft Bedrock server without a console: see who is online, add and remove friends on the allow list, save a backup, restart the server, and set the time, weather and spawn point. It does not talk to the game server itself. It writes request files into a shared folder and reads the status and results that the server's supervisor process writes back ([ADR 0003](docs/adr/0003-file-based-control-channel.md)). Access is behind one shared PIN ([ADR 0004](docs/adr/0004-pin-login.md)).

## Run locally
Needs Python 3.13 and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --extra dev
```

Make a control folder with `requests/` and `results/` inside it, put a PIN (4 or more characters) and a session secret (32 or more characters) in two files, then start the app with these environment variables set:

- `CONTROL_DIR`: the control folder
- `PIN_FILE` and `SESSION_SECRET_FILE`: the two files
- `COOKIE_SECURE=false`: needed on plain `http://localhost`
- `SERVER_ADDRESS`, `BROADCAST_GAMERTAG` and `SERVER_DISPLAY_NAME` (required): the game server details shown on the friends guide page, for example `play.example.org`, `ServerFriend` and `ExampleServer` ([ADR 0008](docs/adr/0008-friends-guide-page.md)). Optional: `SERVER_PORT` (default 19132) and `HELPER_NAME` (default `a grown-up`)

```sh
uv run uvicorn mc_helper.app.main:create_app --factory --port 8000
```

Without a supervisor, write a `status.json` into the control folder by hand (fields in [docs/reference/control-spool.md](docs/reference/control-spool.md)) and answer requests by creating `results/<id>.json`. The control folder formats are in [docs/reference/control-spool.md](docs/reference/control-spool.md), generated from the models by `scripts/gen_reference.py`. Checks: `uv run ruff check`, `uv run pyright`, `uv run lint-imports`, `uv run pytest`.

## Deploy
The app ships as one container image and runs as a single-replica Docker Swarm service behind an internal reverse proxy, with no published ports. CI publishes `ghcr.io/mels0n/mc-helper:sha-<12>` on every push to `main` that changes the app, after the checks pass; the Publish image workflow can also be run by hand (Actions tab, Run workflow) to publish the current `main`. Deploys are manual, with `docker service create` and `docker service update` using that tag; nothing deploys automatically. The steps are in [docs/how-to/deploy.md](docs/how-to/deploy.md), and the service is described in [deploy/mc-helper.yml](deploy/mc-helper.yml).

## Where secrets live
Two Docker secrets, mounted as files: `mch_pin` (the family PIN) and `mch_session_secret` (signs the login cookie). The app reads them through `PIN_FILE` and `SESSION_SECRET_FILE`. Nothing else is secret, and no values are stored in this repository.
