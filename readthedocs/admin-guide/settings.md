# Settings

The **Settings** tab edits `streamhub.json`. Every setting has a hint, and its default is shown in gray as the placeholder: **an empty field uses the default**. Keys the form doesn't show are kept.

```{figure} /_static/screenshots/admin-settings.png
:alt: The Settings tab, Branding section
:class: screenshot

The Settings tab.
```

**Save and apply** validates the whole file and applies it at once. Settings marked *restart* apply after a restart: the page lists them after the save and offers **Restart now**. **Discard changes** reverts the form. Without a `streamhub.json`, the first save creates it.

A setting that an environment variable overrides (for example `STREAMHUB_SLACK_HOOK`) is read-only, and names the variable.

## Sections

| Section | Settings | Reference |
|---|---|---|
| **Branding** | Site title, team name, logo (with an image picker and upload), footer, layout (top menu, sidebar or no menu), template folder | [Branding](../configuration/settings.md#branding-and-layout) |
| **Server** | Server URL, HTTP and HTTPS ports, TLS certificate and key, behind a reverse proxy, instance ID, app port range, reserved ports, upload and WebSocket limits, proxy timeout | [Server](../configuration/settings.md#server-and-network) |
| **Apps** | Default Python environment (suggested as you type), idle, startup, stop and drain timeouts, health checks, bind check, environment passthrough, Streamlit user headers, Kubernetes namespace | [Apps](../configuration/settings.md#apps-defaults-and-timeouts) |
| **Docker** | Docker socket, Docker network | [Docker](../configuration/settings.md#docker-and-kubernetes) |
| **Schedule and files** | Daily memory clean and its time zone (suggested as you type), the paths of the apps, users and news files, the static, temp and log folders, the sessions database, usage retention | [Schedule and files](../configuration/settings.md#schedule-and-files) |
| **Sign-in** | Session lifetime, SSO session limit, cookie secret, SSO default role, OpenID Connect, LDAP, group mapping | [Sign-in](../configuration/settings.md#sign-in-and-sessions) |
| **Notifications** | Slack webhook and channel name, notification channels, mail server | [Notifications](../configuration/notifications.md) |

Paths are checked on the server as you type: the field says whether the file or folder exists. Relative paths start at the config folder.

## Forms for nested settings

OpenID Connect, LDAP, the mail server, the notification channels and the group mapping are forms rather than JSON. Lists such as channels and mapping rules have repeatable rows. **Edit as JSON** switches a form to its JSON text, for keys the form doesn't know.

```{figure} /_static/screenshots/admin-settings-full.png
:alt: The whole Settings tab, every section
:class: screenshot

All the sections of the Settings tab.
```
