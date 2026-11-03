# Streamhub Documentation

Streamhub is a Tornado-based **reverse proxy and app launcher** that serves many Streamlit and Python web apps (Flask, Dash, FastAPI, …) behind **one public port**. Each app runs in its own process and environment and is reached at `http://host:8500/<app_id>/`. Apps are declared in JSON files. Version 2.2 runs on Linux, on Windows and in Docker, and can run apps as local processes, Docker containers or Kubernetes pods.

It is an extended fork of [streamlit-launchpad](https://github.com/ideonate/streamlit-launchpad). The end-user guide is the root [README.md](../README.md), which is also shown by `help.cmd`. The full user documentation, with screenshots, is [streamhub.readthedocs.io](https://streamhub.readthedocs.io/), built from [readthedocs/](../readthedocs/README.md). The package is [py-streamhub](https://pypi.org/project/py-streamhub/) on PyPI and the image [kavehbc/streamhub](https://hub.docker.com/r/kavehbc/streamhub) on Docker Hub.

## Documents

| Document | Contents |
|---|---|
| [architecture.md](architecture.md) | `Hub` object, routing, access control, app lifecycle, proxy, module reference |
| [configuration.md](configuration.md) | Every config key, environment variable, and app, user and news field |
| [operations.md](operations.md) | Install, run, Docker, services, endpoints and access, deploying apps, troubleshooting |
| [windows-compatibility.md](windows-compatibility.md) | How Windows is supported, platform differences, Windows deployment |
| [known-issues.md](known-issues.md) | Open issues (fixed ones are in the README changelog) |
| [roadmap.md](roadmap.md) | Remaining work |
| [recommendations.md](recommendations.md) | Review recommendations not implemented yet: priorities, improvements, proposed features |

## Capabilities at a glance

- **App types**, set by the `app_id` suffix: `.sl` (Streamlit), `.py` (any Python web server), `.url` (redirect), `.curl` (masked external URL), plus the built-in `help.cmd`.
- **Launching**:
  - an app starts on first request in its own process group, on a port from `port-range`;
  - it runs as a process, a Docker container or a Kubernetes pod (`runtime`);
  - its output goes to `logs/<app_id>.log`;
  - the loading page waits until the app's health path (or port) answers.
- **Access**: local users, OpenID Connect and LDAP, with groups mapped to roles and boards; revocable sessions.
- **Boards**: boards (`*.brd`) group apps. Board authentication also protects the apps themselves. There are roles, hashed passwords, XSRF protection and login throttling. Boards have search, filters, live status, favorites and a dark mode, in a responsive UI with the same top menu on every page, including the admin panel.
- **Proxy**: all HTTP methods, streamed requests and responses, WebSockets, prefix-aware redirects, and the signed-in user passed to apps in headers, including a token each app can verify.
- **Process control**:
  - stop apps manually, after an idle timeout, or in a daily memory clean (time-zone aware);
  - start chosen apps automatically;
  - restart crashed or unhealthy apps under a restart policy.
- **Operations**: the `/admin/` page, JSON API, `/metrics`, `streamhub check`, Slack, Teams and email notifications, an issue-report form, audit log, supervised restart, several instances behind a sticky load balancer, Docker image, Kubernetes manifests, systemd unit and NSSM setup.

## Repository layout

```
streamhub/            The package
  app.py              Hub: routes, startup, memory clean, reload, shutdown
  config.py           Typed settings from streamhub.json + environment
  catalog.py          Apps, boards, users, news (cached JSON)
  launcher.py         Start / watch / health-check / stop apps
  runtimes.py         Process, Docker and Kubernetes runtimes
  proxy.py            HTTP and WebSocket reverse proxy
  platform_utils.py   Everything that differs between Linux and Windows
  auth.py sessions.py usage.py validate.py
  ports.py scheduler.py notify.py cli.py bootstrap.py (init, demo, first admin)
  handlers/           Tornado request handlers (pages, login, SSO, apps, admin API, admin page)
  tools/              help.cmd Streamlit page
  templates/          HTML templates (layouts, pages, admin panel)
  static/             UI stylesheet, logo and icons (brand/), Bootstrap and Font Awesome (vendor/), served at /static/
  cdf/                App icons and other static files, served at /cdf/
  demo/               The demo: Streamlit, Flask and FastAPI samples + config (streamhub demo)
  starter/            The starter config that streamhub init writes
tests/                Unit, handler, integration and documentation-link tests (pytest)
config/               Your deployment config (git-ignored, except its README); mounted at /config by Compose
deploy/               systemd unit, Kubernetes and load-balancer examples, PyInstaller spec, minimum-version constraints, icon generator
readthedocs/          The documentation site (Sphinx, MyST, Read the Docs): guides, reference, screenshots and the screenshot tool (_tools/)
Makefile make.bat     Common tasks: install, test, demo, start, passwd, Docker, docs, clean
Dockerfile docker-compose.yml pyproject.toml
```
