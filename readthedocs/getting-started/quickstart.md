# Quick start

This page takes you from an install to a running hub. You need Streamhub [installed](installation.md) with the `tools` and `examples` extras.

## 1. Try the demo

```bash
streamhub demo
```

The demo is a hub with a Streamlit, a Flask and a FastAPI app on a public board. Open <http://localhost:8500> and sign in as **admin** / **admin**.

`streamhub demo` copies the bundled demo to a writable folder first: `~/.local/share/streamhub/demo` on Linux, `%LOCALAPPDATA%\streamhub\demo` on Windows (or `--folder DIR`). Each run refreshes the demo apps and keeps your edits to its JSON files. Use `--port N` for another port. While the demo password is in use, the hub logs a warning and the admin page shows a banner, so don't expose the demo to a network.

```{tip}
With Docker: `docker run -p 8500:8500 kavehbc/streamhub streamhub demo`.
```

## 2. Create your own hub

Pick one of the two ways below. Both give the hub its first admin account.

::::{tab-set}

:::{tab-item} With streamhub init
```console
$ streamhub init my-hub
Site title [Streamhub]: Analytics Hub
HTTP port [8500]:
Admin user name [admin]:
Admin password (8 characters or more):
Repeat for confirmation:
wrote my-hub/streamhub-apps.json
wrote my-hub/streamhub-news.json
wrote my-hub/streamhub.json
wrote my-hub/streamhub-users.json

Next: streamhub run my-hub
Then open http://localhost:8500/
```

`init` writes a starter config folder: the settings, one public board with a link and the Help page, a welcome announcement, and a users file with the hashed admin password. It never overwrites a file unless you pass `--force` (other users are kept). For scripts, `--yes` skips the questions: `streamhub init my-hub --yes --site-title "Analytics Hub" --admin-password '…'`. With `--yes` and no password, no users file is written, and the hub opens on the setup page instead.
:::

:::{tab-item} With the setup page
Start a hub on any folder, even an empty one:

```console
$ mkdir my-hub
$ streamhub run my-hub
… WARNING streamhub.app: No admin account yet: open http://localhost:8500/ and enter the setup token below, or open http://localhost:8500/setup/?token=Xxt1JaC-…
… WARNING streamhub.app: Setup token: Xxt1JaC-…
```

Open <http://localhost:8500>. While the hub has no admin, the start page opens the **setup page**. Paste the **setup token** that the hub printed (or open the whole link), choose the admin name and password, and optionally name the site. The token makes sure that only the person who can read the hub's console creates the admin. In Docker, the page shows the `docker logs` command that prints the token.

```{figure} /_static/screenshots/setup.png
:alt: The first-run setup page asking for the setup token, admin name, password and site title
:class: screenshot
:width: 80%

The setup page of a new hub.
```

The page creates the users file and `streamhub.json`, then signs you in. Once an admin exists, `/setup/` returns 404.
:::
::::

A third way, useful for containers and services: set `STREAMHUB_ADMIN_PASSWORD` (and optionally `STREAMHUB_ADMIN_USER`, default `admin`) in the hub's environment. See [Environment variables](../configuration/environment.md).

## 3. Run it

```bash
streamhub run my-hub
```

Open <http://localhost:8500> and sign in. The config folder defaults to `$STREAMHUB_CONFIG`, then to the current folder. `--port`, `--debug` and the other options are in the [CLI reference](../reference/cli.md).

## 4. Add your apps

Open the account menu (your avatar, top right) and choose **Apps and boards**. Click **Add app**, choose its **Type** (Streamlit, Python, Docker image…), fill in the folder and entry script, and save. There's no restart: the new card appears at once, and the app starts the first time someone opens it.

```{figure} /_static/screenshots/admin-app-editor.png
:alt: The app editor on the admin page
:class: screenshot

The app editor shows the fields of the chosen type and checks folders and files on the server as you type.
```

The [tutorial](tutorial.md) walks through a complete hub: boards, apps, users and news.

## 5. Make it permanent

- Run the hub as a service: [systemd](../deployment/linux.md), [Windows (NSSM)](../deployment/windows.md) or [Docker Compose](../deployment/docker.md).
- Serve it over HTTPS: [HTTPS and reverse proxies](../deployment/https-and-proxies.md).
- Go through the [security checklist](../deployment/security.md).
