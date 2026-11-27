# 0006. Derive the session key from the session secret and the PIN

- Status: accepted. Refines ADR-0004.
- Date: 2026-11-27

## Context
ADR-0004 signs the session cookie with a key from a secret file. Changing the PIN then left every existing session valid, so a PIN that had leaked or been shared kept working for anyone already signed in until the session secret was also rotated.

## Decision
The signing key is `HMAC-SHA256(session secret, "mch-session" + NUL + PIN)`. A cookie issued under one PIN does not verify under another, so changing the PIN signs everyone out. Rotating either secret has the same effect.

## Alternatives rejected
- **Keep one key and track a PIN version in the cookie.** It needs state or a changed cookie format for the same result.
- **A server-side session store.** The app has no database, and a store would be one more thing to keep.

## Consequences
The PIN is changed by replacing the PIN secret and updating the service, which restarts it and logs everyone out. The deploy how-to has the exact steps.
