# 0005. Trust the shared proxy network and accept the lockout bypass

- Status: accepted. Supersedes in part ADR-0004.
- Date: 2026-11-27

## Context
ADR-0004 attributes login attempts to a client address and trusts `X-Forwarded-For` only from the configured `TRUSTED_PROXIES`. It noted that trusting a shared network lets any service on that network choose the address the lockout counts against, and left the choice open. In this project's deployment the reverse proxy reaches the service over an overlay network that other services also use. A dedicated network holding only the proxy and this service would be tighter.

## Decision
- The page is internal only. It must not be reachable from the internet, and this decision holds only while that is true.
- `TRUSTED_PROXIES` is the subnet of the shared proxy network. No dedicated overlay is created for this deployment.
- Any other container on that network can therefore forge `X-Forwarded-For` and bypass the per-address lockout. The deployment's owner accepts this, because the page is not reachable from the internet and every such container is already trusted infrastructure.
- The PIN remains the login credential. The lockout is the brake on guessing it from the allowed networks, and it is weaker than ADR-0004 described while this decision stands.

## Alternatives rejected
- **A dedicated overlay holding only the proxy and this service.** It removes the bypass, at the cost of one more network to create, attach the proxy to, and keep in step. It is the tighter option and the better choice for any deployment that cannot meet the precondition above. It was not chosen for this deployment.
- **Trusting no proxy.** Every login would be attributed to the proxy, so five wrong tries from anyone would lock out everyone.

## Consequences
The deployment documentation says plainly that the lockout can be bypassed from inside a shared proxy network. If the page is ever exposed beyond the allowed networks, or an untrusted workload joins the shared network, move to a dedicated overlay.
