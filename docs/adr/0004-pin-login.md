# 0004. One shared PIN, signed session, CSRF token and lockout

- Status: accepted. Superseded in part by ADR-0005 (the consequences sentence about TRUSTED_PROXIES and a shared network).
- Date: 2026-11-26

## Context
The page runs on a private network behind a reverse proxy. A visiting child on the same Wi-Fi must not be able to remove friends or restart the server. There is one family, so per-user accounts would be ceremony.

## Decision
- One shared PIN, read from a secret file at boot, hashed with scrypt under a random salt, and compared by hash in constant time.
- A signed cookie (HMAC-SHA256, key from a second secret file) carries a random CSRF token, an authenticated flag and an expiry. It is HttpOnly, SameSite=Lax and Secure in production. Visitors who are not logged in get an anonymous session of the same kind so the login form is CSRF-protected too. A successful login issues a new session.
- Every POST must carry the session's CSRF token in the form.
- Five wrong PINs from one client address within five minutes lock that address out until the oldest failure ages out. IPv6 addresses count by /64.
- The client address is the socket peer, unless the peer is in `TRUSTED_PROXIES`; only then is the right-most untrusted `X-Forwarded-For` entry used. The server runs with proxy-header handling off so this is the only place the header is read.
- Counters live in the process, so the service runs as a single replica.

## Alternatives rejected
- **Network location alone.** A guest on the same network would have full control.
- **Per-user accounts.** Nobody would use them and there is no user store to keep.
- **Server-side session storage.** A signed cookie needs no store and the app has no database.

## Consequences
A PIN is short, so the lockout and the network boundary carry the weight, not the PIN's strength. `TRUSTED_PROXIES` is part of deployment: if it covers a shared network, any service on that network can pick the address the lockout counts against. Rotating the session secret logs everyone out.
