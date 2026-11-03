# Environment variables

Secrets belong in environment variables, not in the JSON files. On Linux, put them in the service's environment file (`/etc/streamhub/streamhub.env` in the systemd unit); with Docker Compose, in `.env`.

## Hub variables

| Variable | Effect |
|---|---|
| `STREAMHUB_CONFIG` | The config folder (or file) of `streamhub run` when none is given. The Docker image sets it to `/config`. |
| `STREAMHUB_ADMIN_PASSWORD` | Adds, or replaces, an admin user without a users file. A raw value is hashed in memory at first use; a hash from `streamhub passwd` is used as is. `streamhub demo` defaults it to `admin`; the Docker image leaves it unset, so a new hub opens on the setup page. |
| `STREAMHUB_ADMIN_USER` | Name of that admin (default `admin`) |
| `STREAMHUB_COOKIE_SECRET` | Signs the session cookies. Set the same value on every instance of a [multi-instance](../deployment/multiple-instances.md) setup. Overrides `cookie-secret`. |
| `STREAMHUB_SLACK_HOOK` | Slack webhook; overrides `slack-hook` |
| `STREAMHUB_SMTP_PASSWORD` | Password of the `smtp` mail server |
| `STREAMHUB_OIDC_CLIENT_SECRET` | Client secret of OpenID Connect |
| `STREAMHUB_LDAP_BIND_PASSWORD` | Password of the LDAP service account (`bind-dn`) |
| `STREAMHUB_METRICS_TOKEN` | Bearer token that a Prometheus scraper sends to `/metrics` |
| `STREAMHUB_INSTANCE_ID` | Overrides `instance-id` |
| `STREAMHUB_DOCKER_SOCKET`, `STREAMHUB_DOCKER_NETWORK` | Override `docker-socket` and `docker-network` |
| `STREAMHUB_DOCKER`, `STREAMHUB_KUBECTL` | Paths of the `docker` and `kubectl` executables when they are not on PATH |
| `STREAMHUB_SUPERVISED=1` | Same as `--supervised` |

Settings set by a variable are read-only on the admin page's Settings tab, which names the variable.

## What apps receive

Apps **don't inherit** the hub's environment, so the secrets above never reach them. A process app gets:

- what programs need: `PATH`, locale, temp and home folders, proxies, CA bundles and `CONDA_*` (on Windows also `SYSTEMROOT`, `APPDATA` and the other OS variables);
- the hub variables named by `env-passthrough` (every app) and its own `env_passthrough`;
- the [app variables](../deployment/writing-apps.md#environment-variables) `STREAMHUB_PORT`, `STREAMHUB_HOST`, `STREAMHUB_APP_ID`, `STREAMHUB_BASE_PATH`, `STREAMHUB_URL`, `STREAMHUB_APP_KEY`, and `PYTHONUNBUFFERED=1`;
- its own `env`.

To give an app a variable of the hub, such as cloud credentials, list it:

```json
{ "app_id": "forecast", "env_passthrough": ["AWS_*", "DATABASE_URL"] }
```

Docker apps receive their variables by name (`docker run -e NAME`), so values never appear on a command line.
