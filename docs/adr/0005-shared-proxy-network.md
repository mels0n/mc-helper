# 0005. Trust the shared proxy network and accept the lockout bypass

- Status: accepted. Supersedes in part ADR-0004.
- Date: 2026-11-27

## Context
ADR-0004 attributes login attempts to a client address and trusts `X-Forwarded-For` only from the configured `TRUSTED_PROXIES`. It noted that trusting a shared network lets any service on that network choose the address the lockout counts against, and left the choice open. The reverse proxy reaches this service on `proxy_internal`, an overlay network that many other services also use. A dedicated network holding only the proxy and this service would be tighter.

## Decision
- The page is internal only. It is served by the internal reverse proxy to the home LAN and the kids Wi-Fi, and is not reachable from the internet.
- `TRUSTED_PROXIES` is the subnet of `proxy_internal`. No dedicated overlay is created.
- Any other container on `proxy_internal` can therefore forge `X-Forwarded-For` and bypass the per-address lockout. The owner accepts this, because the page is not reachable from outside and every such container is already trusted infrastructure.
- The PIN remains the login credential; the lockout is the brake on guessing it from the home networks, and it is weaker than ADR-0004 described while this decision stands.

## Alternatives rejected
- **A dedicated overlay holding only the proxy and this service.** It would remove the bypass, at the cost of one more network to create, attach the proxy to, and keep in step. The owner chose not to.
- **Trusting no proxy.** Every login would be attributed to the proxy, so five wrong tries from anyone would lock out everyone.

## Consequences
Deployment documentation says plainly that the lockout can be bypassed from inside `proxy_internal`. If the page is ever exposed beyond the home networks, or an untrusted workload joins `proxy_internal`, revisit this decision and move to a dedicated overlay.
