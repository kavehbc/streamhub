# Streamhub

Streamhub runs many Streamlit and Python web apps (Flask, Dash, FastAPI, …) for many users, each app in its own
environment, and serves them all on **one port** at `http://<host>:<port>/<app_id>/`. Apps start when first opened,
stop when idle or on a schedule, and are listed on boards that can require a login. Everything is configured with
JSON files. Streamhub runs on **Linux and Windows**, and in Docker. Apps can also run as Docker containers or
Kubernetes pods.

The full documentation, with screenshots (getting started, user and admin guides, configuration, deployment), is the
Read the Docs site built from [readthedocs/](readthedocs/README.md) (`make docs`). Maintainer documentation
(architecture, every config key, operations, known issues) is in [docs/](docs/README.md).

## Quick start

```bash
pip install "streamhub[tools,examples] @ git+https://github.com/kavehbc/streamhub"   # or, in a clone: pip install -e ".[tools,examples]"
streamhub demo          # the demo apps on http://localhost:8500, login admin / admin
```

**Your own hub**, in three steps:

1. `streamhub init my-hub` asks for a site title, a port and the admin password, and writes a starter config
   folder.
2. `streamhub run my-hub`, then open http://localhost:8500 and sign in.
3. On the **Admin** page (account menu → Admin), add your apps, users and settings. Every field has a hint,
   and lists offer their choices. Nothing needs editing by hand.

You can also skip `init`, whether you run Streamhub directly or in Docker: on a hub without an admin,
http://localhost:8500 opens the **setup page**. Enter the admin name and password, plus the **setup token**
that the hub printed when it started (`Setup token: …`). The page tells you where to find it; in Docker, it
shows the exact `docker logs` command. The token makes sure only you can create the admin.

**With Docker:**

```bash
docker run -p 8500:8500 -v streamhub-config:/config kavehbc/streamhub   # then open http://localhost:8500: it guides you through setup
docker run -p 8500:8500 kavehbc/streamhub streamhub demo                # the demo
docker compose up -d --build                                            # or: make docker-up (config in ./config)
```

In a clone, `make install` then `make demo` work too (Windows: `make.bat install`, `make.bat demo`); `make help`
lists the other tasks.

## Running

    streamhub demo [--port N]                                  # the bundled demo, login admin / admin
    streamhub init [<folder>] [--yes] [--admin-password …]     # a starter config folder with its admin
    streamhub run [--port N] [--ssl-port N] [--debug] [--supervised] [<config folder | streamhub.json>]
    streamhub check <config folder>   # validate the configuration without starting anything
    streamhub passwd        # hash a password for the users file
    streamhub version

The config folder defaults to `STREAMHUB_CONFIG`, else the current folder. A folder without `streamhub.json`
runs on the defaults, and saving the Settings on the admin page creates the file. `python -m streamhub …` and
`python main.py …` do the same.
Streamhub also comes as a single executable that needs no Python install
([how to build it](docs/operations.md#build)). `make start` runs the `config/` folder and logs to
`logs/streamhub.log`. `--debug` prints debug logs and disables Slack.
`--supervised` is for service managers (systemd, NSSM, Docker): **Restart** then exits with code 3 and the
manager starts Streamhub again.

## Using Streamhub

- **The top menu**, on every page, leads to Home, News and each board (a lock marks boards that need a login).
  On a phone it folds into the ☰ button.
- **Your account menu** opens when you click your avatar: the Admin panel sections (Dashboard and Network for
  managers and admins; Apps and boards, Users, News, Settings, Docker, Static files, Sessions and JSON files for
  admins), Clear memory, Reload configuration, Restart hub and
  Stop hub (admins), and Log out. These are built in: the apps file doesn't list them.
- **Home** shows your favorites, the boards you can open and the latest news; **News** lists every announcement.
- **Boards** list apps as cards. A colored dot and label show whether an app is running (green), starting (amber),
  unhealthy (red) or idle (gray). **Open** starts the app if needed.
- **Search** filters the cards of a board by name, ID or description; **Running** and **Favorites** narrow them.
- **Favorites**: click the star on a card. Favorites come first on their boards and appear on the home page.
  They are stored in your browser.
- **Dark mode** follows your system setting; the ◐ button in the menu switches it.
- **Sign in** with a user name and password, or with your company account when single sign-on is set up.
- **Report an issue** with the flag on a card: describe the problem and Streamhub sends it to the app's
  developers.

## Configuration in brief

A config folder holds four JSON files. The admin page edits all of them; the full reference is in
[docs/configuration.md](docs/configuration.md).

- **`streamhub.json`**: port, schedule and time zone of the daily memory clean, branding, timeouts, health
  checks, notifications (Slack, Teams, email), single sign-on (OpenID Connect, LDAP). Every key is optional.
- **`streamhub-apps.json`**: the first element lists the **boards** (`*.brd`; `"auth": true` requires a login),
  and every following element is an **app**.
- **`streamhub-users.json`**: users with a role (`admin`, `manager`, `user`, `guest`) and the boards they can
  open. Passwords are stored as hashes only: create one with `streamhub passwd`, or convert a file with
  `streamhub hash-passwords <config folder>`.
- **`streamhub-news.json`**: announcements on the landing page.

Keep secrets out of files: use `STREAMHUB_SLACK_HOOK`, `STREAMHUB_COOKIE_SECRET`, `STREAMHUB_ADMIN_PASSWORD`,
`STREAMHUB_SMTP_PASSWORD`, `STREAMHUB_OIDC_CLIENT_SECRET`, `STREAMHUB_LDAP_BIND_PASSWORD` and
`STREAMHUB_METRICS_TOKEN`. Apps don't see them: an app receives only the hub variables listed in its
`env_passthrough`.

### App types

`"type"` decides what Streamhub does with an app, and `app_id` is any name: the app opens at `/<app_id>/`.

| Type | What it is |
|---|---|
| `streamlit` | Streamlit app (`file` + `folder`) |
| `python` | Any Python web server (Flask, Dash, FastAPI, …) |
| `docker` | An `image` run with Docker: a Streamlit app (`"serves": "streamlit"`) or any web server (`web`) |
| `kubernetes` | The same, as a Kubernetes pod |
| `url` | Redirect to `url` |
| `curl` | Proxy to `url`, which stays hidden behind Streamhub |
| `page` | Link to the hub page `/<app_id>/`. The admin pages need no entry: they are in the account menu. |

Apps files from before 2.2 have no `type`: the `app_id` suffix decides (`.sl`, `.py`, `.url`, `.curl`, and
`.cmd` for the built-in `help.cmd`), and that still works.

Example:

```json
{
	"board": ["sales.brd"],
	"app_id": "forecast",
	"type": "streamlit",
	"app_name": "Sales forecast",
	"description": "Weekly forecast by region",
	"file": "forecast.py",
	"folder": "/srv/apps/sales",
	"virtual_environment": "forecasting",
	"auto_shutdown": true,
	"auto_start": false,
	"restart": "on-failure",
	"icon": "/cdf/icons/seasons-3.png",
	"developer": [{"name": "Jane Doe", "email": "jane@example.com"}],
	"children": []
}
```

`virtual_environment` is a conda env name or an environment folder. Other ways to launch an app are
`python_executable`, a `command` list, or a launcher script in `bash_file` (`.sh`, `.bat`, `.cmd` or `.ps1`).
To run it from a container image instead, use `"type": "docker"` (or `"kubernetes"`) with `"image"` and `"serves"`;
`file` is then a path inside the image, and `volumes` mounts folders. Admins can also pull images and add an app on
one from the Docker tab.
`"health_path"` names an endpoint that Streamhub polls to detect a hung app and restart it.

## Writing apps for Streamhub

- **Streamlit (`.sl`)**: nothing to change.
- **Python (`.py`)**: Streamhub runs `python <file> --port=<port> --app_id=<app_id>` (the port is also in
  `STREAMHUB_PORT`). Listen on `STREAMHUB_HOST` (`127.0.0.1`, or `0.0.0.0` in a container). Give the app a cheap
  health endpoint and set `health_path`. The app is served under `/<app_id>/` with that prefix removed, and
  `X-Forwarded-Prefix` is set:

  ```python
  # Flask
  app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
  # FastAPI
  app = FastAPI(root_path=os.environ.get("STREAMHUB_BASE_PATH", ""))
  ```

- The signed-in user is sent to every app as `X-Streamhub-User` / `X-Streamhub-Role` (Streamlit:
  `st.context.headers`, or `st.user` with `"streamlit_user_headers": true` on a recent Streamlit). To be sure a
  request came through Streamhub, verify `X-Streamhub-Identity`, a short-lived token signed for your app only:

  ```python
  import jwt, os  # PyJWT
  claims = jwt.decode(headers["X-Streamhub-Identity"], os.environ["STREAMHUB_APP_KEY"], algorithms=["HS256"],
                      audience=os.environ["STREAMHUB_APP_ID"], issuer="streamhub")
  user, role = claims["sub"], claims["role"]
  ```

- Apps don't inherit Streamhub's environment variables. List the ones an app needs in its `env_passthrough`
  (for example `["AWS_*"]`), or set them in `env`.
- Listen on `127.0.0.1` (`STREAMHUB_HOST`) only; Streamhub warns about apps reachable on other addresses.

Working samples: [streamhub/demo/](streamhub/demo/) (what `streamhub demo` runs).

## Internal pages

| Path | Purpose |
|---|---|
| `/help.cmd/` | This guide |
| `/news/` | Every announcement |
| `/admin/` | Admin panel (manager or admin, also in the account menu): server load, apps with health, memory and CPU, start, stop or restart, live logs, usage today, CPU affinity, listening ports. Admins also edit apps and boards, users, news and settings in forms (a settings save applies at once), manage Docker containers and images, upload and organize the files of `/cdf/`, and get sessions, the JSON editor and git. `/status.cmd/` redirects here. |
| `/out/<app_id>/` | The app's output log |
| `/clear/` | Stop apps with `auto_shutdown` (admins: all apps) and empty the temp folder |
| `/update/` | Reload `streamhub.json` (admin) |
| `/restart/`, `/exit/` | Restart or stop Streamhub (admin) |
| `/report/?id=<app_id>` | Report an issue with an app, or contact its developers |
| `/api/` | Paths and running apps as JSON (admin). Also `/api/health` and `/api/apps` (the apps you can open). |
| `/metrics` | Prometheus metrics (manager, or `STREAMHUB_METRICS_TOKEN`) |
| `/login/`, `/logout/` | Session (`/login/oidc/` for single sign-on) |
| `/setup/` | While the hub has no admin (`/` opens it): with the link the hub printed at startup, creates the first admin |

## Static files

`/cdf/<path>` serves the static folder (icons, CSS). `/temp/<path>` serves a public temporary folder (path in
`/api/` as `cdf_temp`) that is **emptied on every memory clean**. Use it for large downloads, and use unique file names.

## Troubleshooting

- **"The app stopped"**: the page shows the end of the app's log. Refresh to start the app again.
- **"The app did not answer … within N s"**: open `/out/<app_id>/` for errors (a missing package, a wrong
  environment, a wrong port).
- **The report form says your report could not be delivered**: try again later, or write to the developers
  directly.
- **403 on an app**: your user has none of the app's boards.
- **An app restarts by itself**: it failed its health checks; the admin page shows its log.
- **Nobody can sign in on a new hub**: the login page says so when there is no admin yet. Open the hub's
  address: the setup page asks for the setup token from the hub's console (`docker logs <container>` in
  Docker). Or run `streamhub init <config folder>`.

More: [docs/operations.md](docs/operations.md#troubleshooting).

## Reference
This is an extended work based on [Streamlit-launchpad](https://github.com/ideonate/streamlit-launchpad).

___
## Changelog

### Version 2.3
*Update Date: Nov. 2026*
- Releases from CI: CI runs on pushes and pull requests to `main` or `master` only. A push that passes and
  carries a new version publishes the GitHub release `v<version>` with the wheel, the sdist and the Docker image
  tarball, and pushes the image to `ghcr.io/kavehbc/streamhub:<version>` and `:latest`
- Documentation site for Read the Docs in `readthedocs/` (Sphinx, MyST, Furo): installation, quick start, a
  tutorial, user and admin guides with screenshots, the configuration reference, deployment guides (Docker,
  Kubernetes, systemd, Windows, HTTPS, several instances, monitoring, security), the CLI (generated from the code),
  endpoints and troubleshooting. `make docs` builds it; `readthedocs/_tools/screenshots.py` retakes the screenshots
  from a sample hub
- Getting started without editing files: `streamhub init` writes a starter config folder with its admin account,
  and `streamhub demo` runs the demo apps, which now ship inside the package (moved from `examples/` to
  `streamhub/demo/`), from a plain `pip install`
- First-run setup page: on a hub without an admin, the start page opens `/setup/`, a single form that creates the
  admin in the browser and names the site. It asks for the one-time setup token the hub printed (or opens with the
  printed link), and says where to find it (`docker logs <container>` in Docker). The login page says so too. `STREAMHUB_ADMIN_PASSWORD` and the users file work
  as before
- Docker: the image no longer defaults the admin password to `admin`. It runs `/config` (a volume) and opens
  on the setup page; `docker run … kavehbc/streamhub streamhub demo` runs the demo. Compose runs `./config`
- `streamhub run` reads its folder from `STREAMHUB_CONFIG`, and explains what to do when the folder is missing
- Admin page:
  - The Settings tab, the backup restore and the setup page create `streamhub.json` when the hub has none,
    instead of refusing
  - OpenID Connect, LDAP, mail server, notification channels, group mapping and an app's Kubernetes options are
    forms instead of JSON (with **Edit as JSON** for anything else)
  - Lists offer their choices with descriptions: roles, app types, layouts, bind check, restart policy
  - Time zones, Python environments (the server's conda envs) and Docker images are suggested as you type
  - Logo and app icons have a picker of the static folder's images, with upload
  - Folders and files are checked on the server as you type
  - Settings set by an environment variable are shown read-only
  - Every setting and section has a hint
  - The Users tab can generate a password
  - The dashboard shows a **Getting started** checklist
  - The sidebar layout is renamed from `main_2.html` to `main_side.html` (the old name still works, with a
    warning)
  - Boards and apps can be reordered by drag and drop on the Apps tab (or with the keyboard): that is the
    order of the menu, the home page and the board cards
- The time zone is checked when the config is loaded or saved, instead of failing at the first scheduled clean
- The Slack start message uses a standard emoji and no longer appends the port to `server-url` behind a proxy
- The repository no longer ships a deployment config: `config/` is yours (git-ignored), and the bundled
  company logos and product photos are removed. The PyInstaller spec is tracked again, so `make exe` works on a
  fresh clone
- Kubernetes manifest: matching image tag, and a writable `/config` (copied from the ConfigMap at start)

### Version 2.2
*Update Date: Oct. 2026*
- Security: apps no longer inherit the hub's environment (secrets included); opt in per variable with
  `env-passthrough` / `env_passthrough`
- Security: OpenID Connect requires HTTPS for the issuer and its endpoints, checks that discovery names the
  configured issuer, and verifies ID-token signatures against the provider's keys (new `oidc` extra, PyJWT);
  `insecure-http` for development
- Security: LDAP verifies certificates (`ca-file`), never sends credentials after a failed STARTTLS, and requires
  TLS unless `allow-plaintext`
- Security: concurrent login attempts count toward the throttle at once, and at most 8 password checks run together
- Security: an invalid, unreadable or deleted users file grants nothing (only the `STREAMHUB_ADMIN_PASSWORD` admin
  works) and is flagged on `/admin/`
- Apps can verify who is signed in with `X-Streamhub-Identity` (a JWT signed with their own `STREAMHUB_APP_KEY`),
  and Streamlit apps can get `st.user` (`streamlit-user-headers`)
- Revocable sessions: `/admin/` lists sessions and revokes one, or all of a user's, on every instance within
  5 seconds; logout revokes the session; `sso-session-minutes` makes SSO users sign in again periodically
- `streamhub check <config>` validates a config folder without starting it; the admin editor uses the same checks,
  refuses saves over newer changes (409) and writes files atomically; git commits only the hub's own files
- `/metrics` for Prometheus (`STREAMHUB_METRICS_TOKEN`); usage counters survive restarts (SQLite,
  `usage-retention-days`)
- Graceful stop: the hub waits up to `drain-timeout` for requests and sessions before stopping apps
- `bind-check` reports (or with `refuse` stops) apps listening beyond 127.0.0.1
- Uploads are streamed to apps instead of buffered (`max-upload-mb`); hub pages accept 16 MB
- Bootstrap and Font Awesome are bundled: pages look right without internet access
- Fix: concurrent requests could launch an app twice
- Fix: an app that never answered was reported ready after `startup-timeout`; it now fails with a clear message
- Fix: the report form claimed success when nothing was delivered; it now says what happened
- Fix: apps of a crashed hub kept running (Windows: they now die with it; elsewhere the next start stops them)
- Fix: `/out/<app_id>/` found no log for a stopped app whose ID has characters outside letters, digits, `.`, `_`, `-`
- CI tests the minimum dependency versions and audits dependencies (`pip-audit`)
- The Docker image is named `kavehbc/streamhub`; `docker-build` tags it with the version and `latest`
- Account menu: clicking the avatar opens a dropdown with the admin panel sections and the hub actions your role
  allows (Clear memory, Reload configuration, Restart hub, Stop hub) and Log out. It replaces the Admin panel link
  in the top menu and the action buttons on `/admin/`, and the bundled apps files no longer list `admin`, `clear`,
  `restart`, `exit` or an Admin board. `main_nomenu.html` shows it too
- The logo's wordmark reads `streamhub` in lowercase black (white in the dark theme)
- Admin editors: Apps (with boards), Users, News and Settings tabs edit the hub's JSON files in forms, next to the
  raw JSON editor (now the JSON files tab). They keep keys they don't show and save through the same validation.
  Saving `streamhub.json` from the admin page applies it at once, and names the keys that need a restart, with a
  Restart now button
- Fix: with `--port` or `--ssl-port`, Reload configuration reported the port as needing a restart; command-line
  ports now survive reloads
- Docker apps from the admin page: the app editor shows the fields of the chosen runtime (process, Docker image,
  Kubernetes pod) and offers local images
- Docker tab (admins): the daemon in use, containers (start, stop, restart, logs, remove) and images (pull, remove,
  New app from an image). `docker-socket` picks the daemon (default `/var/run/docker.sock`); `docker-network` lets
  a hub that runs in a container reach its docker apps. Compose now mounts the host's Docker socket and runs the
  hub on the `streamhub-apps` network, and the image includes the `docker` client
- Static files tab (admins): browse the `cdf` folder, upload (with drag and drop), create folders, rename or move,
  and delete files
- App types: a `"type"` key (`streamlit`, `python`, `docker`, `kubernetes`, `url`, `curl`, `page`) says what an app
  is, so app IDs need no suffix; files without it keep working. Docker images say what they run with `serves`
  (`streamlit` or `web`; a web image without `file` or `command` runs its own command) and mount `volumes`. App IDs
  that are hub paths (`admin`, `api`, …) are refused, except for hub pages
- App editor: a Type drop-down that shows each type's fields (Docker: image, container port, environment variables,
  volumes, `docker run` options), and a check, as you type, that the app ID is free
- Backup tab (admins): download the config, apps, users and news files as one file, and restore the chosen ones from
  it, all validated first and with the current files kept in `<config>/backups/`
- The admin page's sections are in a menu at the left, collapsible to icons
- Dashboard: Purge empties the temp folder
- New UI: a Streamhub logo and favicons; one responsive top menu on every page, including the admin panel (or a
  sidebar with `main_2.html`); a home page with favorites, boards and the latest news; a `/news/` page; app cards
  with status labels and All / Running / Favorites filters; redesigned login, loading, error and report pages;
  light and dark themes. The landing page now also lists the apps of the board `""`
- Admin panel redesign: tabs (Dashboard, Sessions, Configuration, Network), live CPU and memory meters, a
  filterable app table that becomes cards on phones, log and CPU-affinity dialogs with a following log, and a JSON
  editor with validation, formatting and Ctrl+S
- Customized templates that link `/cdf/css/apps.css` keep their old look; the bundled templates use
  `/static/streamhub.css`
- Docker and Compose log in as `admin` / `admin` when `STREAMHUB_ADMIN_PASSWORD` isn't set (like `make demo`); the
  hub warns, and `/admin/` shows a banner, while that default is in use

### Version 2.1
*Update Date: Oct. 2026*
- Single sign-on: OpenID Connect (authorization code + PKCE) and LDAP (`[ldap]` extra), with groups mapped to roles
  and boards; SSO accounts can also be listed in the users file
- Native admin page `/admin/` replaces the `status.cmd` Streamlit dashboard (which now redirects there):
  start, stop and restart, logs, usage chart, CPU affinity, ports, JSON editor and git; `/api/apps/<id>/restart`
- Landing page: search, live running/starting/unhealthy/stopped badges, favorites, dark mode; `/api/apps`
- Notifications to Slack, Microsoft Teams and email (`notifiers`, `smtp`), filtered by event; the
  "Report an issue" form now sends reports to the `report` channels and emails the developers
- App runtimes: `"runtime": "docker"` and `"kubernetes"` (Pod + Service, hub inside the cluster); leftovers are
  removed at startup; Kubernetes manifests and an image with kubectl in `deploy/kubernetes/`
- Health paths (`health_path`, `_stcore/health` by default for Streamlit) for readiness and periodic checks; hung
  apps are stopped and restarted under their `restart` policy (`health-interval`, `health-failures`)
- Several hub instances behind a sticky load balancer (`instance-id`, `streamhub_instance` cookie, per-instance
  logs and temp); nginx and HAProxy examples in `deploy/multi-instance/`
- Apps receive `STREAMHUB_HOST`; the examples listen on it, and the Flask example has a health endpoint
- Repository layout: the config files moved from the root to `config/` (mounted at `/config` by Compose; set
  `STREAMHUB_CONFIG=/config` in `.env` to run it); `scripts/` is replaced by a `Makefile` and `make.bat`
- Command line like Streamlit's: `streamhub run <config>`, `streamhub passwd`, `streamhub version`
  (`streamhub <config>` and `streamhub-passwd` still work)
- Builds: a wheel for `pip`/`pipx install` (`make dist`) and a single-file executable (`make exe`, PyInstaller)
- Passwords are hashes only: raw passwords in the users file are refused, `streamhub hash-passwords` converts
  them, the admin editor masks passwords and hashes new ones, and `STREAMHUB_ADMIN_PASSWORD` is hashed in memory
- Password checks and hashing run off the event loop, so a login no longer pauses the hub
- The version is set in one place (`streamhub/__init__.py`); `streamhub --version` and the package metadata agree
- Fix: `--debug` no longer takes the config folder as its value (`streamhub --debug <config>` failed)
- Fix: certificates of `.curl` targets are now verified
- Verified with Streamlit 1.66 (its server now runs on Starlette instead of Tornado)

### Version 2.0
*Update Date: Oct. 2026*
- Runs on Windows and Linux; Docker image and Compose file; systemd unit and NSSM instructions
- Installable package (`pyproject.toml`) with `streamhub` and `streamhub-passwd` commands; Python 3.11+, Tornado 6, current Streamlit
- Rewritten proxy: all HTTP methods, query strings, redirects, streamed responses, WebSocket subprotocols
- Access control on the apps themselves (not only boards), hashed passwords, login throttling, XSRF protection
- No more master password, hard-coded cookie secret or committed keys; secrets from environment variables
- Per-app log files (`/out/<app_id>/` for every app), readiness detection, restart policy, idle shutdown
- New app keys: `command`, `python_executable`, `activate`, `env`, `args`, `restart`, `idle_timeout`
- New config keys: `timezone`, `log-folder`, `port-range`, `idle-timeout`, branding, timeouts; every key optional
- `status.cmd` rewritten (no shell commands; JSON validated before saving); `/api/apps/<id>/start|stop`
- Tests and CI on Linux and Windows

### Version 1.5
*Update Date: Feb. 2021*
- Restructuring the whole source code
- Reformatting input commands 
- Renaming `clear.cmd` to `clear` and `exit.cmd` to `exit`
- Supporting app auto shutdown feature
- Supporting all python apps with `.py` extension (e.g. Flask, FastAPI, etc.)
- Supporting auto start apps
- Optional rerunning apps after memory cleaning
- Supporting App IDs with `.curl` extension
- Truncating `Transfer-Encoding: chunked`
- Tracking and reporting apps usage
- Supporting SSL (HTTPS Server) beta
- Redesigning apps listing UI (Modern responsive UI/UX)
- Providing sample apps in the `examples` folder
- Bug fixes and improvements


### Version 1.0
*Update Date: Oct. 2020*
- Adding Display parameter to the json file
- Supporting dynamic multiple boards (`.brd`)
- Responsive landing page
- Supporting user authentication to access restricted boards
- Checking the port availability before assigning
- Static file handling (permanent and temporary)
- Cleaning temporary static files
- Supporting announcements in homepage
- Reporting issues to the developers (beta) via `/report/?id=<app_id>`
- Assigning Apps to multiple boards
- Adding confirmation page to `clear.cmd` and `exit.cmd`
- Adding `/api/` to expose internal settings
- Adding `/update/` to apply changes to the config file
- Adding `/out/<app_id>` to print standard outputs
- Supporting App IDs with `.url` extension
- Adding `restart.cmd` command
- Deprecating `Proxy Map` dumping in favour of `/api/`
- Bug fixes and improvements


### Version 0.5 beta
*Update Date: Apr. 2020*
- JSON support for apps
- Interruption handling
- Internal commands
- Memory management
- Bash scripting support
- Virtual Environment support
- Server monitoring dashboard
- Child application support
- Slack channel monitoring
- User authentication in Status Monitoring app
- Customized landing page
- Dumping `Proxy Map` into a text file
- Port exceptions
- Github integration in monitoring dashboard
- Auto scheduling memory cleaning
  
