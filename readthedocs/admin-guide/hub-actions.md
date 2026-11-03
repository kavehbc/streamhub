# Hub actions

The account menu holds four actions that act on the whole hub. Each opens a confirmation page first (a GET), and runs only when you confirm (a POST with the XSRF token).

| Action | Who | Path | What it does |
|---|---|---|---|
| **Clear memory** | Everyone signed in | `/clear/` | Stops the apps with `auto_shutdown` and empties the temp folder. Admins can stop **all** apps instead. Optionally starts the `auto_start` apps afterwards, or relaunches the apps that were stopped. |
| **Reload configuration** | Admin | `/update/` | Re-reads `streamhub.json` after an edit on disk, and lists any key that needs a restart. Not needed after a save on the admin page. |
| **Restart hub** | Admin | `/restart/` | Stops every app and starts the hub again |
| **Stop hub** | Admin | `/exit/` | Stops every app and the hub |

## The daily memory clean

Every day at `schedule` (default `02:00`, in `timezone`), the hub runs a memory clean by itself. It stops the apps with `auto_shutdown`, empties the temp folder, and starts the `auto_start` apps again. Set `schedule` to `"off"` to disable it.

## How restart works

- **Run by a service manager** (systemd, NSSM, Docker), start the hub with `--supervised`, or set `STREAMHUB_SUPERVISED=1`, as the Docker image does. **Restart** then exits with code 3, and the manager starts the hub again. **Stop** exits with code 0, so a manager set to restart *on failure* leaves it stopped.
- **Run by hand**, **Restart** starts a new copy of the hub before the old one exits.

## Clean shutdown

On **Stop**, **Restart**, Ctrl+C or SIGTERM, the hub first **drains**. It stops accepting connections and waits up to `drain-timeout` (10 s) for proxied requests and WebSocket sessions to end; an open Streamlit tab keeps its session, so expect the full wait. Meanwhile new app launches get 503. Then it stops every app, saves the usage counters, empties the temp folder and sends a `system` notification.

If the hub crashes instead, its next start stops the apps it left behind. On Windows, they stop with the hub.
