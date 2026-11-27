# Why services are changed one at a time

`docker stack deploy` re-resolves every image tag in the stack and restarts every service it touches, including ones unrelated to the change. On a cluster that also runs other household services, a one-service change must not bounce the rest. So this service is created with `docker service create` and changed with `docker service update`, one service at a time.

[deploy/mc-helper.yml](../../deploy/mc-helper.yml) is written in compose format only to describe the service in one place. It is documentation, kept identical to the create command in the [deploy how-to](../how-to/deploy.md), and is never deployed as a stack.
