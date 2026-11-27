# 0002. FastAPI with server-rendered templates, python profile

- Status: accepted
- Date: 2026-11-26

## Context
mc-helper is a one-page tool a child uses to manage a family Minecraft server: friend list, backups, restart, time and weather. It has no database and no accounts. It runs as a single container on a private network.

## Decision
- Python 3.13, FastAPI, Jinja2 server-rendered pages, plain CSS, and a few lines of vanilla JavaScript (confirm dialogs and a "working" banner). The pages work without the script.
- Pydantic for every inbound boundary, pydantic-settings for the one configuration module, uv for packaging.
- Code standard profile `python`: layers `app > api > features > entities > shared` under `src/mc_helper/`, enforced by import-linter, with ruff, pyright (strict) and pytest in CI.
- Two feature slices from the start (`control` and `auth`), because they share nothing. They are kept independent by an import-linter contract.

## Alternatives rejected
- **A SPA framework.** The page is a handful of forms. A build step, a second toolchain and client-side state buy nothing, and every action needs a full round trip to the server anyway.
- **Node.** No reason to leave the language the rest of the home tooling uses.
- **A database.** The server's supervisor owns all state. This app reads its files and keeps nothing of its own.

## Consequences
Each action is a form post followed by a redirect, so the browser back button and refresh behave. Anything that needs live updates would need polling added later.
