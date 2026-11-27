# Deploy to Docker Swarm

Run mc-helper as one Swarm service behind the internal reverse proxy. [deploy/mc-helper.yml](../../deploy/mc-helper.yml) describes the service in one place. Create or update it with `docker service create` and `docker service update`, never with `docker stack deploy` ([why](../explanation/service-updates.md)).

The commands below are PowerShell, run from your own machine against a Swarm manager over SSH. `<manager>` is the SSH host name of a manager node.

| Placeholder | Meaning |
| --- | --- |
| `<manager>` | SSH host alias of a Swarm manager |
| `<image>` | `ghcr.io/mels0n/mc-helper:sha-<12 chars>`, the tag CI published for the commit. Never `:latest` |
| `<control-path>` | Host path of the shared control folder (NFS), the one the server supervisor also mounts |
| `<proxy-network-subnet>` | Subnet of `proxy_internal`, see step 2 |
| `<game-address>` | Host name players type to reach the game server, for example `play.example.org` |
| `<broadcast-gamertag>` | Xbox gamertag of the account that makes the server show up in consoles' Friends tab |
| `<display-name>` | Name of the server shown in page titles and the friends guide |

## 1. Check the control folder

The folder must already hold `requests/` and `results/`, created by the supervisor. The app never creates them: a missing mount must fail loudly instead of writing into the container.

The service runs as uid 1000, gid 1000 (`--user 1000:1000` in step 5). That user needs:

- write access to `requests/` (new requests, and cleanup of abandoned temp files),
- write access to `results/` (the app deletes results older than a day),
- read access to the files in `results/` and to `status.json`.

```powershell
ssh.exe <manager> ls -ln <control-path>
```

New files from the supervisor must show up on the node quickly, or every action ends in "Waiting for the server". Check how the share is mounted:

```powershell
ssh.exe <manager> "mount | grep /mnt/config"
```

If actions always end in "Waiting for the server" although the supervisor does answer, the node's NFS directory cache is the usual cause. The fix is a mount option on the nodes: `lookupcache=positive`, or a short `actimeo` (a few seconds). This repository does not set either; check the current options first.

## 2. Find the proxy network subnet

```powershell
ssh.exe <manager> "docker network inspect proxy_internal --format '{{range .IPAM.Config}}{{.Subnet}}{{end}}'"
```

Use that value as `TRUSTED_PROXIES`. The page is for the home LAN and the kids Wi-Fi only, through the internal proxy, and is not reachable from the internet. The app attributes logins to the client address in `X-Forwarded-For`, but only when the connection comes from an address in `TRUSTED_PROXIES`. That subnet is the shared `proxy_internal` network, so any other container on it can forge the header and dodge the per-address lockout. The owner accepted this because the page is not internet-reachable ([ADR 0005](../adr/0005-shared-proxy-network.md)).

## 3. Create the secrets

Two secrets. The PIN is what the family types: 4 or more characters, ASCII only (letters, digits and common symbols). The session secret signs the login cookie and must be at least 32 characters.

```powershell
$pin = Read-Host "PIN (4 or more ASCII characters)"
$pin | ssh.exe <manager> docker secret create mch_pin -
```

```powershell
$bytes = New-Object byte[] 48
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
[Convert]::ToBase64String($bytes) | ssh.exe <manager> docker secret create mch_session_secret -
```

## 4. Get the image

Every push to `main` that changes the app runs the checks and then publishes `ghcr.io/mels0n/mc-helper:sha-<first 12 characters of the commit>`. Deploy that tag. If no new commit is pending, publish the current `main` by hand with `gh workflow run publish.yml --ref main` (it works once the workflow file is on `main`); the tag is built from the head commit of `main`, and a commit that already has an image is not rebuilt. The package is private, so log the manager in to GHCR once with a token that has the `read:packages` scope (you are prompted for the token):

```powershell
ssh.exe -t <manager> docker login ghcr.io -u <github-user>
```

Use `--with-registry-auth` on every `docker service create` and `docker service update` of this service so the other nodes can pull.

Fallback when CI is unavailable: build with `docker build -t <image> .` on a machine with Docker and push it to the registry yourself.

## 5. Create the service

```powershell
ssh.exe <manager> docker service create --name mc-helper --with-registry-auth `
  --user 1000:1000 `
  --network proxy_internal `
  --secret mch_pin `
  --secret mch_session_secret `
  --env CONTROL_DIR=/control `
  --env TRUSTED_PROXIES=<proxy-network-subnet> `
  --env COOKIE_SECURE=true `
  --env DISPLAY_TIMEZONE=America/Chicago `
  --env SERVER_ADDRESS=<game-address> `
  --env BROADCAST_GAMERTAG=<broadcast-gamertag> `
  --env SERVER_DISPLAY_NAME=<display-name> `
  --mount type=bind,source=<control-path>,target=/control `
  --read-only `
  --cap-drop ALL `
  --replicas 1 `
  --update-order stop-first `
  --restart-condition on-failure `
  <image>
```

Three settings are required, and the service refuses to start without them:

- `SERVER_ADDRESS`: a host name made of valid DNS labels (letters, digits and hyphens, no label starting or ending with a hyphen, no empty label, 63 characters per label, 253 characters at most).
- `BROADCAST_GAMERTAG`: a valid gamertag (1 to 16 letters, digits and spaces, at least one letter or digit, no space at either end).
- `SERVER_DISPLAY_NAME`: 1 to 40 printable characters, no space at either end.

Optional: `SERVER_PORT` (default `19132`, the Bedrock port) and `HELPER_NAME` (default `a grown-up`), the name the pages use in "Ask ..." and "Tell ..." sentences (1 to 40 printable characters, no space at either end). Add `--env HELPER_NAME=<name>` to set it.

To add or change one of these on a running service, without recreating it:

```powershell
ssh.exe <manager> docker service update --with-registry-auth --env-add SERVER_ADDRESS=<game-address> mc-helper
```

Keep it at one replica: the login lockout counts failures in the process. No ports are published.

Wait until the task is healthy:

```powershell
ssh.exe <manager> docker service ps mc-helper
```

## 6. Add the proxy vhost

Copy [deploy/swag/mcadmin.subdomain.conf](../../deploy/swag/mcadmin.subdomain.conf) into the internal proxy's `proxy-confs` folder, test the config and reload nginx. With a wildcard DNS record pointing at the internal proxy, `mcadmin.<your-domain>` needs no new DNS entry.

Only networks that can reach the internal proxy can open the page. Confirm the firewall lets the home LAN and the kids Wi-Fi reach it.

## Update to a new image

```powershell
ssh.exe <manager> docker service update --with-registry-auth --image <image> mc-helper
```

Roll back with `docker service rollback mc-helper`.

## Rotate the PIN or the session secret

A Swarm secret cannot be replaced in place, so rotate by creating a new, versioned secret and swapping it in under the same target name. The session key is derived from both secrets ([ADR 0006](../adr/0006-session-key-includes-pin.md)), so rotating either one logs everyone out.

Find which secret is mounted now. This prints the container spec as JSON; its `Secrets` list has one entry per secret, each with a `File` object (whose `Name` is the target, `mch_pin` or `mch_session_secret`) and a `SecretName`:

```powershell
ssh.exe <manager> "docker service inspect mc-helper --format '{{json .Spec.TaskTemplate.ContainerSpec}}'"
```

The `SecretName` in the entry whose `File` name is `mch_pin` is `<current-pin-secret>`; the one in the `mch_session_secret` entry is `<current-session-secret>`. Use a new version suffix every time, for example the date:

```powershell
$pin = Read-Host "New PIN (4 or more ASCII characters)"
$pin | ssh.exe <manager> docker secret create mch_pin_<version> -
ssh.exe <manager> docker service update --with-registry-auth --secret-rm <current-pin-secret> --secret-add source=mch_pin_<version>,target=mch_pin mc-helper
```

For the session secret:

```powershell
$bytes = New-Object byte[] 48
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
[Convert]::ToBase64String($bytes) | ssh.exe <manager> docker secret create mch_session_secret_<version> -
ssh.exe <manager> docker service update --with-registry-auth --secret-rm <current-session-secret> --secret-add source=mch_session_secret_<version>,target=mch_session_secret mc-helper
```

When `docker service ps mc-helper` shows the new task running and healthy, remove the secret you just swapped out (`<current-pin-secret>` or `<current-session-secret>`; it cannot be removed while a task still uses it):

```powershell
ssh.exe <manager> docker secret rm <old-secret>
```

## Check it works

Open `https://mcadmin.<your-domain>`, log in, and press "Save a backup now". The result shows under "What happened lately". Logs are JSON lines:

```powershell
ssh.exe <manager> docker service logs mc-helper --tail 50
```
