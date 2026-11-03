# Dashboard and network

Managers and admins see the **Dashboard**. It refreshes itself every few seconds.

```{figure} /_static/screenshots/admin-dashboard-full.png
:alt: The full dashboard with server meters and the app table
:class: screenshot

The dashboard: server load at the top, then every app.
```

## Server meters

| Tile | Shows |
|---|---|
| CPU | Total CPU use, a bar per logical CPU, and the CPU count |
| Memory | Memory in use, of the total |
| Load 1 / 5 / 15 min | Load average as a share of all CPUs (`n/a` on Windows, which has none) |
| Apps | Running apps, of all launchable apps |
| Open sessions | WebSocket connections to apps (a Streamlit tab holds one) |
| Temp folder | Size and file count of the `temp` folder. The 🗑 button (**Purge**) empties it; files in use are skipped. |

## Apps table

Every app that the hub can launch or proxy, with:

- **Status**: running, starting, unhealthy, idle, or the exit code of the last run;
- **Runtime**: `process`, `docker`, `kubernetes` or `external`, and the health path;
- **PID / port**, **Sessions**, **Memory** and **CPU** of the app's process tree;
- **Up since**, **Last access**, and a chart of today's requests, hour by hour.

Filter the table by name, or with **All**, **Running**, **Idle** and **Problems**. The actions of a row are:

| Button | Action |
|---|---|
| ▶ Start | Start the app now |
| ■ Stop | Stop it (its process tree, container or pod) |
| ↻ Restart | Stop and start it |
| CPU affinity | Pin the app to some CPUs, for example `0,1`, where the OS supports it |
| Log | Open its log in a dialog. With **Follow**, new lines appear as the app writes them. |

```{figure} /_static/screenshots/admin-log.png
:alt: The log dialog of the Flask demo app
:class: screenshot

The log dialog, following new output.
```

The same actions are available as an API: `POST /api/apps/<id>/start`, `/stop` and `/restart` ([Endpoints](../reference/endpoints.md)).

## Network

**Network** lists the listening TCP ports of the server, with the PID and process name where the OS tells them. Use it to find a port conflict, or an app listening on more than `127.0.0.1`.

```{figure} /_static/screenshots/admin-network.png
:alt: The Network tab listing listening ports
:class: screenshot

The Network tab, filtered to the hub's port range.
```

## In the dark

The panel follows the dark theme too:

```{figure} /_static/screenshots/admin-dashboard-dark.png
:alt: The dashboard in the dark theme
:class: screenshot

The dashboard in the dark theme.
```
