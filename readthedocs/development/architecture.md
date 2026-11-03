# Architecture

Streamhub is **one Python process running one asyncio event loop**, which Tornado uses. Blocking work (password hashing, LDAP binds, SMTP, SQLite, `conda env list`, waiting on process trees) runs in an executor. The HTTP and HTTPS listeners share one Tornado application. The same code runs on Linux and Windows; every OS-specific branch lives in `platform_utils.py`.

The maintainer documentation in the repository goes deeper: [docs/architecture.md](https://github.com/kavehbc/streamhub/blob/main/docs/architecture.md).

```{mermaid}
flowchart LR
    B[Browser] -->|HTTP/WS :8500| T[Tornado application]
    T -->|static| S["/cdf/, /temp/, /static/"]
    T -->|"pages, login, SSO, admin, /api/, /metrics"| H[Hub handlers]
    T -->|app not running yet| L[LaunchHandler]
    L -->|"AppManager.start → runtime"| P1[(App: process, container or pod)]
    T -->|"app ready: RunningAppMatcher"| R[Proxy HTTP / WebSocket]
    R --> P1
    R -.->|curl apps| X[(External URL)]
    J["Daily clean, idle reaper, health checks"] -->|stop| P1
```

## Request routing

Routes are tried in order: the hub's own pages and APIs first, then the static folders. Then comes `RunningAppMatcher`, a custom Tornado matcher. It reads the first path segment, looks it up among the running apps, and matches only when that app is ready; the upgrade header picks the WebSocket or HTTP proxy. A request for an app that isn't ready falls through to `LaunchHandler`, which starts the app or shows its loading or error page. Nothing is added to or removed from the route table at runtime.

## App lifecycle

```{mermaid}
sequenceDiagram
    participant U as Browser
    participant L as LaunchHandler
    participant M as AppManager
    participant P as App
    participant X as Proxy
    U->>L: GET /forecast/
    L->>M: start(app)
    M->>M: allocate a port from port-range
    M->>P: spawn (own process group, log to logs/forecast.log)
    L-->>U: loading page (polls /api/apps/forecast/status)
    M->>P: wait for the health path (or the port), bind check
    U->>X: GET /forecast/ (matched: app ready)
    X->>P: stream the request and response, WebSocket
    Note over P: exits, or fails its health checks
    M->>M: release the port, apply the restart policy
```

- **One launch per app:** concurrent requests share a single launch.
- **Runtimes** (`runtimes.py`) decide how an app runs: a local process, `docker run` in the foreground, or a Kubernetes pod with a `follow-pod` process that streams its log. Each runtime gives the manager **one local child process** to watch, so logs, exit detection and restart policies work the same everywhere.
- **Stopping** an app terminates its whole process tree: SIGTERM, then a kill after `stop-timeout` (on Windows, `TerminateProcess`).
- **Leftovers of a crashed hub** are recorded in `<log-folder>/processes.json` and swept at the next start. On Windows the hub runs in a Job Object, so its apps die with it.

## The proxy

- **HTTP:** every method; the query string is kept, and request and response bodies are streamed. Hop-by-hop headers are dropped and redirects aren't followed. The hub's cookies are removed, and `X-Forwarded-For/Proto/Host/Prefix` plus the identity headers are added.
- **Prefixes:** Streamlit serves itself under `/<app_id>/` (`--server.baseUrlPath`), so the proxy forwards the full path. For other apps, the proxy strips `/<app_id>`, sends `X-Forwarded-Prefix`, and rewrites `Location` headers.
- **WebSocket:** subprotocols are forwarded (Streamlit needs `streamlit`), early client messages are buffered, closes propagate both ways, and messages are capped at `max-ws-message-mb`.

## Hub lifecycle

1. **Startup:** listen, install signal handlers, create the folders, log the setup token if there is no admin, schedule the daily clean, load usage and session data, start the idle reaper and health checks, sweep leftovers, notify, start `auto_start` apps.
2. **Run** until a shutdown is requested.
3. **Shutdown:** stop listening, drain for up to `drain-timeout`, stop every app, save the usage counters, empty `temp`, notify.
4. **Restart:** exit with code 3 under a service manager (`--supervised`), or start a new copy of the hub first.

## Modules

| Module | Responsibility |
|---|---|
| `cli.py` | The `streamhub` command (Click) |
| `app.py` | The `Hub` object, routes, startup, memory clean, reload, shutdown and restart |
| `config.py` | Typed settings, defaults, validation, environment overrides; the Settings form definition |
| `bootstrap.py` | `init`, `demo`, and the setup page's first admin |
| `catalog.py` | Apps, boards, users and news, cached by modification time |
| `validate.py` | The checks shared by `streamhub check` and the admin editors |
| `auth.py`, `sessions.py` | Password hashes, roles and access, session cookies, group mapping, LDAP, login throttle, identity tokens; the session store |
| `launcher.py`, `runtimes.py`, `ports.py` | Launching, readiness, health checks, restart policy and stop; the runtimes; port leases |
| `proxy.py` | The HTTP and WebSocket proxy |
| `scheduler.py`, `notify.py`, `usage.py` | The daily job; Slack, Teams and email; usage counters in SQLite |
| `platform_utils.py` | Everything that differs between Linux and Windows |
| `handlers/` | Pages, login, SSO, setup, apps, admin API, admin page, Docker, static files and backup tabs |
