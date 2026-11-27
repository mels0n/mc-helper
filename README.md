# mc-helper

## What this is
A small web page that lets a child manage a family Minecraft Bedrock server without a console: see who is online, add and remove friends on the allow list, save a backup, restart the server, and set the time, weather and spawn point. It also has a guide the child can print or share to get friends playing. It does not talk to the game server itself. It writes request files into a shared folder and reads the status and results that the server's supervisor process writes back ([ADR 0003](docs/adr/0003-file-based-control-channel.md)). Access is behind one shared PIN ([ADR 0004](docs/adr/0004-pin-login.md)).

### How it fits together
Three pieces share one folder, the control spool:

- **This app** serves the web page and writes a small JSON request file for each button press.
- **A game-server supervisor** (see the companion server repository, link to be added) runs the Bedrock server, picks up those requests, carries them out, and writes back a result file and a `status.json`.
- **A reverse proxy** with TLS sits in front of the app and decides which networks can open the page.

The file formats the supervisor must read and write are in [docs/reference/control-spool.md](docs/reference/control-spool.md). Any supervisor that follows that contract works with this app.

## Run locally
Needs Python 3.13 and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --extra dev
```

Make a control folder with `requests/` and `results/` inside it, put a PIN (4 or more characters) and a session secret (32 or more characters) in two files, then start the app with these environment variables set:

- `CONTROL_DIR`: the control folder
- `PIN_FILE` and `SESSION_SECRET_FILE`: the two files
- `COOKIE_SECURE=false`: needed on plain `http://localhost`
- `SERVER_ADDRESS`, `BROADCAST_GAMERTAG` and `SERVER_DISPLAY_NAME` (required): the game server details shown on the friends guide page, for example `play.example.org`, `ExampleFriend` and `ExampleServer` ([ADR 0008](docs/adr/0008-friends-guide-page.md)). Optional: `SERVER_PORT` (default 19132), `HELPER_NAME` (default `a grown-up`) and `DISPLAY_TIMEZONE` (default `UTC`)

```sh
uv run uvicorn mc_helper.app.main:create_app --factory --port 8000
```

Without a supervisor, write a `status.json` into the control folder by hand and answer requests by creating `results/<id>.json`; the formats are in [docs/reference/control-spool.md](docs/reference/control-spool.md), generated from the models by `scripts/gen_reference.py`. Checks: `uv run ruff check`, `uv run pyright`, `uv run lint-imports`, `uv run pytest`.

## Deploy
The app ships as one container image and runs as a single-replica service (Docker Swarm or plain Docker) behind a reverse proxy, with no published ports. CI publishes `ghcr.io/<owner>/mc-helper:sha-<12>` on every push to `main` that changes the app, after the checks pass; the Publish image workflow can also be run by hand (Actions tab, Run workflow) to publish the current `main`. Deploys are manual; nothing deploys automatically. The Swarm steps are in [docs/how-to/deploy.md](docs/how-to/deploy.md), and the service is described in [deploy/mc-helper.yml](deploy/mc-helper.yml).

### Quick start
You need:

- Docker, either Swarm or a single host.
- A reverse proxy with TLS in front of the app, on a network the app shares with it.
- A folder shared between the app and your game-server supervisor.
- A supervisor that follows the [control spool contract](docs/reference/control-spool.md).

Steps, with your own values in place of the placeholders:

1. Create the control folder `<control-path>` and mount it into the supervisor. It must contain `requests/` and `results/`; the supervisor creates them. The app runs as uid 1000 and needs write access to both.
2. Write a PIN (4 or more ASCII characters) to `<pin-file>` and 32 or more random characters to `<secret-file>`.
3. Pull the image and run it:

   ```sh
   docker run -d --name mc-helper --user 1000:1000 --read-only --cap-drop ALL \
     --network <proxy-network> \
     -v <control-path>:/control \
     -v <pin-file>:/run/secrets/mch_pin:ro \
     -v <secret-file>:/run/secrets/mch_session_secret:ro \
     -e TRUSTED_PROXIES=<proxy-network-subnet> \
     -e SERVER_ADDRESS=<game-address> \
     -e BROADCAST_GAMERTAG=<broadcast-gamertag> \
     -e SERVER_DISPLAY_NAME=<display-name> \
     -e DISPLAY_TIMEZONE=<timezone> \
     ghcr.io/<owner>/mc-helper:sha-<12>
   ```

4. Add a server block to your reverse proxy, starting from [deploy/nginx/admin-page.conf.example](deploy/nginx/admin-page.conf.example), and point DNS for `<admin-host>` at it.
5. Open `https://<admin-host>`, log in with the PIN, and press "Save a backup now". The supervisor's answer shows under "What happened lately".

## Where secrets live
Two secrets, mounted as files: the PIN (`mch_pin`) and a session secret (`mch_session_secret`) that signs the login cookie. The app reads them through `PIN_FILE` and `SESSION_SECRET_FILE`. On Swarm they are Docker secrets; on plain Docker they are read-only file mounts. Nothing else is secret, and no values are stored in this repository.
