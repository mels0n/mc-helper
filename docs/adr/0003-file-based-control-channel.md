# 0003. Talk to the server supervisor through a shared folder

- Status: accepted
- Date: 2026-11-26

## Context
The game server runs under a separate supervisor process. The web page must never hold the server's console credentials, and it must not be able to run arbitrary commands, because anything it can do a compromised page can do too.

## Decision
The app and the supervisor share one directory.

- The app writes a request document to `requests/<id>.json`: first to a dot-prefixed temporary file in the same directory, then a rename, so the supervisor never reads a partial file.
- The supervisor answers in `results/<id>.json`. The app polls for up to 30 seconds. After that the page says it is still working, and the answer appears later in the activity list.
- The supervisor publishes `status.json`. The app treats it, and every result, as untrusted: it is parsed with pydantic, size-capped, and every string is escaped when rendered. A status older than 60 seconds, missing or malformed shows "server not responding".
- Arguments follow the supervisor's own rules (gamertag, time, weather). The app enforces them before writing, in one place (`entities/control.py`), and the spawn action also requires the name to be online right now. The supervisor validates again, so the app is a convenience layer, not the only check.
- The app deletes result files older than a day.
- If the control directory is missing, the app reports it instead of creating it, so an unmounted share can never silently swallow requests.

## Alternatives rejected
- **The app talks to the game console directly.** It would hold a credential that can run any command.
- **An HTTP API on the supervisor.** One more listening port and an auth scheme to design, for a family-sized task.
- **A message queue.** A new service with nothing to justify it.

## Consequences
The shared folder is the whole interface, so its format is a contract owned by the supervisor. Result documents carry no action name, so the activity list shows the supervisor's message and a time, not the action that was requested.
