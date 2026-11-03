# Settings: `streamhub.json`

`streamhub.json` is a JSON object. **Every key is optional**: a missing key, `null` or `""` means *use the default*. A bad value stops startup with a message naming the key, and an unknown key produces a warning. The sections below follow the [Settings tab](../admin-guide/settings.md) of the admin page.

A typical file:

```json
{
  "site-title": "Analytics Hub",
  "team-name": "Data Platform Team",
  "server-url": "https://apps.example.com",
  "port": 8500,
  "behind-proxy": true,
  "schedule": "02:00",
  "timezone": "America/Toronto",
  "virtual-environment": "/opt/conda/envs/apps",
  "idle-timeout": 60,
  "cdf": "cdf",
  "notifiers": [{"type": "teams", "url": "https://….logic.azure.com/…", "events": ["health", "report"]}]
}
```

The `--port` and `--ssl-port` options of `streamhub run` override the file, also across reloads. The old `master-password` key is ignored, with a warning.

## Branding and layout

| Key | Type | Default | Description |
|---|---|---|---|
| `site-title` | string | `Streamhub` | Heads the landing page and names the browser tab. The top menu shows it after the logo, unless it is "Streamhub" or "Streamhub Demo". |
| `team-name` | string | `""` | Shown under the top menu, and in the landing page's introduction |
| `logo` | URL | `""` | Image for the top menu, for example `/cdf/logo.png`. Without it, the Streamhub logo. |
| `footer` | string | `""` | Footer text; defaults to the site title |
| `template-file` | string | `main.html` | Layout of the landing, news and board pages: `main.html` (top menu), `main_side.html` (a sidebar menu on wide screens), `main_nomenu.html` (no menu, only the account menu), or your own. The old name `main_2.html` still works, with a warning. |
| `template-folder` | path | bundled | A folder of your own templates, which override the bundled ones by file name. *Restart.* |

## Server and network

| Key | Type | Default | Description |
|---|---|---|---|
| `server-url` | string | `http://localhost` | The address people use to reach the hub, for links in notifications |
| `port` | int | `8500` | HTTP port: the one port of the hub and all its apps. *Restart.* |
| `ssl_port` | int | `0` (off) | HTTPS port. Needs `ssl-cert` and `ssl-key`. *Restart.* |
| `ssl-cert`, `ssl-key` | path | – | PEM certificate and key for HTTPS. *Restart.* |
| `behind-proxy` | bool | `false` | Trust `X-Forwarded-*` and `X-Real-IP` from a reverse proxy in front of the hub. Turn it on behind nginx or a load balancer, so clients are told apart by IP. *Restart.* |
| `instance-id` | string | `""` | Name of this hub among [several instances](../deployment/multiple-instances.md): 1–32 lowercase letters, digits and `-`. *Restart.* |
| `port-range` | `[first, last]` | `[port+1, port+1000]` | Internal ports handed to apps. *Restart.* |
| `port-exception` | int list | `[8501]` | Ports never handed out |
| `max-upload-mb` | int | `1024` | Largest request body proxied to an app. Uploads are streamed, not buffered. Hub pages accept 16 MB. |
| `max-ws-message-mb` | int | `200` | WebSocket message limit, also passed to Streamlit (its file uploads use it). *Restart.* |
| `proxy-timeout` | seconds | `300` | Per proxied request or WebSocket connect; also the longest pause between two chunks of an upload |

## Apps: defaults and timeouts

| Key | Type | Default | Description |
|---|---|---|---|
| `virtual-environment` | string | `""` | Default environment of apps that name none: a conda env name or an environment folder. Empty: the hub's own Python (`python` from PATH for the [executable](../development/building.md#single-file-executable)). |
| `idle-timeout` | minutes | `0` (off) | Stop `auto_shutdown` apps that had no open session and no request for this long |
| `startup-timeout` | seconds | `120` | How long an app may take to answer (its health path or port). An app that doesn't answer in time is stopped and counts as failed. |
| `stop-timeout` | seconds | `10` | Grace period between SIGTERM and SIGKILL (Linux), and the `docker stop` timeout |
| `drain-timeout` | seconds | `10` | On stop or restart, how long to wait for proxied requests and WebSocket sessions to end |
| `health-interval` | seconds | `30` | How often running apps with a health path are checked. `0` turns the checks off. *Restart.* |
| `health-failures` | int | `3` | Failed checks in a row before an app is stopped (and restarted under its `restart` policy) |
| `bind-check` | `warn`, `refuse`, `off` | `warn` | When a process app is ready, look for its processes listening beyond `127.0.0.1`, which would bypass the hub's login. `warn` logs it; `refuse` stops the app and shows why. |
| `env-passthrough` | string list | `[]` | Names, or globs such as `AWS_*`, of hub environment variables that **every** app receives. Apps otherwise get only what programs need (`PATH`, locale, temp and home folders, proxies, CA bundles, `CONDA_*`) plus the [app variables](../deployment/writing-apps.md#environment-variables). |
| `streamlit-user-headers` | bool | `false` | Fill `st.user` (`name`, `role`) in Streamlit apps from the hub's identity headers. Needs a Streamlit with `server.trustedUserHeaders` (1.66 works); older ones refuse to start. Per app: `streamlit_user_headers`. |

## Docker and Kubernetes

| Key | Type | Default | Description |
|---|---|---|---|
| `docker-socket` | string | Docker's default | Daemon of Docker apps and of the Docker tab: a socket path (used as `unix://<path>`) or a Docker host URL (`unix://`, `npipe://`, `tcp://`), passed as `docker -H`. Docker's default is `DOCKER_HOST`, else `/var/run/docker.sock` (the named pipe on Windows). |
| `docker-network` | string | `""` | For a hub that runs in a container: Docker apps join this network instead of publishing a port, and the hub reaches them by container name. Empty: apps are published on `127.0.0.1`. |
| `kubernetes-namespace` | string | the hub pod's namespace, else `default` | Namespace of Kubernetes apps that name none |

## Schedule and files

| Key | Type | Default | Description |
|---|---|---|---|
| `schedule` | `"HH:MM"` or `"off"` | `"02:00"` | Daily memory clean. `null`, `""` or `"off"` disables it. |
| `timezone` | IANA name | server local | Time zone of `schedule`, for example `Europe/Paris`. An unknown name stops startup and is refused on save. |
| `apps`, `users`, `news` | path | `streamhub-apps.json`, `streamhub-users.json`, `streamhub-news.json` | The catalog files |
| `cdf` | path | bundled `streamhub/cdf` | Static folder served at `/cdf/`. Point it at a folder of your config, so uploads survive upgrades and new containers. *Restart.* |
| `temp` | path | `<config>/temp` | Public folder at `/temp/`, emptied by every memory clean. *Restart.* |
| `log-folder` | path | `<config>/logs` | One `<app_id>.log` per app (stdout and stderr); the previous run is kept as `.log.1`. *Restart.* |
| `sessions-db` | path | `<config>/.streamhub-sessions.sqlite3` | Sessions and revocations, shared by the instances that use this config folder. Put it on a disk with working SQLite locking (not NFS). *Restart.* |
| `usage-retention-days` | int | `90` | Days of hourly usage kept in `<log-folder>/usage.sqlite3` (`0`: all). Lifetime totals are always kept. *Restart.* |

## Sign-in and sessions

| Key | Type | Default | Description |
|---|---|---|---|
| `session-days` | int | `7` | How long a login lasts |
| `sso-session-minutes` | int | `0` (`session-days`) | Single sign-on sessions older than this must sign in again, so directory group changes apply within this time |
| `cookie-secret` | string | generated | Prefer `STREAMHUB_COOKIE_SECRET`. When neither is set, a random secret is stored in `<config>/.streamhub-secret`. *Restart.* |
| `sso-default-role` | role or `null` | `null` | Role of single sign-on users that no `group-mapping` rule matches. `null` refuses them. |
| `oidc`, `ldap`, `group-mapping` | object, object, list | off | [Single sign-on](single-sign-on.md) |

## Notifications

| Key | Type | Default | Description |
|---|---|---|---|
| `slack-hook` | URL | `""` | Slack incoming webhook that receives every event. Prefer `STREAMHUB_SLACK_HOOK`. |
| `slack-name` | string | `""` | Channel name, used in logs only |
| `notifiers` | list | `[]` | More channels: Slack, Microsoft Teams, email |
| `smtp` | object | `{}` | Mail server, for email channels and issue reports |

See [Notifications](notifications.md).
