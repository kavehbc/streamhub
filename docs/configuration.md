# Configuration

Streamhub reads four JSON files. The `CONFIG` CLI argument is either a folder that contains `streamhub.json` or the path of the config file itself. Every relative path, in the config or in the apps file, resolves against the config folder.

`streamhub init <folder>` writes a [starter config](../streamhub/starter/) and its admin ([First config](operations.md#install)); [streamhub/demo/config/](../streamhub/demo/config/) is the demo's. The admin page edits all four files with forms ([Endpoints and access](operations.md#endpoints-and-access)); a folder without `streamhub.json` runs on the defaults until its first save creates the file. In this repository, [config/](../config/) is git-ignored: it holds your own deployment config.

## Config file: `streamhub.json`

Parsed by `load_settings()` in [config.py](../streamhub/config.py).

- **Every key is optional.** A missing key, `null` or `""` means "use the default".
- **Bad values stop startup** with a message naming the key.
- **Unknown keys** produce a warning.
- **`streamhub check <config>`** runs every check below, and those of the other files, without starting anything ([operations.md](operations.md#run)).

| Key | Type | Default | Description |
|---|---|---|---|
| `server-url` | string | `http://localhost` | Public base URL, used in notifications |
| `apps` / `users` / `news` | path | `streamhub-apps.json` / `streamhub-users.json` / `streamhub-news.json` | Catalog files |
| `cdf` | path | bundled `streamhub/cdf` | Static folder served at `/cdf/`, managed on the admin page's Static files tab. Point it at a folder of your config to keep uploads across upgrades and new containers. |
| `temp` | path | `<config>/temp` (`<config>/temp/<instance-id>` with an `instance-id`) | Public folder at `/temp/`, emptied on every memory clean |
| `log-folder` | path | `<config>/logs` (`<config>/logs/<instance-id>` with an `instance-id`) | One `<app_id>.log` per app (stdout and stderr). The previous run is kept as `.log.1`. |
| `schedule` | `"HH:MM"`, `null` or `"off"` | `"02:00"` | Daily memory clean. `null`, `""` or `"off"` disables it. |
| `timezone` | IANA name | server local | Time zone of `schedule`, for example `America/Montreal`. An unknown name stops startup (and is refused on save). |
| `template-folder` | path | bundled | Templates here override the bundled ones by name |
| `template-file` | string | `main.html` | Layout of the landing, news and board pages: `main.html` (top menu), `main_side.html` (sidebar menu on wide screens; its old name `main_2.html` still works, with a warning), `main_nomenu.html` (no menu), or your own |
| `site-title`, `team-name`, `logo`, `footer` | string | `Streamhub`, `""`, `""`, `""` | Branding. `logo` is an image URL for the top menu; without it the menu shows the Streamhub logo, followed by `site-title` unless that is "Streamhub" or "Streamhub Demo". `site-title` also heads the landing page and names the browser tab; `team-name` shows under the menu; `footer` replaces `site-title` in the footer. |
| `slack-name` | string | `""` | Channel name, used in logs only |
| `slack-hook` | URL | `""` | Slack incoming webhook that receives every event. Prefer the `STREAMHUB_SLACK_HOOK` env var. |
| `notifiers` | list | `[]` | More notification channels ([Notifications](#notifications)) |
| `smtp` | object | `{}` | Mail server for email channels and issue reports ([Notifications](#notifications)) |
| `oidc`, `ldap`, `group-mapping`, `sso-default-role` | object, object, list, role | `{}`, `{}`, `[]`, `null` | Single sign-on ([Single sign-on](#single-sign-on)) |
| `virtual-environment` | string | `""` (the hub's interpreter; `python` from PATH for the [executable](operations.md#build)) | Default env for apps without one: a conda env name or an environment folder |
| `port` | int | `8500` | HTTP port |
| `ssl_port` | int | `0` (off) | HTTPS port. Requires `ssl-cert` and `ssl-key`. |
| `ssl-cert`, `ssl-key` | path | – | PEM files for HTTPS |
| `behind-proxy` | bool | `false` | Trust `X-Forwarded-*` / `X-Real-IP` from a reverse proxy in front of the hub |
| `port-range` | `[first, last]` | `[port+1, port+1000]` | Internal ports handed to apps |
| `port-exception` | int[] | `[8501]` | Ports never handed out |
| `cookie-secret` | string | generated | Prefer `STREAMHUB_COOKIE_SECRET`. If neither is set, a random secret is stored in `<config>/.streamhub-secret`. |
| `session-days` | int | `7` | Login lifetime |
| `sso-session-minutes` | int | `0` (`session-days`) | SSO sessions older than this must sign in again, so directory group changes apply within this time |
| `sessions-db` | path | `<config>/.streamhub-sessions.sqlite3` | Session inventory and revocations ([sessions](architecture.md#access-control)), shared by the instances that use this config folder |
| `idle-timeout` | minutes | `0` (off) | Stop `auto_shutdown` apps with no open session and no request for this long |
| `startup-timeout` | seconds | `120` | How long to wait for an app to answer (health path or port). An app that doesn't answer in time is stopped and counts as failed. |
| `proxy-timeout` | seconds | `300` | Per proxied request or WebSocket connect; also the limit between two chunks of an upload |
| `max-upload-mb` | int | `1024` | Largest request body proxied to an app (streamed, not buffered). Hub pages accept 16 MB. |
| `drain-timeout` | seconds | `10` | On stop or restart, how long to wait for proxied requests and WebSocket sessions to end before stopping the apps |
| `stop-timeout` | seconds | `10` | Grace period between SIGTERM and SIGKILL (Linux); `docker stop` timeout |
| `max-ws-message-mb` | int | `200` | WebSocket message limit, also passed to Streamlit |
| `health-interval` | seconds | `30` | How often running apps with a health path are checked. `0` turns the checks off. |
| `health-failures` | int | `3` | Failed checks in a row before an app is stopped (and restarted under its `restart` policy) |
| `kubernetes-namespace` | string | the hub pod's namespace, else `default` | Namespace of `kubernetes` apps without their own `namespace` |
| `docker-socket` | string | `""` (Docker's default: `DOCKER_HOST`, else `/var/run/docker.sock`, or the named pipe on Windows) | Daemon of `docker` apps and the admin page's Docker tab: a socket path (used as `unix://<path>`) or a Docker host URL (`unix://`, `npipe://`, `tcp://`), passed as `docker -H` |
| `docker-network` | string | `""` (publish on `127.0.0.1`) | For a hub that runs in a container: `docker` apps join this network instead of publishing a port, and the hub reaches them by container name ([operations.md](operations.md#app-runtimes-docker-and-kubernetes)) |
| `instance-id` | string | `""` | Name of this hub among [several instances](operations.md#multiple-instances): 1–32 lowercase letters, digits and `-`. Sets the `streamhub_instance` cookie and separate log and temp folders. |
| `env-passthrough` | string[] | `[]` | Names (globs such as `AWS_*`) of hub environment variables that every app receives. Apps otherwise get only what programs need (`PATH`, locale, temp and home folders, proxies, CA bundles, `CONDA_*`) plus the [app variables](operations.md#deploying-an-app). |
| `bind-check` | `warn`, `refuse`, `off` | `warn` | When a `process` app becomes ready, look for its processes listening on a non-loopback address ([SEC-12](known-issues.md#sec-12)). `refuse` stops the app and shows why. |
| `streamlit-user-headers` | bool | `false` | Fill `st.user` (`name`, `role`) in `.sl` apps from the hub's identity headers. Needs a Streamlit with `server.trustedUserHeaders` (1.66 works); older ones refuse to start. Per app: `streamlit_user_headers`. |
| `usage-retention-days` | int | `90` | Days of hourly usage kept in `<log-folder>/usage.sqlite3` (`0`: all). Lifetime totals are always kept. |

The `--port` and `--ssl-port` CLI flags override the file, also when it is reloaded. The old `master-password` key is ignored and produces a warning.

### Notifications

Every channel receives the events listed in its `events`, or all of them when `events` is missing. The events are:

| Event | Sent when |
|---|---|
| `system` | The hub starts, stops or restarts |
| `clean` | A memory clean runs |
| `health` | An app is stopped after failing its health checks |
| `report` | A user sends the "Report an issue" form |

```json
"notifiers": [
  { "type": "teams", "url": "https://….logic.azure.com/…", "events": ["health", "report"] },
  { "type": "email", "to": ["ops@example.com"], "events": ["health"] },
  { "type": "slack", "url": "https://hooks.slack.com/…" }
],
"smtp": { "host": "smtp.example.com", "port": 587, "starttls": true, "username": "streamhub", "from": "streamhub@example.com" }
```

| Channel | Payload |
|---|---|
| `slack` | `{"text": …}` to an incoming webhook |
| `teams` | An Adaptive Card to a Teams "Workflows" webhook. Slack `:emoji:` codes are removed. |
| `email` | Plain-text mail through `smtp` |

**SMTP:**

- `ssl: true` uses implicit TLS (port 465).
- Otherwise `starttls` defaults to `true` (port 587).
- The password comes from `STREAMHUB_SMTP_PASSWORD`.

**Issue reports** go to the `report` channels. When `smtp` is set, they are also emailed to the app's `developer` addresses, with the reporter's address as `Reply-To`. `--debug` turns every channel off.

### Single sign-on

Users can sign in with an OpenID Connect provider (button on the login page), with an LDAP directory (the normal login form, after the users file), or both.

```json
"oidc": { "issuer": "https://login.example.com/realms/main", "client-id": "streamhub", "label": "Sign in with Okta",
          "scopes": ["openid", "profile", "email"], "username-claim": "preferred_username", "groups-claim": "groups" },
"ldap": { "url": "ldaps://ldap.example.com", "bind-dn": "cn=streamhub,ou=svc,dc=example,dc=com",
          "search-base": "ou=people,dc=example,dc=com", "search-filter": "(uid={username})", "group-attribute": "memberOf" },
"group-mapping": [
  { "group": "data-team", "role": "user", "boards": ["sales.brd"] },
  { "group": "cn=ops,ou=groups,dc=example,dc=com", "role": "manager", "boards": ["*"] }
],
"sso-default-role": null
```

**`oidc` keys:**

| Key | Default | Description |
|---|---|---|
| `issuer`, `client-id` | required | `https://`. `<issuer>/.well-known/openid-configuration` must exist and name the same issuer, and every endpoint it lists must be `https://`. The client secret comes from `STREAMHUB_OIDC_CLIENT_SECRET`. |
| `algorithms` | `RS256` … `ES512` | ID-token signature algorithms accepted (a subset of RS, PS and ES 256/384/512). Tokens are checked against the provider's `jwks_uri`. |
| `insecure-http` | `false` | Development only: allow an `http://` issuer and endpoints. Signatures are still checked. |
| `scopes` | `openid profile email` | Requested scopes |
| `username-claim` | `preferred_username` | Claim used as the Streamhub user name; falls back to `email`, then `sub`. Pick a claim users can't change themselves. |
| `groups-claim` | `groups` | Claim, in the ID token or userinfo, that lists the user's groups |
| `token-auth` | `basic` | `basic` (`client_secret_basic`) or `post` (`client_secret_post`) |
| `redirect-uri` | `<scheme>://<host>/login/oidc/callback` | Register this URL with the provider. Set it explicitly behind a proxy that changes the host. |
| `label` | `Single sign-on` | Button text |

**`ldap` keys:**

| Key | Description |
|---|---|
| `url` | Required. `ldap://` or `ldaps://` |
| `user-dn` | Bind directly as this DN, with `{username}`, for example `uid={username},ou=people,dc=example,dc=com` |
| `bind-dn`, `search-base`, `search-filter` | Instead of `user-dn`: bind as a service account (password in `STREAMHUB_LDAP_BIND_PASSWORD`), find the user with the filter (default `(uid={username})`), then bind as that user |
| `group-attribute` | Attribute that lists the groups (default `memberOf`) |
| `starttls` | `true` to upgrade an `ldap://` connection. If the upgrade fails, nothing is sent. |
| `ca-file` | PEM file of the CA that signed the directory's certificate (default: the system CAs). Certificates and host names are always verified. |
| `allow-plaintext` | Development only: allow `ldap://` without `starttls`, so passwords cross the network unencrypted |

LDAP needs the `ldap` extra: `pip install "py-streamhub[ldap]"`. OpenID Connect needs the `oidc` extra (PyJWT): `pip install "py-streamhub[oidc]"`; the hub refuses to start with `oidc` set but PyJWT missing.

**Group mapping:**

- Rules match group names case-insensitively; `"group": "*"` matches everyone.
- The highest matching role wins, and the boards of every matching rule are combined.
- A user that matches no rule gets `sso-default-role` with no boards. When it is `null`, that user is refused.
- Role and boards are fixed at login and kept in the session cookie, so group changes apply at the next login. `sso-session-minutes` bounds how long that can take; an admin can also revoke sessions on `/admin/`.
- To give one SSO account its own role and boards, add it to the users file with its `source` ([Users file](#users-file-streamhub-usersjson)).

### Environment variables

| Variable | Effect |
|---|---|
| `STREAMHUB_SLACK_HOOK`, `STREAMHUB_COOKIE_SECRET`, `STREAMHUB_INSTANCE_ID`, `STREAMHUB_DOCKER_SOCKET`, `STREAMHUB_DOCKER_NETWORK` | Override the matching keys. Keep secrets out of git. |
| `STREAMHUB_SMTP_PASSWORD`, `STREAMHUB_OIDC_CLIENT_SECRET`, `STREAMHUB_LDAP_BIND_PASSWORD` | Secrets for `smtp`, `oidc` and `ldap` |
| `STREAMHUB_METRICS_TOKEN` | Bearer token that a Prometheus scraper sends to `/metrics` |
| `STREAMHUB_ADMIN_PASSWORD` (+ optional `STREAMHUB_ADMIN_USER`, default `admin`) | Adds or replaces an admin user without a users file. `streamhub demo` (and `make demo`) default it to `admin`; the Docker image and Compose leave it unset, so a new hub opens on the [setup page](operations.md#install). A raw value is hashed in memory at first use; a hash from `streamhub passwd` is used as is. |
| `STREAMHUB_DOCKER`, `STREAMHUB_KUBECTL` | Paths of the `docker` and `kubectl` executables when they are not on PATH |
| `STREAMHUB_SUPERVISED=1` | Same as `--supervised` |
| `STREAMHUB_CONFIG` | The config folder (or file) of `streamhub run` when none is given. The Docker image sets it to `/config`. |

## Apps file: `streamhub-apps.json`

A JSON array. **Element 0** defines the boards, and every following element is an app. The file is re-read when it changes. If an edit makes it invalid (bad JSON, a duplicate `app_id`, a `restart` other than `never`, `on-failure` or `always`, a value of the wrong type), the hub logs the error, shows it on `/admin/`, and keeps the last good version. `streamhub check` also warns about undefined boards and missing files.

### Boards (element 0)

```json
{ "boards": [ { "name": "sales.brd", "label": "Sales", "auth": true } ] }
```

| Key | Description |
|---|---|
| `name` | Unique ID ending in `.brd` |
| `label` | Menu text (defaults to `name`) |
| `auth` | `true` means only users whose `boards` include it (or `*`) can see the board **and launch its apps** |

The landing page is the board `""`. Apps that list `""` appear there and are public.

### App entry

| Key | Applies to | Default | Description |
|---|---|---|---|
| `app_id` | all | required | Unique ID; the app's URL is `/<app_id>/`. With `type`, any name works except the hub's own paths (`catalog.RESERVED_IDS`: `admin`, `api`, `cdf`, `login`, … and names ending in `.brd`), which only a `page` may use; the admin page's app editor checks the ID as you type. Without `type`, as before 2.2, the suffix sets the type: `.sl` (Streamlit), `.py` (Python web app), `.url`, `.curl`, `.cmd` (built-in: `help.cmd`), and no suffix a hub page. |
| `type` | all | from the `app_id` suffix | `streamlit`, `python` (any web server run as a process), `docker` or `kubernetes` (run an `image`), `url` (redirect to `url`), `curl` (proxy to `url`, which stays hidden), or `page` (a link to the hub page `/<app_id>/`; the admin pages need no entry, they are in the account menu: [operations.md](operations.md#endpoints-and-access)). It wins over the suffix. |
| `serves` | `docker`, `kubernetes` | `web` | What the image runs: `streamlit` (it gets the Streamlit flags, keeps the `/<app_id>` prefix and is checked on `_stcore/health`) or `web` (any other server: requests arrive without the prefix) |
| `board` | all | `[]` | Boards the app is listed on, which also decide who can use it |
| `app_name`, `description`, `icon` | all | `app_id`, `""`, `""` | Card text and icon URL |
| `display` | all | `show` | `show`, `disabled` or `hidden`. Hidden apps still open by URL, subject to the board access rules. |
| `developer` | all | `[]` | `[{ "name", "email" }]` for `/report/` |
| `children` | parents | `[]` | Nested apps with the same schema, one level deep |
| `url` | `url`, `curl` | – | Target URL |
| `file` | `streamlit`, `python`, `docker`, `kubernetes` | – | Entry script: relative to `folder`, or a path inside the image. A `web` image with neither `file` nor `command` runs its own command. |
| `folder` | `streamlit`, `python` | – | The entry script's folder, also the working directory |
| `virtual_environment` | `streamlit`, `python` | `virtual-environment` | Conda env name or environment folder. The interpreter is called directly, without activation. |
| `python_executable` | `streamlit`, `python` | – | Explicit interpreter path; overrides `virtual_environment` |
| `activate` | `streamlit`, `python` | `false` | Launch through `conda run -n <env>`, for envs that need activation (some Windows DLLs) |
| `command` | `streamlit`, `python`, `docker`, `kubernetes` | – | Full argument list with `{python}`, `{port}`, `{app_id}` and `{base_path}` placeholders. Replaces `file`. |
| `bash_file` | `streamlit`, `python` | – | Launcher script, run by extension (`.sh`/`.bash` with bash, `.bat`/`.cmd` with `cmd /c`, `.ps1` with PowerShell). It receives the port flags and must forward them (`$@` / `%*`). |
| `args` | `streamlit`, `python`, `docker`, `kubernetes` | `[]` | Extra arguments appended to the command |
| `env` | `streamlit`, `python`, `docker`, `kubernetes` | `{}` | Extra environment variables |
| `env_passthrough` | `streamlit`, `python`, `docker`, `kubernetes` | `[]` | Like `env-passthrough`, for this app only. For `kubernetes` apps the values are written into the Pod spec ([SEC-20](known-issues.md#sec-20)). |
| `streamlit_user_headers` | Streamlit apps and images | `streamlit-user-headers` | Fill `st.user` from the hub's identity |
| `auto_shutdown` | `streamlit`, `python`, `docker`, `kubernetes` | `true` | Stopped by a standard memory clean and by the idle timeout |
| `auto_start` | `streamlit`, `python`, `docker`, `kubernetes` | `false` | Started when the hub starts and after scheduled cleans |
| `idle_timeout` | `streamlit`, `python`, `docker`, `kubernetes` | `idle-timeout` | Per-app idle timeout in minutes (`0` disables it) |
| `restart` | `streamlit`, `python`, `docker`, `kubernetes` | `never` | `on-failure` or `always`: relaunch after a crash or failed health checks, with backoff |
| `health_path` | `streamlit`, `python`, `docker`, `kubernetes` | `_stcore/health` for Streamlit, none otherwise | Path under `/<app_id>/` that answers 2xx/3xx when the app is healthy. Used for readiness and the periodic checks. `""` turns it off. |
| `runtime` | apps without `type` | `process` | Before 2.2: `process`, `docker` or `kubernetes` for `.sl` and `.py` apps. `"type": "docker"` (or `kubernetes`) replaces it ([operations.md](operations.md#app-runtimes-docker-and-kubernetes)). |
| `image` | `docker`, `kubernetes` | required | Container image. `file` and `command` are then paths and commands inside the image; `folder`, `bash_file`, `virtual_environment`, `python_executable` and `activate` are ignored. |
| `container_port` | `docker`, `kubernetes` | `8501` for Streamlit, `8000` otherwise | Port the app listens on inside the container |
| `volumes` | `docker` | `[]` | `docker run -v` values: `"<host path or named volume>:<path in the container>[:ro]"`. Host paths are on the Docker host, which differs from the hub's file system when the hub runs in a container. |
| `runtime_args` | `docker` | `[]` | Extra `docker run` arguments, for example `["--memory=2g", "--cpus=1"]` |
| `kubernetes` | `kubernetes` | `{}` | `namespace`, `resources`, `node_selector`, `service_account`, `image_pull_policy`, `image_pull_secrets`, `env_from` (copied into the Pod spec) |

## Users file: `streamhub-users.json`

Create it with `streamhub init`, the [setup page](operations.md#install) or the admin page's Users tab, which writes the hashes for you. Keep it out of git.

**An unusable users file grants nothing.** If the file becomes invalid (bad JSON, an unknown `role` or `source`), unreadable, or is deleted after the hub loaded it, its local users are logged out and SSO logins and sessions are refused until the file is fixed; `/admin/` shows the error. Only the `STREAMHUB_ADMIN_PASSWORD` admin can still log in. To remove every user, write `{}`. A users file that never existed simply has no users.

**Passwords are stored as hashes only** (`pbkdf2_sha256$<iterations>$<salt>$<digest>`, 600,000 iterations).
- Create one with `streamhub passwd`.
- To convert a file that still holds raw passwords, run `streamhub hash-passwords <config folder or users file>`. It rewrites the file in place, checks each new hash first, and prints only user names.
- A raw password cannot log in. The hub logs an error naming the user and the command to fix it.
- The [admin page](operations.md#endpoints-and-access) Users tab and JSON editor never show passwords: the editor shows `********` instead. Keeping `********` leaves a password unchanged; typing a new value stores its hash.

```json
{
  "alice": { "password": "pbkdf2_sha256$600000$…", "role": "admin", "boards": ["*"] },
  "bob":   { "password": "pbkdf2_sha256$600000$…", "role": "user",  "boards": ["sales.brd"] },
  "carol@example.com": { "source": "oidc", "role": "manager", "boards": ["*"] }
}
```

An entry with `"source": "oidc"` or `"ldap"` has no password. It sets the role and boards of that SSO account instead of the group mapping, and it can't be used to log in with the form ([sessions](architecture.md#access-control)).

| Role | Grants |
|---|---|
| `admin` | Every app, `/api/`, `/update/`, `/restart/`, `/exit/`, "stop all apps" on `/clear/`, and on `/admin/` the apps, users, news and settings editors, Docker, static files, sessions, the JSON editor and git |
| `manager` | `/admin/`: server load, start, stop, restart, logs, usage and CPU affinity of apps; the `/api/apps/<id>/start\|stop\|restart` endpoints |
| `user`, `guest` | The boards listed in `boards`, `/clear/` (apps with `auto_shutdown` only), and `/out/` for apps they can use |

## News file: `streamhub-news.json`

An array of `{ "title", "date", "message", "type" }`, where `type` is `normal`, `info` or `warning`. Entries without `title` are skipped. News appears only on `/`.

## Applying changes

- **Apps, users and news files:** apply on the next request, whether edited on disk or on `/admin/`.
- **`streamhub.json`:** a save on `/admin/` (Settings or JSON files) applies it at once. After an edit on disk, apply it with **Reload configuration** (`/update/`, admin). Most keys take effect immediately, including the schedule. Both list any that need a restart (`config.RESTART_ONLY`), and the Settings tab offers **Restart now**: ports, TLS, `behind-proxy`, folders, `cookie-secret`, `port-range`, `max-ws-message-mb`, `health-interval`, `instance-id`, `sessions-db` and `usage-retention-days`. It also names any catalog file that is currently invalid.
