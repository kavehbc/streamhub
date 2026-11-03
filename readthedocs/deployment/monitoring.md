# Monitoring

## Health endpoint

`GET /api/health` answers `{"status": "ok", "instance": "…", "version": "2.3.0"}` to anyone. Use it for load balancer and container health checks; the Docker image's `HEALTHCHECK` does.

## Prometheus metrics

`GET /metrics` serves the Prometheus text format to a manager's session, or to a scraper that sends `Authorization: Bearer <STREAMHUB_METRICS_TOKEN>`. It holds no user names, emails or URLs.

```yaml
# prometheus.yml
scrape_configs:
  - job_name: streamhub
    scheme: https
    authorization:
      credentials: "<STREAMHUB_METRICS_TOKEN>"
    static_configs:
      - targets: ["apps.example.com"]
```

| Metric | Labels | Meaning |
|---|---|---|
| `streamhub_info` | `version`, `instance` | Always 1 |
| `streamhub_uptime_seconds` | – | Since the hub started |
| `streamhub_app_requests_total` | `app` | Page loads and WebSocket sessions, kept across restarts |
| `streamhub_app_up` | `app` | 1 while the app is ready |
| `streamhub_app_healthy` | `app` | 1 while it passes its health checks |
| `streamhub_app_sessions` | `app` | Open WebSocket sessions |
| `streamhub_app_restarts` | `app` | Restarts in the current backoff run |
| `streamhub_app_ready_seconds` | `app` | Time from launch to ready |
| `streamhub_app_start_failures_total` | `app` | Launches that failed, timed out or were refused by `bind-check` |
| `streamhub_notification_failures_total` | `channel` | Undelivered notifications per channel type |
| `streamhub_login_failures_total` | – | Failed logins |
| `streamhub_config_errors` | `file` | 1 for each catalog file that is currently invalid |

Counters other than `app_requests_total` restart at 0 with the hub. Each instance serves its own metrics.

Useful alerts: `streamhub_config_errors > 0`, `increase(streamhub_app_start_failures_total[15m]) > 0`, `streamhub_app_healthy == 0`, and a rising `streamhub_login_failures_total`.

## Logs

| Log | Where | Contents |
|---|---|---|
| Hub log | stderr (the journal, `docker logs`, or `make start`'s `logs/streamhub.log`) | Startup, launches, stops, health failures, warnings. `--log-level` or `--debug` sets the detail. |
| Audit log | The `streamhub.audit` logger, in the hub log | Logins (with their source), refused SSO logins and their reason, admin actions, admin-page edits, Docker actions, issue reports |
| App logs | `<log-folder>/<app_id>.log` | Each app's stdout and stderr. The previous run is kept as `.log.1`. Shown on `/out/<app_id>/` and in the dashboard's log dialog. |

## Usage

The hub counts page loads and WebSocket sessions per app and hour, and keeps them in `<log-folder>/usage.sqlite3` for `usage-retention-days` (90 by default). The dashboard charts today's requests per app.

## Notifications

[Notifications](../configuration/notifications.md) report hub starts and stops, memory cleans, apps stopped for failing health checks, and issue reports, to Slack, Teams or email.
