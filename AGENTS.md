# Working in mc-helper

This file is for anyone making changes to this repository. It covers how to build and check the code and where things live. It does not restate the code itself.

## Build, test, lint

Needs Python 3.13 and uv.

- Install: `uv sync --extra dev`
- Lint: `uv run ruff check` (formatting: `uv run ruff format`)
- Typecheck: `uv run pyright`
- Layer rules: `uv run lint-imports`
- Test: `uv run pytest`

## Layout

Source lives under `src/mc_helper/`, arranged as layers from top to bottom:

- `app/`: application factory and wiring
- `api/`: HTTP routes, templates, static files, middleware and the single mapping from errors to responses
- `features/`: `control` (requests, results and status in the shared folder) and `auth` (PIN, session, CSRF, lockout)
- `entities/`: the request, result and status documents and the argument rules
- `shared/`: settings, typed errors, logging, client-address helpers

Imports only point downward through this list, and the two feature slices do not import each other. Slices are imported through their `__init__.py`. Both rules are enforced by `.importlinter` (`lint-imports`) and fail CI.

## Conventions

- Every inbound payload (forms, `status.json`, result files) is parsed with a pydantic model before use. Argument rules exist once, in `entities/control.py`.
- Configuration is read once, at boot, in `shared/config.py`. Nothing else reads the environment or secret files.
- Domain errors are typed (`shared/errors.py`) and mapped to HTTP responses only in `api/errors.py`.
- Logs are JSON lines carrying a per-request correlation id.
- Visible text is written for a child: short, friendly, no jargon and no em dashes.
- Everything shown from `status.json` or a result file is untrusted and must go through the template's autoescaping.

## Decisions

Non-obvious choices are recorded in `docs/adr/`. Read the relevant ADR before proposing an approach that a past decision may already have rejected.
