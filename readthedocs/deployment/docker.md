# Docker

There are two separate topics here: **the hub in a container**, and **apps in containers** (`"type": "docker"`). They combine: the Compose file runs the hub in a container that starts app containers on the host's daemon.

## The hub in a container

The image [`kavehbc/streamhub`](https://hub.docker.com/r/kavehbc/streamhub) on Docker Hub (built from the repository's `Dockerfile` by `make docker-build`; each [release](../development/building.md#releases) also publishes it as `ghcr.io/kavehbc/streamhub:<version>` and `:latest`):

- has Python 3.12, the `tools`, `examples` and `oidc` extras, and the `docker` client;
- runs as the non-root user `streamhub` (uid 1000), in supervised mode (`STREAMHUB_SUPERVISED=1`);
- runs `streamhub run` on `STREAMHUB_CONFIG=/config`, a volume;
- has a health check on `/api/health`, and exposes port 8500.

```bash
docker run -d --name streamhub -p 8500:8500 -v streamhub-config:/config kavehbc/streamhub
docker logs streamhub      # look for "Setup token:", then open http://localhost:8500
```

**The admin.** The image sets no password. An empty `/config` runs on the defaults, and the first visit opens the [setup page](../getting-started/quickstart.md#2-create-your-own-hub), which shows the `docker logs` command that prints the token. To define the admin up front instead, pass `-e STREAMHUB_ADMIN_PASSWORD=…`.

**The demo:** `docker run -p 8500:8500 kavehbc/streamhub streamhub demo` (login `admin` / `admin`).

### Docker Compose

The repository's `docker-compose.yml` runs the hub on `./config`:

```bash
cp .env.example .env     # optional settings, see below
docker compose up -d --build    # or: make docker-up
docker compose logs -f          # or: make docker-logs
docker compose down             # or: make docker-down
```

| Compose setting | Why |
|---|---|
| `./config:/config` | The config folder. Admin-page saves, `logs/`, `temp/`, `.streamhub-secret` and the session database go there, so uid 1000 must be able to write to it. |
| `/var/run/docker.sock` mounted, and `group_add: ${DOCKER_GID}` | Lets the hub run Docker apps and use the Docker tab. `DOCKER_GID` is the socket's group: `0` on Docker Desktop; on Linux, `getent group docker \| cut -d: -f3`. |
| `networks: streamhub-apps`, `STREAMHUB_DOCKER_NETWORK=streamhub-apps` | Docker apps join this network, so the hub reaches them by container name |
| `restart: on-failure` | **Restart hub** (exit code 3) starts it again; **Stop hub** (exit code 0) leaves it stopped |
| `init: true` | An init process that forwards signals and reaps orphaned processes |
| `stop_grace_period: 30s` | Time for the drain and the app shutdown |

`.env` (copied from `.env.example`) can set `STREAMHUB_ADMIN_PASSWORD`, `STREAMHUB_COOKIE_SECRET`, `STREAMHUB_SLACK_HOOK`, `STREAMHUB_CONFIG` and `DOCKER_GID`.

```{warning}
Whoever controls the Docker daemon controls its host. If you don't need Docker apps or the Docker tab, remove the socket mount and `group_add`.
```

### Keeping files

- The bundled static folder belongs to the container and is lost when it is replaced: set `cdf` to a folder under `/config` (for example `"cdf": "cdf"`) to keep uploaded icons.
- If `/config` isn't writable, point `log-folder`, `temp` and `sessions-db` elsewhere. Without a writable `sessions-db`, session revocations apply only to the running instance.

### Building the image

```bash
make docker-build       # tags kavehbc/streamhub:<version> and kavehbc/streamhub:latest
make docker-build IMAGE_NAME=registry.example.com/streamhub
```

## Docker apps

An app with `"type": "docker"` runs from an image instead of a local environment:

```json
{
  "board": ["sales.brd"],
  "app_id": "reports",
  "type": "docker",
  "image": "ghcr.io/acme/reports:1.4",
  "serves": "streamlit",
  "file": "/app/main.py",
  "volumes": ["/srv/reports-data:/data:ro"],
  "runtime_args": ["--memory=2g", "--cpus=1"]
}
```

- **`serves`** says what the image runs. `streamlit` gets the Streamlit flags and `file`, and keeps the `/<app_id>` prefix. `web` (the default) runs `file`, `command`, or, with neither, the image's own command, listening on `container_port` (default `8000`; `8501` for Streamlit).
- **`env`** sets variables, **`volumes`** mounts host paths or named volumes, and **`runtime_args`** adds other `docker run` options such as limits.
- A missing image is pulled by `docker run` within `startup-timeout`. Pull big images first, on the [Docker tab](../admin-guide/docker.md).
- The `docker` CLI must be on the hub's PATH (or set `STREAMHUB_DOCKER`), and the hub's user must be allowed to use the daemon.

How the hub reaches the container:

| The hub runs | Setting | The container |
|---|---|---|
| On the host | – | Is published on `127.0.0.1:<port>` only |
| In a container, with the host's socket | `docker-network` | Joins that network without publishing a port. The hub proxies to `http://<container name>:<container_port>`. |

Containers are named `streamhub-<instance-id or hub>-<app_id>` and labelled with the app and instance. Leftover containers of the same instance are removed when the hub starts. On Windows, with Docker Desktop, `docker-socket` must be an `npipe://` URL, and images must match the daemon's OS.

The admin page's app editor has a *Docker image* type with all these fields, and the Docker tab's **New app** button starts it from an existing image.
