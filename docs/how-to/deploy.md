# Deploy to Docker Swarm

Run mc-helper as one Swarm service behind the internal reverse proxy. [deploy/mc-helper.yml](../../deploy/mc-helper.yml) describes the service in one place. Create or update it with `docker service create` and `docker service update`. Do not use `docker stack deploy`: it re-resolves every image tag in the stack and restarts services you did not mean to touch.

The commands below are PowerShell, run from your own machine against a Swarm manager over SSH. `<manager>` is the SSH host name of a manager node.

| Placeholder | Meaning |
| --- | --- |
| `<manager>` | SSH host alias of a Swarm manager |
| `<registry-image-tag>` | The exact image, `ghcr.io/<owner>/mc-helper:sha-<12 chars>`. Never `:latest` |
| `<control-path>` | Host path of the shared control folder (NFS), the one the server supervisor also mounts |
| `<proxy-network-subnet>` | Subnet of `proxy_internal`, see step 2 |

## 1. Check the control folder

The folder must already hold `requests/` and `results/`, created by the supervisor. The app never creates them: a missing mount must fail loudly instead of writing into the container. The container runs as uid 10001, so that user needs write access to `requests/` and read access to `results/` and `status.json`.

```powershell
ssh.exe <manager> ls -ln <control-path>
```

## 2. Find the proxy network subnet

```powershell
ssh.exe <manager> "docker network inspect proxy_internal --format '{{range .IPAM.Config}}{{.Subnet}}{{end}}'"
```

Use that value as `TRUSTED_PROXIES`. The app believes `X-Forwarded-For` only from addresses in it. Every service on `proxy_internal` can then name a client address, which is acceptable here because the PIN is the real gate and the lockout is a second layer (see [ADR 0004](../adr/0004-pin-login.md)). If you want a tighter setting, create a dedicated overlay that holds only the proxy and this service and trust that subnet instead.

## 3. Create the secrets

Two secrets. The PIN is what the family types. The session secret signs the login cookie and must be at least 32 characters.

```powershell
$pin = Read-Host "PIN (4 or more characters)"
$pin | ssh.exe <manager> docker secret create mch_pin -
```

```powershell
$bytes = New-Object byte[] 48
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
[Convert]::ToBase64String($bytes) | ssh.exe <manager> docker secret create mch_session_secret -
```

Changing the PIN later means removing the service, replacing the secret and creating the service again, because a secret in use cannot be replaced in place.

## 4. Build and publish the image

Build the image from the repository root and push it to your registry as `sha-<first 12 characters of the commit>`.

```powershell
docker build -t <registry-image-tag> .
docker push <registry-image-tag>
```

## 5. Create the service

```powershell
ssh.exe <manager> docker service create --name mc-helper `
  --network proxy_internal `
  --secret mch_pin `
  --secret mch_session_secret `
  --env CONTROL_DIR=/control `
  --env TRUSTED_PROXIES=<proxy-network-subnet> `
  --env COOKIE_SECURE=true `
  --env DISPLAY_TIMEZONE=America/Chicago `
  --mount type=bind,source=<control-path>,target=/control `
  --read-only `
  --cap-drop ALL `
  --replicas 1 `
  --update-order stop-first `
  --restart-condition on-failure `
  <registry-image-tag>
```

Add `--with-registry-auth` if the image is private. Keep it at one replica: the login lockout counts failures in the process. No ports are published.

Wait until the task is healthy:

```powershell
ssh.exe <manager> docker service ps mc-helper
```

## 6. Add the proxy vhost

Copy [deploy/swag/mcadmin.subdomain.conf](../../deploy/swag/mcadmin.subdomain.conf) into the internal proxy's `proxy-confs` folder, test the config and reload nginx. With a wildcard DNS record pointing at the internal proxy, `mcadmin.<your-domain>` needs no new DNS entry.

Only devices in a network zone that can reach the internal proxy can open the page. A device on a locked-down kids network cannot, until you add a firewall rule for it.

## Update to a new image

```powershell
ssh.exe <manager> docker service update --image <registry-image-tag> mc-helper
```

Roll back with `docker service rollback mc-helper`.

## Check it works

Open `https://mcadmin.<your-domain>`, log in, and press "Save a backup now". The result shows under "What happened lately". Logs are JSON lines:

```powershell
ssh.exe <manager> docker service logs mc-helper --tail 50
```
