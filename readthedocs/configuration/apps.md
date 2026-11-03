# Apps file: `streamhub-apps.json`

A JSON array. **Element 0 defines the boards**, and every following element is an app. The file is re-read when it changes. If an edit makes it invalid (bad JSON, a duplicate `app_id`, a value of the wrong type), the hub logs the error, shows it on `/admin/`, and keeps the last good version.

## Boards

```json
{ "boards": [
    { "name": "demo.brd",  "label": "Demo",  "auth": false },
    { "name": "sales.brd", "label": "Sales", "auth": true }
] }
```

| Key | Description |
|---|---|
| `name` | Unique ID ending in `.brd`; the board's page is `/<name>/` |
| `label` | Menu text (defaults to `name`) |
| `auth` | `true`: only users whose `boards` include it (or `*`) can see the board **and open its apps** |

The landing page is the board `""`: apps that list `""` appear on the home page and are public.

## App types

`type` says what the hub does with an app. `app_id` is any name: the app opens at `/<app_id>/`.

| `type` | What it is |
|---|---|
| `streamlit` | A Streamlit script (`folder` + `file`), run as a process |
| `python` | Any Python web server (Flask, Dash, FastAPI…), run as a process |
| `docker` | A container run from `image`: a Streamlit app (`"serves": "streamlit"`) or any web server (`"serves": "web"`) |
| `kubernetes` | The same, as a Kubernetes pod |
| `url` | A card that redirects to `url` |
| `curl` | A proxy to `url`, which stays hidden behind the hub (and its login) |
| `page` | A card that opens the hub page `/<app_id>/` |

**Apps files from before 2.2** have no `type`: the `app_id` suffix decides. `.sl` means Streamlit, `.py` Python, and `.url`, `.curl` and `.cmd` (the built-in `help.cmd`) work the same way; no suffix means a hub page. These files keep working.

App IDs that are hub paths (`admin`, `api`, `cdf`, `clear`, `exit`, `login`, `logout`, `metrics`, `news`, `out`, `report`, `restart`, `setup`, `static`, `temp`, `update`, … and names ending in `.brd`) are refused, except for a `page`.

## Examples

::::{tab-set}

:::{tab-item} Streamlit
```json
{
  "board": ["sales.brd"],
  "app_id": "forecast",
  "type": "streamlit",
  "app_name": "Sales forecast",
  "description": "Weekly forecast by region",
  "folder": "/srv/apps/sales",
  "file": "forecast.py",
  "virtual_environment": "forecasting",
  "restart": "on-failure",
  "icon": "/cdf/icons/forecast.png",
  "developer": [{"name": "Jane Doe", "email": "jane@example.com"}]
}
```
:::

:::{tab-item} Flask / FastAPI
```json
{
  "board": ["ops.brd"],
  "app_id": "inventory",
  "type": "python",
  "app_name": "Inventory API",
  "folder": "C:/apps/inventory",
  "file": "main.py",
  "python_executable": "C:/apps/inventory/.venv/Scripts/python.exe",
  "health_path": "health/",
  "env_passthrough": ["DATABASE_URL"],
  "idle_timeout": 30
}
```
:::

:::{tab-item} Custom command
```json
{
  "board": ["ops.brd"],
  "app_id": "dash-kpis",
  "type": "python",
  "folder": "/srv/apps/kpis",
  "command": ["{python}", "-m", "gunicorn", "app:server", "-b", "127.0.0.1:{port}"],
  "env": {"SCRIPT_NAME": "/dash-kpis"},
  "health_path": ""
}
```
:::

:::{tab-item} Docker
```json
{
  "board": ["sales.brd"],
  "app_id": "reports",
  "type": "docker",
  "image": "ghcr.io/acme/reports:1.4",
  "serves": "web",
  "container_port": 8000,
  "env": {"REPORTS_THEME": "dark"},
  "volumes": ["reports-data:/data", "/srv/shared:/shared:ro"],
  "runtime_args": ["--memory=2g", "--cpus=1"],
  "health_path": "healthz"
}
```
:::

:::{tab-item} Link and proxy
```json
[
  { "board": [""], "app_id": "wiki", "type": "url",
    "app_name": "Team wiki", "url": "https://wiki.example.com" },
  { "board": ["ops.brd"], "app_id": "grafana", "type": "curl",
    "app_name": "Grafana", "url": "https://grafana.internal.example.com" }
]
```
:::

:::{tab-item} Parent and child
```json
{
  "board": ["demo.brd"],
  "app_id": "flask-demo",
  "type": "python",
  "folder": "../flask",
  "file": "main.py",
  "children": [
    { "board": ["demo.brd"], "app_id": "fastapi-demo", "type": "python",
      "folder": "../fastapi", "file": "main.py" }
  ]
}
```
:::
::::

```{note}
The placeholders `{python}`, `{port}`, `{app_id}` and `{base_path}` (the app's prefix, `/<app_id>`) expand in `command` only. Every app also receives its prefix as the `STREAMHUB_BASE_PATH` environment variable. The Custom command example passes the prefix to a WSGI server as `SCRIPT_NAME`, so the app builds links under it.
```

## Keys of an app

### Card and access

| Key | Applies to | Default | Description |
|---|---|---|---|
| `app_id` | all | required | Unique ID; the app's URL is `/<app_id>/` |
| `type` | all | from the suffix | See [App types](#app-types) |
| `board` | all | `[]` | Boards the app is listed on, which also decide who can open it |
| `app_name` | all | `app_id` | Card title |
| `description` | all | `""` | Card text |
| `icon` | all | `""` | Icon URL, for example `/cdf/icons/monitor.png` |
| `display` | all | `show` | `show`, `disabled` (listed, can't be opened) or `hidden` (not listed; still opens by URL, subject to its boards) |
| `developer` | all | `[]` | `[{"name", "email"}]`, for *Report an issue* |
| `children` | parents | `[]` | Nested apps with the same keys, one level deep |
| `url` | `url`, `curl` | – | Target URL |

### Launching a process app

These keys apply to `streamlit` and `python` apps.

| Key | Default | Description |
|---|---|---|
| `folder` | – | The app's folder, also its working directory. Relative to the config folder. |
| `file` | – | Entry script, relative to `folder` |
| `virtual_environment` | `virtual-environment` setting | A conda env name or an environment folder. Its interpreter is called directly, without activation. |
| `python_executable` | – | Explicit interpreter path; overrides `virtual_environment` |
| `activate` | `false` | Launch through `conda run -n <env>`, for envs that need activation (some Windows DLLs) |
| `command` | – | Full argument list with `{python}`, `{port}`, `{app_id}` and `{base_path}` placeholders. Replaces `file`. |
| `bash_file` | – | Launcher script, run by its extension: `.sh` or `.bash` with bash, `.bat` or `.cmd` with `cmd /c`, `.ps1` with PowerShell. It receives the port flags and must forward them (`"$@"` or `%*`). |

How the hub builds the command:

| App | Command |
|---|---|
| Streamlit | `<python> -m streamlit run <folder>/<file> --server.port=N --server.address=127.0.0.1 --server.headless=true --server.baseUrlPath=<app_id> …` |
| Python | `<python> <folder>/<file> --port=N --app_id=<app_id>` |
| `command` set | The list, with the placeholders filled in |
| `bash_file` set | The script's interpreter, the script, then the flags above |
| `activate: true` | `conda run -n <env> --no-capture-output python …` |

`<python>` is `python_executable` if set, else the interpreter of `virtual_environment`, else the hub's own. No shell is involved, so quoting is never an issue.

### Containers

These keys apply to `docker` and `kubernetes` apps. See [Docker](../deployment/docker.md#docker-apps) and [Kubernetes](../deployment/kubernetes.md).

| Key | Applies to | Default | Description |
|---|---|---|---|
| `image` | both | required | Container image. `file` and `command` are then paths and commands inside the image; `folder`, `bash_file`, `virtual_environment`, `python_executable` and `activate` are ignored. |
| `serves` | both | `web` | `streamlit`: the image gets the Streamlit flags, keeps the `/<app_id>` prefix, and is checked on `_stcore/health`. `web`: any other server; requests arrive without the prefix. A `web` image with neither `file` nor `command` runs its own command. |
| `container_port` | both | `8501` (Streamlit), `8000` | Port the app listens on inside the container |
| `volumes` | docker | `[]` | `docker run -v` values: `"<host path or named volume>:<path in the container>[:ro]"`. Host paths are on the Docker host. |
| `runtime_args` | docker | `[]` | Extra `docker run` arguments, such as `["--memory=2g", "--cpus=1"]` |
| `kubernetes` | kubernetes | `{}` | `namespace`, `resources`, `node_selector`, `service_account`, `image_pull_policy`, `image_pull_secrets`, `env_from`, copied into the Pod spec |
| `runtime` | apps without `type` | `process` | Before 2.2: `process`, `docker` or `kubernetes` for `.sl` and `.py` apps. `type` replaces it. |

### Environment, arguments and lifecycle

These keys apply to `streamlit`, `python`, `docker` and `kubernetes` apps.

| Key | Default | Description |
|---|---|---|
| `args` | `[]` | Extra arguments appended to the command |
| `env` | `{}` | Extra environment variables |
| `env_passthrough` | `[]` | Names or globs of hub environment variables this app receives, like `env-passthrough` for one app. For Kubernetes apps the values are written into the Pod spec. |
| `auto_shutdown` | `true` | Stopped by a memory clean and by the idle timeout |
| `auto_start` | `false` | Started with the hub and after scheduled cleans |
| `idle_timeout` | `idle-timeout` setting | Minutes without use before the app stops; `0` disables it |
| `restart` | `never` | `on-failure` or `always`: relaunch after a crash or failed health checks, with backoff (1, 2, 4 … up to 60 s) |
| `health_path` | `_stcore/health` for Streamlit, none otherwise | Path under `/<app_id>/` that answers 2xx or 3xx when the app is healthy, used for readiness and the periodic checks. `""` turns it off. |
| `streamlit_user_headers` | `streamlit-user-headers` setting | Fill `st.user` from the hub's identity (Streamlit apps and images) |

## How an app becomes ready

- **With a health path,** the app is ready when `GET /<app_id>/<health_path>` answers 2xx or 3xx.
- **Without one,** a process is ready when its port is taken, and a container or pod when a TCP connection succeeds.

An app that isn't ready within `startup-timeout` is stopped and shows an error page. While it runs, its health path is checked every `health-interval` seconds; after `health-failures` failures in a row, the app is stopped, a `health` notification is sent, and its `restart` policy applies.
