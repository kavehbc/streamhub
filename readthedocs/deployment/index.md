# Deployment overview

A production hub usually looks like this:

```{mermaid}
flowchart LR
    U[Users] -->|HTTPS 443| P[Reverse proxy<br/>nginx, Caddy, IIS, ingress]
    P -->|HTTP 8500| H[Streamhub<br/>--supervised]
    H --> A1[(Process apps<br/>127.0.0.1:8501+)]
    H --> A2[(Docker apps)]
    H --> A3[(Kubernetes pods)]
    S[systemd / NSSM / Docker] -.->|restarts on exit code 3| H
```

| Decision | Options | Guide |
|---|---|---|
| Where the hub runs | A Linux service, a Windows service, a container, a Kubernetes pod | [Linux](linux.md), [Windows](windows.md), [Docker](docker.md), [Kubernetes](kubernetes.md) |
| How apps run | Processes in Python environments on the server, Docker containers, or Kubernetes pods | [Writing apps](writing-apps.md), [Apps file](../configuration/apps.md) |
| How users sign in | Local users, OpenID Connect, LDAP | [Single sign-on](../configuration/single-sign-on.md) |
| TLS | The hub itself (`ssl_port`), or a reverse proxy in front | [HTTPS and reverse proxies](https-and-proxies.md) |
| Scale | One hub, or several behind a sticky load balancer | [Multiple instances](multiple-instances.md) |
| Monitoring | `/api/health`, Prometheus `/metrics`, notifications, logs | [Monitoring](monitoring.md) |

## Production checklist

- [ ] Run the hub under a service manager, with `--supervised`, so **Restart hub** works.
- [ ] Serve it over HTTPS, and set `behind-proxy` behind a reverse proxy.
- [ ] Set `STREAMHUB_COOKIE_SECRET`, and keep secrets in environment variables, never in the JSON files.
- [ ] Replace the demo password: `streamhub check` and the dashboard warn while `admin` / `admin` is in use.
- [ ] Point `cdf` at a folder of your config, so uploaded icons survive upgrades.
- [ ] Set `virtual-environment`, or give every app an environment, so apps don't run in the hub's own Python.
- [ ] Firewall the internal port range (`port-range`): only the hub's port should be reachable.
- [ ] Back up the config folder, including the users file.
- [ ] Run `streamhub check <config>` after every change on disk.

Read [Security](security.md) before exposing a hub to many users.
