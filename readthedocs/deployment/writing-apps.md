# Writing apps for Streamhub

Most apps need little or no change to run behind the hub. This page is the contract between the hub and an app. Working samples are in [`streamhub/demo/`](https://github.com/kavehbc/streamhub/tree/main/streamhub/demo), which is what `streamhub demo` runs.

## Deploying an app

1. Put the code on the server, in an environment that has its framework, or build an image for a container runtime.
2. Add the app on the admin page (**Apps → Add app**), or add an entry to the [apps file](../configuration/apps.md). Icons can go in the static folder; the app editor's icon picker uploads them.
3. Open `/<app_id>/`. No restart is needed.

## Streamlit apps

**Nothing to change.** The hub runs:

```text
<python> -m streamlit run <folder>/<file> --server.port=N --server.address=127.0.0.1
         --server.headless=true --server.baseUrlPath=<app_id> …
```

Streamlit then serves itself under `/<app_id>/`, and the hub checks `/<app_id>/_stcore/health` to know it is ready. If you use a launcher script (`bash_file`), forward the flags:

```bash
#!/usr/bin/env bash
cd "$(dirname "$0")"
exec streamlit run main.py "$@"
```

## Python web apps

The hub runs `<python> <folder>/<file> --port=N --app_id=<app_id>`, and the port is also in `STREAMHUB_PORT`. The app must:

1. **Listen on `STREAMHUB_HOST` and the given port.** That is `127.0.0.1` as a process, and `0.0.0.0` in a container.
2. **Handle its path prefix.** The hub serves the app under `/<app_id>/`, strips that prefix before forwarding, and sends `X-Forwarded-Prefix: /<app_id>`. Frameworks use it to build correct links and redirects.
3. **Offer a cheap health endpoint**, and set `health_path` to it, so the hub knows when the app is ready and can restart it when it hangs.

::::{tab-set}

:::{tab-item} Flask
```python
import os
import click
from flask import Flask, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
# Trust the hub's X-Forwarded-* headers, so url_for() builds /<app_id>/... links.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)


@app.route("/")
def index():
    return f'Hello! <a href="{url_for("health")}">health</a>'


@app.route("/health/")
def health():
    return "ok"


@click.command()
@click.option("--port", default=5000)
@click.option("--app_id", default="")
def run(port, app_id):
    app.run(host=os.environ.get("STREAMHUB_HOST", "127.0.0.1"), port=port)


if __name__ == "__main__":
    run()
```

Apps file entry: `"type": "python", "file": "main.py", "health_path": "health/"`.
:::

:::{tab-item} FastAPI
```python
import os
import click
import uvicorn
from fastapi import FastAPI

# The hub strips /<app_id>; root_path makes /docs and the OpenAPI URLs right.
app = FastAPI(root_path=os.environ.get("STREAMHUB_BASE_PATH", ""))


@app.get("/")
def root():
    return {"message": "Hello"}


@app.get("/health")
def health():
    return {"status": "ok"}


@click.command()
@click.option("--port", default=8000)
@click.option("--app_id", default="")
def run(port, app_id):
    uvicorn.run(app, host=os.environ.get("STREAMHUB_HOST", "127.0.0.1"), port=port)


if __name__ == "__main__":
    run()
```
:::

:::{tab-item} Dash
```python
import os
from dash import Dash, html

prefix = os.environ.get("STREAMHUB_BASE_PATH", "") + "/"
# Dash serves its assets under requests_pathname_prefix; routes arrive without the prefix.
app = Dash(__name__, requests_pathname_prefix=prefix, routes_pathname_prefix="/")
app.layout = html.Div("Hello from Dash")

if __name__ == "__main__":
    app.run(host=os.environ.get("STREAMHUB_HOST", "127.0.0.1"), port=int(os.environ["STREAMHUB_PORT"]))
```
:::

:::{tab-item} Any command
Use `command` for servers that don't take `--port`, such as gunicorn or uvicorn on the command line:

```json
{
  "app_id": "kpis",
  "type": "python",
  "folder": "/srv/apps/kpis",
  "command": ["{python}", "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "{port}",
              "--root-path", "{base_path}"],
  "health_path": "health"
}
```
:::
::::

## Environment variables

Every app receives:

| Variable | Value |
|---|---|
| `STREAMHUB_PORT` | The port to listen on |
| `STREAMHUB_HOST` | The address to listen on: `127.0.0.1`, or `0.0.0.0` in a container |
| `STREAMHUB_APP_ID` | The app's ID |
| `STREAMHUB_BASE_PATH` | `/<app_id>` |
| `STREAMHUB_URL` | The hub's loopback address (not reachable from a container) |
| `STREAMHUB_APP_KEY` | This app's own key, to verify `X-Streamhub-Identity` |
| `PYTHONUNBUFFERED`, `PYTHONIOENCODING` | `1` and `utf-8`, so the log shows output at once |

Apps **don't inherit** the hub's environment. List the hub variables an app needs in its `env_passthrough` (for example `["AWS_*"]`), or set values in its `env`. See [Environment variables](../configuration/environment.md#what-apps-receive).

## Knowing who is signed in

The hub adds these headers to every request it proxies for a signed-in user. It discards any `X-Streamhub-*` header the browser sent.

| Header | Value |
|---|---|
| `X-Streamhub-User` | User name |
| `X-Streamhub-Role` | `admin`, `manager`, `user` or `guest` |
| `X-Streamhub-Identity` | A short-lived HS256 JWT, signed for this app only: `iss` = `streamhub`, `aud` = the app ID, `sub` (user), `role`, `source`, valid for five minutes |

In Streamlit, read them with `st.context.headers`:

```python
import streamlit as st

user = st.context.headers.get("X-Streamhub-User")
st.caption(f"Signed in as {user}" if user else "Not signed in")
```

With `"streamlit_user_headers": true` (or the `streamlit-user-headers` setting) and Streamlit 1.66 or later, `st.user.name` and `st.user.role` are filled in too. Streamlit's own `st.login` doesn't work behind the hub.

**When the app could be reached without the hub**, trust the signed identity rather than the plain headers:

```python
import os
import jwt  # PyJWT

claims = jwt.decode(headers["X-Streamhub-Identity"], os.environ["STREAMHUB_APP_KEY"], algorithms=["HS256"],
                    audience=os.environ["STREAMHUB_APP_ID"], issuer="streamhub")
user, role = claims["sub"], claims["role"]
```

`streamhub.auth.verify_identity` does the same check, for apps that run in the hub's environment.

## Rules of the road

- **Listen on `127.0.0.1` only** (`STREAMHUB_HOST`). An app on `0.0.0.0` can be reached around the hub's login. `bind-check` reports it, or with `refuse` stops it.
- Use the hub's cookies? You can't: the hub removes its cookies (`user`, `_xsrf`, `oidc`, `streamhub_instance`) before forwarding. Apps manage their own sessions and CSRF.
- Every app is served from the hub's origin. A page of one app can send requests to another app with the user's cookies, so put untrusted apps on their own hub.
- Large files for download: write them to the hub's `temp` folder with a unique name, and link to `/temp/<name>`. The folder is emptied by every memory clean.
- Uploads are streamed to the app, up to `max-upload-mb` (1 GB by default).

## Proxied external sites

A `curl` app proxies an external URL under `/<app_id>/`, behind the hub's login. The proxy forwards requests without the hub's cookies, verifies the target's certificate, and rewrites redirects so they stay under the prefix.
