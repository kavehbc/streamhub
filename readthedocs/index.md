# Streamhub

**Streamhub runs many Streamlit and Python web apps for many users, behind one port.**

Each app (Streamlit, Flask, Dash, FastAPI, or any web server) runs in its own process and Python environment, or as a Docker container or Kubernetes pod, and is served at `http://<host>:<port>/<app_id>/`. Apps start when someone first opens them, stop when idle or on a daily schedule, and are listed on **boards** that can require a login. An admin panel in the browser manages apps, users and settings. Streamhub runs on **Linux and Windows**, and in Docker.

```{figure} /_static/screenshots/home.png
:alt: The Streamhub home page with favorites, boards and the latest news
:class: screenshot

The home page of a hub: favorites, the boards you can open and the latest announcements.
```

::::{grid} 1 2 2 3
:gutter: 3

:::{grid-item-card} {octicon}`rocket` Get started
:link: getting-started/quickstart
:link-type: doc

Install Streamhub, try the demo, and create your own hub in a few minutes.
:::

:::{grid-item-card} {octicon}`person` Use a hub
:link: user-guide/home-and-boards
:link-type: doc

Boards, app cards, favorites, signing in and reporting an issue.
:::

:::{grid-item-card} {octicon}`tools` Administer a hub
:link: admin-guide/index
:link-type: doc

The admin panel: dashboard, apps, users, news, settings, Docker and backups.
:::

:::{grid-item-card} {octicon}`gear` Configure
:link: configuration/index
:link-type: doc

Every key of the four JSON files, and the environment variables.
:::

:::{grid-item-card} {octicon}`server` Deploy
:link: deployment/index
:link-type: doc

Write apps for the hub, then run it with Docker, Kubernetes, systemd or as a Windows service.
:::

:::{grid-item-card} {octicon}`code` Build and contribute
:link: development/building
:link-type: doc

Build from source, run the tests, build the wheel, the executable and the Docker image.
:::
::::

## Features

- **One port for every app.** A reverse proxy for HTTP and WebSockets serves each app under its own path, and handles streamed uploads and downloads and redirects that keep the app's prefix.
- **Apps start on demand.** Opening an app starts it on a free internal port and shows a loading page until it answers. Apps stop after an idle timeout, during the daily memory clean, or when an admin stops them. Apps can also start with the hub, and they restart after a crash or failed health checks.
- **Many kinds of apps:** Streamlit scripts, any Python web server, Docker images, Kubernetes pods, links, and external sites proxied behind the hub's login.
- **Boards and access control.** Boards group apps. Protected boards need a login, and they protect their apps as well as the list. There are four roles: `admin`, `manager`, `user` and `guest`.
- **Sign-in:** local users with hashed passwords, OpenID Connect (Entra ID, Okta, Keycloak, Google…) and LDAP, with directory groups mapped to roles and boards. Sessions can be revoked.
- **Admin panel** in the browser: live CPU and memory, per-app state, logs, start, stop and restart. Form editors for apps, users, news and settings, plus Docker containers and images, static files, sessions, a JSON editor with git, and backup and restore.
- **Operations:** Prometheus metrics, health checks, Slack, Microsoft Teams and email notifications, an issue-report form, an audit log, and several instances behind a load balancer.
- **Cross-platform:** the same code on Linux and Windows. Also a Docker image, Kubernetes manifests, a systemd unit, NSSM instructions and a single-file executable.

## How it works

```{mermaid}
flowchart LR
    B[Browser] -->|"HTTP / WebSocket :8500"| H[Streamhub]
    H -->|"/ , boards, login, /admin/"| P[Hub pages]
    H -->|"/sales-forecast/"| A1[(Streamlit app<br/>127.0.0.1:8501+)]
    H -->|"/price-monitor/"| A2[(Flask app)]
    H -->|"/reports/"| A3[(Docker container)]
    H -.->|"/wiki/ (proxy)"| X[(External site)]
```

The browser only ever talks to the hub. When a request arrives for an app that isn't running, the hub starts it and shows a loading page. Once the app answers, the hub proxies every request and WebSocket to it. [Architecture](development/architecture.md) has the details.

```{toctree}
:caption: Getting started
:hidden:

getting-started/installation
getting-started/quickstart
getting-started/tutorial
```

```{toctree}
:caption: User guide
:hidden:

user-guide/home-and-boards
user-guide/opening-apps
user-guide/signing-in
```

```{toctree}
:caption: Admin guide
:hidden:

admin-guide/index
admin-guide/dashboard
admin-guide/apps-and-boards
admin-guide/users-and-sessions
admin-guide/news
admin-guide/settings
admin-guide/docker
admin-guide/static-files
admin-guide/json-files-and-backup
admin-guide/hub-actions
```

```{toctree}
:caption: Configuration
:hidden:

configuration/index
configuration/settings
configuration/apps
configuration/users
configuration/news
configuration/environment
configuration/notifications
configuration/single-sign-on
```

```{toctree}
:caption: Deployment
:hidden:

deployment/index
deployment/writing-apps
deployment/docker
deployment/kubernetes
deployment/linux
deployment/windows
deployment/https-and-proxies
deployment/multiple-instances
deployment/monitoring
deployment/security
```

```{toctree}
:caption: Reference
:hidden:

reference/cli
reference/endpoints
reference/troubleshooting
```

```{toctree}
:caption: Development
:hidden:

development/building
development/architecture
development/documentation
changelog
```
