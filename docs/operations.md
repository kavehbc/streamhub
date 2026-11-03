# Operations

## Install

Streamhub needs Python ≥ 3.11 on Linux or Windows, unless you use the [executable](#build). The distribution name is `py-streamhub` ([PyPI](https://pypi.org/project/py-streamhub/)); the import package and the command stay `streamhub`. Installing it adds the `streamhub` command. From PyPI, from GitHub, or as a tool in its own environment from a [built or released wheel](#releases):

```bash
pip install "py-streamhub[tools]"
pip install "py-streamhub[tools] @ git+https://github.com/kavehbc/streamhub"   # the latest commit
pipx install "dist/py_streamhub-2.3.0-py3-none-any.whl[tools]"   # or: pip install "<wheel>[tools]"
```

From a checkout (the repository root):

```bash
pip install -e ".[tools]"            # hub + help.cmd (Streamlit)
pip install -e ".[tools,examples]"   # + Flask/FastAPI/uvicorn for the demo apps (streamhub demo)
pip install -e ".[tools,ldap]"       # + ldap3 for LDAP login
pip install -e ".[tools,oidc]"       # + PyJWT for OpenID Connect login (ID-token signatures)
make install                         # development: tools, examples and tests (make.bat install on Windows)
```

Or with conda: `conda env create -f environment.yml`. Each app's own environment needs its framework (`streamlit` for Streamlit apps).

**First config.** Any of these gives a hub its first admin:

| Way | What it does |
|---|---|
| `streamhub init <folder>` | Asks for the site title, port, admin name and password (or takes `--yes`, `--site-title`, `--port`, `--admin-user`, `--admin-password`). Writes the [starter](../streamhub/starter/) `streamhub.json`, apps and news files, and a users file with the hashed admin. It never overwrites a file unless you pass `--force`; with `--force`, the other users are kept. |
| Setup page | A hub without an admin, run directly or in Docker, logs `No admin account yet: open <server-url>:<port>/ and enter the setup token below, or open …/setup/?token=…`, then `Setup token: …`. Until an admin exists, the start page `/` redirects to `/setup/`: one form for the admin's name and password, the site title and team name, and the token. The token field says where to find the token (`docker logs <container ID>` in a container) and also takes the whole link. Opened from the link, the form has the token already ([access](architecture.md#access-control)). |
| `STREAMHUB_ADMIN_PASSWORD` | An admin from the environment ([configuration](configuration.md#environment-variables)) |
| Users file | Hashes from `streamhub passwd` (or `make passwd`), in `streamhub-users.json` ([format](configuration.md#users-file-streamhub-usersjson)) |

A config folder is yours: in this repository, [config/](../config/) is git-ignored except its README. The demo, [streamhub/demo/](../streamhub/demo/), ships in the package.

## Run

```bash
streamhub run [--port N] [--ssl-port N] [--debug] [--supervised] [--log-level LEVEL] [<config dir | streamhub.json>]
streamhub run my-hub              # the folder defaults to $STREAMHUB_CONFIG, else the current one
python -m streamhub run my-hub    # same thing; python main.py run ... also works
```

| Command | Does |
|---|---|
| `streamhub run [options] [CONFIG]` | Runs the hub on a config folder (or `streamhub.json`). CONFIG defaults to `STREAMHUB_CONFIG`, else `.`. A missing folder is an error that suggests `init` and `demo`; a folder without `streamhub.json` runs on the defaults. |
| `streamhub init [FOLDER]` | Writes a starter config folder ([First config](#install)) |
| `streamhub demo [--port N] [--debug] [--folder DIR]` | Copies the [bundled demo](../streamhub/demo/) to a writable folder (default: `demo/` in the per-user data folder, [`platform_utils.user_data_dir`](windows-compatibility.md#behavior-differences)) and runs it, with the admin `admin` / `admin` unless `STREAMHUB_ADMIN_PASSWORD` is set. Each run refreshes the demo apps and keeps the demo's JSON files, logs and sessions. The apps need the `examples` extra. |
| `streamhub passwd [PASSWORD]` | Prints a password hash for the users file (prompts without PASSWORD) |
| `streamhub hash-passwords [CONFIG]` | Replaces the raw passwords left in the users file with hashes, in place (CONFIG: a config folder or the users file) |
| `streamhub check [CONFIG]` | Validates a config folder without starting anything: settings, the apps, users and news files, undefined boards, missing files and tools, raw passwords, and risky settings (secrets in the file, `env-passthrough` of hub secrets, `bind-check` off, development-only SSO options). Prints errors and warnings, never secret values; exits with 1 on errors. CI runs it on the demo config. |
| `streamhub version`, `streamhub --version` | Prints the version |
| `streamhub --help`, `streamhub run --help` | Lists the commands and the options |

`streamhub [options] CONFIG`, without `run`, still works (2.0 form), and so does the `streamhub-passwd` command.

| `run` option | Effect |
|---|---|
| `--port`, `--ssl-port` | Override `port` and `ssl_port`, also across configuration reloads |
| `--debug` | Debug logs and tracebacks; notifications are turned off |
| `--supervised` (or `STREAMHUB_SUPERVISED=1`) | `/restart/` exits with code 3 so a service manager restarts the hub. Without it, the hub starts a new copy of itself. |

Common tasks are targets of the [Makefile](../Makefile) (Linux, macOS, Git Bash) and of [make.bat](../make.bat) (Windows cmd or PowerShell). Both take the same names (`make help` lists them):

| Target | Runs |
|---|---|
| `install`, `install-ldap`, `install-build` | `pip install -e ".[tools,examples,dev]"` (plus `ldap`, or the `build` tools) |
| `test` | `pytest -q`: unit, handler, integration and documentation-link tests |
| `demo` | `streamhub demo --debug` |
| `start` | The hub on `CONFIG` (default `config`), with its output appended to `logs/streamhub.log` |
| `check` | `streamhub check` on `CONFIG` |
| `passwd` | `streamhub passwd` |
| `dist`, `exe` | The wheel and sdist, or the single-file executable ([Build](#build)) |
| `docker-build`, `docker-up`, `docker-down`, `docker-logs` | The image, tagged `kavehbc/streamhub:<version>` and `kavehbc/streamhub:latest`, and the Compose stack |
| `k8s-image` | `streamhub-kubectl:<version>`: the hub image with `kubectl` for the Kubernetes runtime (built on `IMAGE`) |
| `docs` | The documentation site ([readthedocs/](../readthedocs/README.md)) into `readthedocs/_build/html`, with warnings as errors; needs `pip install -r readthedocs/requirements.txt` |
| `clean` | Caches and build output (including the documentation build) |

**Overrides:**
- Makefile: `PYTHON`, `CONFIG`, `ARGS` (extra `streamhub` options) `IMAGE_NAME` (default `kavehbc/streamhub`), and `IMAGE` and `LATEST` (the two tags `docker-build` applies), for example `make start CONFIG=/etc/streamhub ARGS=--supervised`.
- make.bat: set `PYTHON`, `CONFIG`, `IMAGE_NAME`, `IMAGE` and `LATEST` as environment variables, and pass extra options after the target: `set CONFIG=C:\streamhub-config` then `make.bat start --supervised`.

Logs go to stderr; the `streamhub.audit` logger records logins (with their source), admin actions, issue reports and admin-page edits.

The hub stops cleanly on SIGINT (Ctrl+C), SIGTERM, SIGQUIT, or SIGBREAK on Windows. A clean stop first drains: it stops accepting connections and waits up to `drain-timeout` (10 s) for proxied requests and WebSocket sessions to end (an open Streamlit tab keeps its session, so expect the full wait). Then it stops every app, saves the usage counters, empties `temp/` and sends a `system` notification. If the hub crashes instead, the next start stops the apps it left behind ([architecture.md](architecture.md#app-lifecycle)).

## Build

Two build outputs, both in `dist/`. Install the tools once with `make install-build` (`pip install -e ".[build]"`).

| Command | Output | Runs on |
|---|---|---|
| `make dist` (`python -m build`) | `py_streamhub-<version>-py3-none-any.whl` and `.tar.gz` | Any OS with Python ≥ 3.11: `pip install` or `pipx install` it, then `streamhub run <config>` |
| `make exe` (PyInstaller) | `streamhub` (`streamhub.exe` on Windows), one file of about 10 MB | The OS it was built on; no Python needed for the hub itself |

`make.bat dist` and `make.bat exe` do the same on Windows. The executable is built from [deploy/pyinstaller/streamhub.spec](../deploy/pyinstaller/streamhub.spec). It bundles the templates, static files, the starter config, the demo apps, the `help.cmd` page and this README. To build:

- **Build once per OS:** PyInstaller doesn't cross-compile. Build on Linux for Linux (preferably on the oldest glibc you deploy to), and on Windows for Windows.
- **Conda Pythons:** they work. The spec adds the environment's `Library\bin` to PATH so DLLs such as libffi are found.
- **Run it like the installed command:** `./streamhub run <config>`, `streamhub.exe passwd`, and so on.

The executable has no Python of its own, so:
- Apps without `virtual_environment` or `python_executable` run with `python` from PATH (`python3` first on Linux). Prefer setting `virtual-environment`.
- `help.cmd` needs Streamlit in that Python.
- `/restart/` relaunches the executable itself. It unpacks into a new temporary folder, because the old one is deleted when the old copy exits.

### Releases

[ci.yml](../.github/workflows/ci.yml) runs on pushes and pull requests to `main` or `master`. A push also builds the wheel and sdist (installed into a clean environment as a check) and the Docker image. When every job passes and the release `v<version>` (`__version__` in [`streamhub/__init__.py`](../streamhub/__init__.py)) doesn't exist yet, the `release` job:

- pushes the image to `ghcr.io/kavehbc/streamhub:<version>` and `:latest` (with `GITHUB_TOKEN`; a new package is private until you change its visibility on GitHub);
- creates the GitHub release and tag `v<version>` on the pushed commit, with the wheel, the sdist and `streamhub-<version>-docker-image.tar.gz` (`docker load -i`, tagged `kavehbc/streamhub:<version>` and `:latest`). Its notes are the README changelog section of that major.minor version.

A push without a version bump publishes nothing. The executable isn't part of a release.

### Docker

```bash
docker run -p 8500:8500 -v streamhub-config:/config kavehbc/streamhub   # your hub; open it, the setup token is in docker logs
docker run -p 8500:8500 kavehbc/streamhub streamhub demo                # the demo, login admin / admin
docker compose up -d --build  # ./config on http://localhost:8500; the setup token is in docker compose logs
cp .env.example .env          # optional: STREAMHUB_ADMIN_PASSWORD, STREAMHUB_COOKIE_SECRET, DOCKER_GID…
```

The image ([Dockerfile](../Dockerfile)) has the `tools`, `examples` and `oidc` extras and runs as a non-root user in supervised mode, with a health check on `/api/health`. It runs `STREAMHUB_CONFIG` (`/config`, a volume).

**Admin login:** the image sets no password. An empty `/config` runs on the defaults: the first visit to `http://localhost:8500/` opens the [setup page](#install), which asks for the setup token and shows the `docker logs` command that prints it. Pass `-e STREAMHUB_ADMIN_PASSWORD=…` (Compose: `.env`) to define an admin instead. `streamhub demo` uses `admin` / `admin` unless that variable is set; while that default is in use, the hub logs a warning at startup and `/admin/` shows a banner. [docker-compose.yml](../docker-compose.yml) has these relevant settings:

- `restart: on-failure`: `/restart/` (exit code 3) starts the hub again, while `/exit/` (exit code 0) leaves it stopped.
- `init: true`: adds an init process that reaps orphaned processes.
- `./config` is mounted at `/config`.
  - It is the hub's config folder (`STREAMHUB_CONFIG` in `.env` picks another path in the container). Saves on the admin page go there.
  - The container user (uid 1000) must be able to write there (logs, temp files, the cookie secret and the session database); otherwise point `log-folder`, `temp` and `sessions-db` elsewhere. Without a writable `sessions-db`, revocations apply to the running instance only.
  - The bundled `cdf` folder is writable but belongs to the container: set `cdf` to a folder under `/config` to keep uploaded static files.
- `/var/run/docker.sock` is mounted, for [docker apps](#app-runtimes-docker-and-kubernetes) and the admin page's Docker tab (the image has the `docker` client). `group_add` gives uid 1000 the socket's group: `DOCKER_GID` in `.env`, default `0` (Docker Desktop); on Linux, `getent group docker | cut -d: -f3`. Control of the daemon is control of the host ([SEC-21](known-issues.md#sec-21)): remove the mount and `group_add` if you don't need Docker.
- The hub joins the `streamhub-apps` network and sets `STREAMHUB_DOCKER_NETWORK=streamhub-apps`, so docker apps run on that network.

### Services

- **Linux:** [deploy/streamhub.service](../deploy/streamhub.service) (systemd, `Restart=on-failure`).
- **Windows:** see [windows-compatibility.md](windows-compatibility.md#deploying-on-windows).

## App runtimes (Docker and Kubernetes)

An app with `"type": "docker"` or `"kubernetes"` (before 2.2: `"runtime"`) runs from its `image` instead of a local environment ([keys](configuration.md#app-entry), [mechanism](architecture.md#app-lifecycle)).

**Docker:**
- The `docker` CLI must be on the hub's PATH (or set `STREAMHUB_DOCKER`), and the hub's user must be allowed to use the daemon: `docker-socket` picks the daemon (default `/var/run/docker.sock`).
- **Hub on the host:** the container is published on `127.0.0.1` only.
- **Hub in a container** (with the host's socket mounted): set `docker-network` to a network the hub's container is on. Apps then join it without publishing a port, and the hub proxies to `http://<container name>:<container_port>`. Without it, the app's port is published on the host's loopback, which the hub's container can't reach. [docker-compose.yml](../docker-compose.yml) sets this up.
- `serves` says what the image runs: `streamlit` gets the Streamlit flags and `file`; `web` (the default) runs `file`, `command`, or, with neither, the image's own command, listening on `container_port`.
- `env` sets its environment variables, `volumes` mounts host paths or named volumes (`-v`), and `runtime_args` adds other `docker run` options, such as limits.
- A missing image is pulled by `docker run`, within `startup-timeout`: pull big images first (admin page, Docker tab).

**Kubernetes:**
- The hub must run **inside the cluster**, because it proxies to `http://<service>.<namespace>.svc:<container_port>`.
- [deploy/kubernetes/](../deploy/kubernetes/) has an image with `kubectl` ([Dockerfile](../deploy/kubernetes/Dockerfile)), and a [manifest](../deploy/kubernetes/streamhub.yaml) with the ServiceAccount, the Role the hub needs (pods and services: get, list, watch, create, patch, delete; pods/log: get) and the hub's Deployment.
- Apps are created in `kubernetes.namespace`, then `kubernetes-namespace`, then the hub's own namespace.

**Docker tab** (admin page, admins only): the client, the daemon and its version, and whether `docker-network` exists; every container (all, the hub's apps by their `streamhub.app` label, or running), with start, stop, restart, logs and remove (the hub's own container is marked, and stopping it stops Streamhub); every image, with pull, remove, and **New app**, which opens the app editor on that image. Stopping an app's container stops the app, and its `restart` policy applies.

**Both runtimes:**
- Leftover containers or pods of the same `instance-id` are removed when the hub starts.
- `STREAMHUB_URL` points at the hub's loopback address, which a container can't reach.

## Single sign-on

Configuration keys: [configuration.md](configuration.md#single-sign-on).

**OIDC:**
1. Register a confidential client with the provider. Use the redirect URI `https://<hub host>/login/oidc/callback`, the authorization code flow, and a groups claim.
2. Set `oidc` and `STREAMHUB_OIDC_CLIENT_SECRET`.
3. Install the `oidc` extra and serve the hub over HTTPS (directly or with `behind-proxy`). The issuer and its endpoints must be `https://`, and ID tokens must be signed with a key from its `jwks_uri` ([keys](configuration.md#single-sign-on)).

**LDAP:**
- Install the `ldap` extra, set `ldap`, and set `STREAMHUB_LDAP_BIND_PASSWORD` for search binds.
- Use `ldaps://` or `starttls: true`, because passwords cross that connection. Set `ca-file` for a private CA.

**Both:**
- Map groups to roles and boards with `group-mapping`.
- Set `sso-session-minutes` so removed group memberships take effect without waiting for `session-days`.
- Failed and refused SSO logins are logged to `streamhub.audit`.

## Notifications

Configure Slack, Teams and email channels with `notifiers` and `smtp` ([configuration.md](configuration.md#notifications)). Delivery failures are logged as warnings (with the webhook's host, never its URL), counted in `/metrics`, and never stop the hub.

## Metrics

`GET /metrics` serves Prometheus text format to a manager's session, or to a scraper that sends `Authorization: Bearer <STREAMHUB_METRICS_TOKEN>`. It holds no user names, emails or URLs.

| Metric | Labels | Meaning |
|---|---|---|
| `streamhub_info` | `version`, `instance` | Always 1 |
| `streamhub_uptime_seconds` | – | Since the hub started |
| `streamhub_app_requests_total` | `app` | Page loads and WebSocket sessions, kept across restarts |
| `streamhub_app_up`, `streamhub_app_healthy`, `streamhub_app_sessions`, `streamhub_app_restarts`, `streamhub_app_ready_seconds` | `app` | Per launched app: ready, passing its health checks, open WebSocket sessions, restarts in the current backoff run, time from launch to ready |
| `streamhub_app_start_failures_total` | `app` | Launches that failed, timed out or were refused by `bind-check`, since the hub started |
| `streamhub_notification_failures_total` | `channel` | Undelivered notifications per channel type |
| `streamhub_login_failures_total` | – | Failed logins |
| `streamhub_config_errors` | `file` | 1 for each catalog file that is currently invalid |

Counters other than `app_requests_total` restart at 0 with the hub. Each instance serves its own metrics.

## Multiple instances

Several hubs can serve the same catalog for more users. Each instance runs **its own copies** of the apps it is asked for, so a browser must keep reaching the same instance.

1. Give every instance its own `STREAMHUB_INSTANCE_ID` (or `instance-id`) and `"behind-proxy": true`.
2. Share the config folder (a network share, a ConfigMap or a git checkout) and set the same `STREAMHUB_COOKIE_SECRET` on every instance, so sessions are valid on all of them. Logs and temp files go to per-instance subfolders.
3. Make the load balancer sticky:
   - **nginx:** route on the hub's `streamhub_instance` cookie ([deploy/multi-instance/nginx.conf](../deploy/multi-instance/nginx.conf)).
   - **HAProxy:** insert its own cookie ([deploy/multi-instance/haproxy.cfg](../deploy/multi-instance/haproxy.cfg)).
   - **Kubernetes ingress-nginx:** `nginx.ingress.kubernetes.io/affinity: cookie`. Use a StatefulSet, or set `STREAMHUB_INSTANCE_ID` from `metadata.name`.

Usage counters, metrics, idle timers, health checks and the login throttle are per instance. Sessions are shared: an admin who revokes a session on one instance revokes it on all of them within 5 seconds, as long as they share `sessions-db` (put it on a disk that supports SQLite locking, not NFS).

## Endpoints and access

The routing mechanism is described in [architecture.md](architecture.md#request-routing).

| Endpoint | Who can use it | Behavior |
|---|---|---|
| `/<id>/` (Streamlit, Python, Docker, Kubernetes and proxy apps, `help.cmd`) | Anyone who can see one of the app's boards ([rules](architecture.md#access-control)) | Starts the app on first use, shows a loading page until it is ready, then proxies |
| `/<id>.url/` | Same | 302 redirect to `url` |
| `/admin/` | Manager or admin | The admin panel. Its sections are in a menu at the left, which collapses to icons (remembered per browser; a scrolling strip on phones). Every page links its tabs (`/admin/#dashboard`, `#apps`, `#users`, `#news`, `#settings`, `#docker`, `#static`, `#sessions`, `#files`, `#backup`, `#network`; the old `#config` opens `#files`) from the account menu, which opens from the avatar and also holds the actions below that the user's role allows (`/clear/`, `/update/`, `/restart/`, `/exit/`) and log out. Tabs: **Dashboard** (for admins, a **Getting started** checklist until its steps are done or hidden: save the settings, add an app, replace the demo password, add users or single sign-on, move the static folder out of the package; invalid catalog files and the demo password as a banner; server load; every app with state, health, runtime, PID, port, sessions, memory, CPU and a chart of today's requests; start, stop and restart; log tail; CPU affinity; listening ports; temp folder size, with **Purge**, which empties it (files in use and the readme marker stay). Logs and CPU affinity open in dialogs; the log can follow new output), **Network** (listening ports). Admins also get the editors of the hub's files: **Apps** (boards: add, edit the label and login requirement, delete, which takes the board off its apps; apps: add, edit, delete, add a child, or move an app under another one, with the fields of its type shown; drag the ☰ grip, or focus it and press Up or Down, to reorder boards, top-level apps with their children, or the children of an app, which is the order of the menu, the home page and the board cards; not while the app list is filtered), **Users** (add, edit the sign-in source, role, boards and password, delete; passwords are never shown), **News** (add on top, edit, reorder, delete), **Settings** (every `streamhub.json` key, grouped, with a hint per section and per key, its default as a placeholder, and the keys that need a restart marked; a key set by an environment variable is read-only with the variable named. Lists are drop-downs with descriptions (layout, bind check, SSO default role); `oidc`, `ldap`, `smtp`, `notifiers` and `group-mapping` are forms, with repeatable rows for the lists and **Edit as JSON** for keys the form doesn't know; time zones and Python environments are suggested as you type; paths are checked on the server as you type; the logo has an image picker with upload. Without a `streamhub.json`, the first save creates it). These forms save the whole file through the same endpoint as the JSON editor and write only the fields that changed, so other keys are kept. The app editor starts with the app's **Type** (Streamlit, Python, Docker image, Kubernetes pod, link, proxy, hub page) and shows that type's fields; Docker images get their image (local ones offered), container port, environment variables, volumes and `docker run` options. It describes the chosen type, says as you type whether the app ID is free and whether the folder, entry script, Python executable and launcher script exist on the server, suggests the server's conda environments, offers an icon picker of the `cdf` images (with upload to `icons/`), and edits Kubernetes options with a form. New apps are saved with `type`, so their IDs need no suffix. The Users editor describes each role and can generate a password, shown once. **Docker** manages the daemon's containers and images ([App runtimes](#app-runtimes-docker-and-kubernetes)). **Static files** browses the `cdf` folder (served at `/cdf/`), with thumbnails and the URL of each file; it uploads files (button or drag and drop, 16 MB per upload, replacing a file only after a confirmation), creates folders, renames or moves files and folders, and deletes files and empty folders. Every path must stay inside the `cdf` folder. **Backup** downloads the config, apps, users and news files as one JSON file (password hashes and secrets in the config included, so keep it safe; static files are not), and restores the files you choose from such a file: all are validated first, the current files are saved to `<config>/backups/`, raw passwords are hashed, and a restored config applies at once. Admins also get **Sessions** (revoke one session, or every session of a user) and **JSON files**: the JSON editor (validity shown as you type, Format, Ctrl+S to save) and git status, pull, and commit and push of the config, apps and news files. The editor validates like `streamhub check` and shows its warnings, refuses a save with 409 when the file changed on disk since it was opened, and writes atomically; in the users file, passwords show as `********` and new ones are hashed on save. |
| `/status.cmd/` | – | 301 to `/admin/` |
| `/<board>.brd/` | Anyone (public boards); users with access (`auth` boards) | The board's apps as cards, with search, All / Running / Favorites filters and live status |
| `/news/` | Anyone | Every announcement of the news file, filterable by type; the landing page shows the latest three |
| `/out/<id>/` | Logged-in users who can use the app | Last 256 KB of the app log |
| `/clear/` | Logged-in users ("stop all apps" is admin only) | Stops apps with `auto_shutdown` (or all apps), empties `temp/`, then optionally runs auto-start apps or relaunches the stopped ones |
| `/update/`, `/restart/`, `/exit/` | Admin | Reload the config; restart; stop the hub and all apps |
| `/api/` | Admin, or built-in tools with the internal token | Paths, settings summary, instance, running apps (PID, port, state, health, runtime, upstream, sessions, usage today, log path) |
| `/api/apps` | Anyone | The apps the caller can open, with their state, polled by the landing page |
| `/api/apps/<id>/status` | Anyone who can use the app | `{"state", "ready", "error"}`, polled by the loading page; `error` says why a launch failed |
| `/api/apps/<id>/start`, `/stop`, `/restart` (POST) | Manager or admin (with XSRF), or the internal token | Start, stop or restart one app |
| `/api/apps/<id>/log`, `/api/apps/<id>/affinity`, `/api/admin/state`, `/api/admin/ports` | Manager or admin | Admin page data. Affinity also takes a POST (XSRF). |
| `/api/admin/docker` (GET), `/api/admin/docker/containers/<name>/<start\|stop\|restart\|remove>`, `/api/admin/docker/containers/<name>/logs` (GET), `/api/admin/docker/images/<pull\|remove>` (POST `{"image"}`) | Admin (POSTs with XSRF) | Docker tab: state, containers and images; container actions and logs (last 500 lines); pull (up to 15 minutes) and remove. Names and image references are checked; everything is audited. |
| `/api/admin/cdf` (GET), `/api/admin/cdf/upload?folder=<path>[&overwrite=1]` (multipart `files`), `/api/admin/cdf/<rename\|delete\|folder>` (POST `{"from", "to"}` or `{"path"}`) | Admin (POSTs with XSRF) | Static files tab. An upload over an existing file answers 409 unless `overwrite=1`; a rename never overwrites; delete removes a file or an empty folder. Paths outside the `cdf` folder are refused (400). |
| `/api/admin/backup` (GET), `/api/admin/restore` (POST `{"backup", "files": [...]}`) | Admin (POST with XSRF) | Backup download; restore of the chosen files, all or none, answering 400 with the first invalid file |
| `/api/admin/environments` (GET), `/api/admin/path-check?path=<path>[&base=<folder>]` (GET) | Admin | Suggestions and checks for the editors: the server's conda environments and the hub's Python; whether a path exists, relative to `base`, itself relative to the config folder |
| `/api/admin/temp/purge` (POST) | Manager or admin (with XSRF) | Empties the temp folder; answers with what is left (`bytes`, `files`) |
| `/api/admin/files/<config\|apps\|users\|news>`, `/api/admin/git/<status\|pull\|push>`, `/api/admin/sessions` | Admin (POSTs with XSRF) | The file editors (GET returns a `version`; POST `{"text", "version"}`; a missing config file is created at `<config>/streamhub.json`; a saved config is applied at once, and the response's `restart` lists the keys that still need a restart), git, and sessions (POST `{"id"}` or `{"user", "source"}` revokes) |
| `/api/health` | Anyone | `{"status": "ok", "instance", "version"}` |
| `/metrics` | Manager or admin, or the `STREAMHUB_METRICS_TOKEN` bearer token | [Metrics](#metrics) |
| `/report/?id=<id>` | Anyone | Developer contacts and an issue form. Sending it notifies the `report` channels and, with `smtp`, emails the developers; 5 reports per client per 10 minutes. The answer says whether the report was sent, partly sent, not delivered (502) or had nowhere to go (503). |
| `/setup/[?token=<token>]` | Anyone with the token, only while the hub has no admin | The [first-run setup](#install), where `/` redirects while there is no admin: GET shows the form, with a token field (and where to find the token) unless the URL carries the token; a wrong token, in the URL or the POST, shows the form again with an error (403) and keeps what was typed. POST (with XSRF; `token` may also be the whole link) creates the admin, sets `site-title` and `team-name`, and signs the new admin in. 404 once an admin exists, or when OIDC or LDAP is configured, or when the users file is invalid. |
| `/login/`, `/logout/` | – | Signed `user` cookie (HttpOnly, SameSite=Lax, Secure over HTTPS) with a revocable session ID. Local users, then LDAP. A client gets HTTP 429 once its failed logins in 5 minutes plus its logins in progress reach 10; at most 8 password checks run at once (503 after waiting 10 s). Logout revokes the session. |
| `/login/oidc/`, `/login/oidc/callback` | – | OpenID Connect login (404 when `oidc` isn't set; 502 when the provider's discovery fails) |
| `/cdf/<path>`, `/temp/<path>`, `/static/<path>`, `/favicon.ico` | Anyone | Static files. `temp/` is emptied on every clean, except `readme_will_not_be_deleted.txt`. `/static/` holds the UI stylesheet, the Streamhub logo and icons (`/static/brand/logo.svg`, `logo-mark.svg`), and the bundled Bootstrap and Font Awesome. |

Admin actions use a GET for the confirmation page and a POST to run them. The 1.x `*.cmd` URLs redirect to the new ones. While the hub drains before stopping, `/<id>/` launches and new WebSocket sessions get 503.

## Deploying an app

1. Put the code on the server, with an environment that has its framework, or build an image for a container runtime.
2. Add the app on the admin page (Apps → Add app), or add an entry to the apps file ([configuration.md](configuration.md#app-entry)). Icons can go under the `cdf` folder; the app editor's icon picker uploads them.
3. Open `/<app_id>/`. No restart is needed.

Contract for each app type:

- **Streamlit (`"type": "streamlit"`, a Streamlit image, or `.sl`):**
  - Needs nothing special. Streamhub passes `--server.port`, `--server.address` and `--server.baseUrlPath=<id>`.
  - A `bash_file` must forward those flags (`streamlit run app.py "$@"`; see [streamhub/demo/streamlit/run.bash](../streamhub/demo/streamlit/run.bash)).
  - Readiness and health use `/_stcore/health`.
- **Python and other web servers (`"type": "python"`, a `web` image, or `.py`):**
  - Accept `--port` and `--app_id`, or read `STREAMHUB_PORT`.
  - Listen on `STREAMHUB_HOST`: `127.0.0.1` as a process, `0.0.0.0` in a container.
  - The app sees paths without the `/<id>` prefix. Use `X-Forwarded-Prefix` (Flask `ProxyFix(x_prefix=1)`) or `root_path=os.environ["STREAMHUB_BASE_PATH"]` (FastAPI) so it builds correct links. See the [demo apps](../streamhub/demo/).
  - Expose a cheap endpoint and set `health_path` to it, so hung apps are detected.
- **Any app:**
  - Read `X-Streamhub-User` and `X-Streamhub-Role` to know who is signed in. When the app could be reached without the hub, verify `X-Streamhub-Identity` instead: an HS256 JWT signed with `STREAMHUB_APP_KEY`, with `aud` = `STREAMHUB_APP_ID`, `iss` = `streamhub`, `sub` (user), `role` and `source`, valid for five minutes (`streamhub.auth.verify_identity`, or any JWT library).
  - Streamlit apps can get the user in `st.user` (`name`, `role`) with `streamlit_user_headers`; Streamlit's own `st.login` doesn't work behind the hub ([COMPAT-5](known-issues.md#compat-5)).
  - The app doesn't inherit the hub's environment. List the hub variables it needs in its `env_passthrough` (or `env-passthrough` for every app), or set them in its `env`.
  - Listen on `127.0.0.1` only (`STREAMHUB_HOST`): `bind-check` reports, or with `refuse` stops, an app listening on other addresses.
- **`.curl`:** the proxy forwards requests to `url` without the hub's cookies, and certificates are verified.

## Troubleshooting

| Symptom | Cause / action |
|---|---|
| Error page "The app stopped (exit code N)" | Read the log tail on the page, or the full log at `/out/<id>/`. Refresh to start the app again. |
| "The app did not answer on … within N s" | The app doesn't answer on its health path or port. Check `/out/<id>/` for an import error, a missing framework in the env, the app listening on a different port, or a wrong `health_path`; or raise `startup-timeout` for a slow app. |
| "… listens on 0.0.0.0:N, which bypasses the hub's access control" | The app binds every interface. Make it listen on `STREAMHUB_HOST` (`127.0.0.1`). |
| An app fails with a missing variable or credential it used to read | Apps no longer inherit the hub's environment: add the variable to its `env_passthrough`. |
| An app keeps restarting, with "failed N health checks" in the log | Its `health_path` returns errors or takes longer than 10 s. Fix the endpoint, or raise `health-failures`. |
| "Could not start …: Conda environment not found" | Check `virtual_environment`. Use an env folder path or `python_executable` when conda isn't on PATH (services, Docker). |
| "docker was not found" / "kubectl was not found" | Install the CLI for the hub's user, or set `STREAMHUB_DOCKER` / `STREAMHUB_KUBECTL`. |
| Kubernetes app stuck on the loading page | `/out/<id>/` shows the pod's waiting reason (for example `ImagePullBackOff`). The follower gives up after `startup-timeout`. |
| SSO login returns to the login page | The audit log names the reason: state mismatch (cookies blocked, or more than 10 minutes on the provider's page), issuer or audience mismatch, an invalid signature or unknown signing key, or no `group-mapping` rule matched (403). |
| The hub refuses to start: "oidc: the issuer must be https://" or "ldap: use ldaps://" | 2.2 requires TLS for SSO. Fix the URL; the `insecure-http` and `allow-plaintext` options are for development only. "PyJWT with cryptography" means the `oidc` extra is missing. |
| A new hub has no admin: the login page says so | Open the hub's address and enter the setup token the hub logged at startup (`Setup token: …`; in Docker, `docker logs <container>`). It is logged again, at most once a minute, when someone opens the login page. Or run `streamhub init <config folder>`, or set `STREAMHUB_ADMIN_PASSWORD`. |
| `/setup/` answers 404 | The hub already has an admin, or uses OIDC or LDAP (their admins come from `group-mapping`), or its users file is invalid. |
| Everyone is logged out; `/admin/` says the users file is not in use | The users file is invalid, unreadable or was deleted. Fix it on disk (`streamhub check` names the problem); meanwhile only the `STREAMHUB_ADMIN_PASSWORD` admin can log in. |
| An upload fails or the connection resets | The body is larger than `max-upload-mb`. |
| 403 on an app | The user has none of the app's boards. Add the board to the user, or put the app on a public board. |
| A user can no longer log in after upgrading to 2.1 | Their password is stored raw, and raw passwords are refused (the log names the user). Run `streamhub hash-passwords <config folder>`. |
| Too many logins rejected (429) | Wait 5 minutes. Behind a reverse proxy, set `behind-proxy: true` so clients are told apart by IP. A 503 "Too many logins in progress" means more than 8 password checks were queued for 10 s. |
| App behind a path prefix shows broken links | See the `.py` contract above (prefix handling). |
| With several instances, apps restart or sessions drop | The load balancer is not sticky, or the instances have different cookie secrets ([Multiple instances](#multiple-instances)). |
