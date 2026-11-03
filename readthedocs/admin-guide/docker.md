# Docker

The **Docker** tab (admins) manages the Docker daemon that runs the hub's [Docker apps](../deployment/docker.md#docker-apps).

```{figure} /_static/screenshots/admin-docker.png
:alt: The Docker tab with the daemon, containers and images
:class: screenshot

The Docker tab, filtered to Streamhub's own containers and images.
```

## Daemon

The top card shows the `docker` client in use, the daemon (the `docker-socket` setting, or Docker's default), the server version, and whether the `docker-network` setting names an existing network. Without a network, app containers are published on `127.0.0.1`.

## Containers

Every container of the daemon, or only **Streamhub apps** (by their `streamhub.app` label), or only **Running** ones. Per container: **start**, **stop**, **restart**, **logs** (the last 500 lines) and **remove**. The hub's own container is marked: stopping it stops Streamhub. Stopping an app's container stops the app, and then its `restart` policy applies.

## Images

Every image, with its size, age and number of containers. Per image:

- **New app** (＋) opens the app editor on that image, with the type *Docker image*;
- **Pull** (⤓) pulls it again;
- **Remove** (🗑).

**Pull** at the top fetches a new image by name, for example `python:3.12-slim`, for up to 15 minutes. Pull big images before you use them: a missing image is pulled when its app starts, within the startup timeout.

Image names and container names are checked, and every action is written to the audit log.

```{warning}
Whoever controls the Docker daemon controls its host. Only admins reach this tab, but treat admin accounts accordingly, and remove the socket mount if you don't need Docker. See [Security](../deployment/security.md).
```
