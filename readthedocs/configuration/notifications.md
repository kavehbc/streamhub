# Notifications

The hub reports what happens to it to Slack, Microsoft Teams or email. Configure the channels on the Settings tab (**Notifications**), or in `streamhub.json`.

## Events

| Event | Sent when |
|---|---|
| `system` | The hub starts, stops or restarts |
| `clean` | A memory clean runs |
| `health` | An app is stopped after failing its health checks |
| `report` | A user sends the *Report an issue* form |

Every channel receives the events listed in its `events`, or all of them when `events` is missing.

## Channels

```json
"notifiers": [
  { "type": "teams", "url": "https://….logic.azure.com/…", "events": ["health", "report"] },
  { "type": "email", "to": ["ops@example.com"], "events": ["health"] },
  { "type": "slack", "url": "https://hooks.slack.com/…" }
],
"smtp": { "host": "smtp.example.com", "port": 587, "starttls": true,
          "username": "streamhub", "from": "streamhub@example.com" }
```

| `type` | Sends |
|---|---|
| `slack` | `{"text": …}` to a Slack incoming webhook |
| `teams` | An Adaptive Card to a Teams *Workflows* webhook. Slack `:emoji:` codes are removed. |
| `email` | A plain-text mail to `to`, through `smtp` |

The `slack-hook` setting, or `STREAMHUB_SLACK_HOOK`, adds one more Slack channel that receives every event.

## Mail server

| `smtp` key | Description |
|---|---|
| `host`, `port` | The server |
| `ssl` | `true` uses implicit TLS (port 465) |
| `starttls` | Without `ssl`, defaults to `true` (port 587) |
| `username` | Login; the password comes from `STREAMHUB_SMTP_PASSWORD` |
| `from` | Sender address |

## Issue reports

Reports go to the channels that receive `report`. When `smtp` is set, they are also emailed to the app's `developer` addresses, with the reporter's address as `Reply-To`. The report page tells the user whether the report was delivered.

## Delivery

Delivery never blocks or stops the hub. A failure is logged as a warning (with the webhook's host, never its URL) and counted in the `streamhub_notification_failures_total` metric. `--debug` turns every channel off, and the messages are only logged.
