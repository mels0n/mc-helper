# 0007. Queued actions stay queued; no actions while the server is not answering

- Status: accepted. Refines ADR-0003.
- Date: 2026-11-27

## Context
ADR-0003 has the app wait up to 30 seconds for the supervisor's answer. Two questions were left open: what happens to a request the supervisor has not picked up by then, and what the page should offer while the server is not answering.

## Decision
- A request not picked up within 30 seconds is not withdrawn. It stays in the queue and runs when the server is back. The page says so ("Waiting for the server ... will happen when the server is back, so please do not press the button again"), because a second press would queue a second copy.
- While the status document is missing, malformed or older than 60 seconds, the page hides every action form and the service refuses every action, not only the ones that need the status. Nothing new is queued against a server that cannot answer.
- The wait uses a monotonic clock, and the longest allowed wait is 40 seconds, below the reverse proxy's 45 second read timeout.

## Alternatives rejected
- **Withdraw an unanswered request.** It would race with a supervisor that picks it up at the same moment, and the page could not say truthfully whether the action ran.
- **Keep the buttons while the server is not answering.** A child pressing a button repeatedly would pile up requests that all run at once later.

## Consequences
A restart pressed while the server is already unresponsive is refused, so the page cannot be used to restart a hung server. The supervisor's own tooling covers that case.
