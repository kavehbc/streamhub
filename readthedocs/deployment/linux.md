# Linux service (systemd)

## Install

```bash
sudo useradd --system --create-home --home-dir /opt/streamhub streamhub
sudo -u streamhub python3 -m venv /opt/streamhub/.venv
sudo -u streamhub /opt/streamhub/.venv/bin/pip install "streamhub[tools,oidc] @ git+https://github.com/kavehbc/streamhub"
sudo mkdir -p /etc/streamhub && sudo chown streamhub: /etc/streamhub
sudo -u streamhub /opt/streamhub/.venv/bin/streamhub init /etc/streamhub
```

Keep secrets in an environment file that only the service can read:

```bash
sudo install -m 600 -o streamhub /dev/null /etc/streamhub/streamhub.env
sudoedit /etc/streamhub/streamhub.env
```

```ini
STREAMHUB_COOKIE_SECRET=a-long-random-string
STREAMHUB_SLACK_HOOK=https://hooks.slack.com/services/…
```

## The unit

The repository's `deploy/streamhub.service`:

```ini
[Unit]
Description=Streamhub
After=network-online.target

[Service]
User=streamhub
WorkingDirectory=/opt/streamhub
ExecStart=/opt/streamhub/.venv/bin/streamhub run --supervised /etc/streamhub
EnvironmentFile=-/etc/streamhub/streamhub.env
# /restart/ exits with code 3; /exit/ exits with 0 and stays down.
Restart=on-failure
RestartSec=2
KillMode=mixed
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
```

```bash
sudo cp deploy/streamhub.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now streamhub
journalctl -u streamhub -f
```

- `--supervised` makes **Restart hub** exit with code 3, which `Restart=on-failure` restarts; **Stop hub** exits with 0 and stays down.
- `KillMode=mixed` sends SIGTERM to the hub only, so it can drain and stop its apps itself; `TimeoutStopSec` leaves time for that.
- Logs go to the journal. Each app also has its own log, `logs/<app_id>.log` in the config folder.

## App environments

A service runs without your shell's PATH, so conda env **names** may not resolve. Prefer environment **folders**, for example `"virtual-environment": "/opt/conda/envs/apps"`, or a `python_executable` per app. The service user needs read access to the app folders and environments.

## Firewall

Open only the hub's port (or only the reverse proxy's). Apps listen on `127.0.0.1`, on the `port-range` ports, and must not be reachable from outside. Keep `bind-check` on to catch apps that listen on every interface.
