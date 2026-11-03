# Endpoints

Every path the hub serves, and who may use it. Admin actions use a GET for a confirmation page and a POST to run; every POST needs the XSRF token (the `_xsrf` form field, or the `X-XSRFToken` header). While the hub drains before stopping, app launches and new WebSocket sessions get 503.

## Pages

| Path | Who | What |
|---|---|---|
| `/` | Anyone | Home page: favorites, boards, the apps of the board `""`, the latest news. Opens `/setup/` while the hub has no admin. |
| `/<board>.brd/` | Anyone (public boards), users with the board (protected boards) | The board's app cards, with search, filters and live status |
| `/news/` | Anyone | Every announcement |
| `/<app_id>/` | Users who can see one of the app's boards; admins | Starts the app on first use, shows the loading page, then proxies to it. A `url` app redirects (302). |
| `/out/<app_id>/` | Signed-in users who can open the app | The last 256 KB of the app's log |
| `/report/?id=<app_id>` | Anyone | Developer contacts and the issue form (5 reports per client per 10 minutes) |
| `/help.cmd/` | Anyone | The built-in user guide |
| `/login/`, `/logout/` | – | Sign in (local users, then LDAP); sign out (POST, revokes the session) |
| `/login/oidc/`, `/login/oidc/callback` | – | OpenID Connect sign-in (404 when `oidc` isn't set) |
| `/setup/[?token=…]` | Anyone with the setup token, only while there is no admin | First-run setup. 404 once an admin exists, with OIDC or LDAP configured, or with an invalid users file. |
| `/admin/` | Manager, admin | The [admin panel](../admin-guide/index.md); `/status.cmd/` redirects here |
| `/clear/` | Signed-in users (*stop all apps*: admin) | Clear memory |
| `/update/`, `/restart/`, `/exit/` | Admin | Reload the configuration; restart; stop the hub |

## API

| Path | Who | What |
|---|---|---|
| `GET /api/health` | Anyone | `{"status": "ok", "instance", "version"}` |
| `GET /api/apps` | Anyone | The apps the caller can open, with their state |
| `GET /api/apps/<id>/status` | Users who can open the app | `{"state", "ready", "error"}`; `error` says why a launch failed |
| `POST /api/apps/<id>/start`, `/stop`, `/restart` | Manager, admin | Control one app |
| `GET /api/apps/<id>/log`, `GET`/`POST /api/apps/<id>/affinity` | Manager, admin | Log tail; CPU affinity |
| `GET /api/admin/state`, `/api/admin/ports` | Manager, admin | Dashboard and Network data |
| `POST /api/admin/temp/purge` | Manager, admin | Empty the temp folder |
| `GET /api/` | Admin | Paths, settings summary, instance, running apps (PID, port, state, health, upstream, sessions, usage, log path) |
| `GET`/`POST /api/admin/files/<config\|apps\|users\|news>` | Admin | The file editors. GET returns a `version`; POST `{"text", "version"}` answers 409 if the file changed since. |
| `/api/admin/git/<status\|pull\|push>` | Admin | Git of the config folder |
| `GET`/`POST /api/admin/sessions` | Admin | List sessions; revoke with `{"id"}` or `{"user", "source"}` |
| `/api/admin/docker…` | Admin | Docker tab: state, container actions and logs, image pull and remove |
| `/api/admin/cdf…` | Admin | Static files tab: list, upload, rename, delete, new folder |
| `GET /api/admin/backup`, `POST /api/admin/restore` | Admin | Backup download; validated restore |
| `GET /api/admin/environments`, `/api/admin/path-check` | Admin | Conda environments; whether a path exists on the server |
| `GET /metrics` | Manager, admin, or the `STREAMHUB_METRICS_TOKEN` bearer token | [Prometheus metrics](../deployment/monitoring.md#prometheus-metrics) |

## Static files

| Path | What |
|---|---|
| `/cdf/<path>` | The static folder (`cdf`): icons, logos, CSS |
| `/temp/<path>` | The temp folder, emptied by every memory clean (except `readme_will_not_be_deleted.txt`) |
| `/static/<path>`, `/favicon.ico` | The hub's own stylesheet, logo, icons, and the bundled Bootstrap and Font Awesome, so pages work offline |

## Calling the API from a script

Use a session cookie of a manager or admin, or for `/metrics` the bearer token. For example, restarting an app with `requests`:

```python
import requests

hub = "https://apps.example.com"
s = requests.Session()
s.get(f"{hub}/login/")                               # sets the _xsrf cookie
xsrf = s.cookies["_xsrf"]
s.post(f"{hub}/login/", data={"username": "alice", "password": "…", "_xsrf": xsrf})
r = s.post(f"{hub}/api/apps/sales-forecast/restart", headers={"X-XSRFToken": xsrf})
print(r.status_code, r.json())
```
