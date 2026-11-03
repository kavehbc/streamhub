# Configuration overview

A hub is configured by a **config folder** that holds four JSON files. The admin page edits all of them, so you rarely need to open them, but they are plain files that you can keep in git, template, or generate.

| File | Holds | Reference |
|---|---|---|
| `streamhub.json` | Settings: port, branding, schedule, timeouts, sign-in, notifications. Every key is optional. | [Settings](settings.md) |
| `streamhub-apps.json` | The boards (first element) and every app | [Apps file](apps.md) |
| `streamhub-users.json` | Local users, their roles and boards, with password hashes | [Users file](users.md) |
| `streamhub-news.json` | Announcements | [News file](news.md) |

Secrets don't belong in these files: pass them as [environment variables](environment.md).

## The config folder

`streamhub run CONFIG` takes either the folder or the path of its `streamhub.json`. Without an argument, it uses `$STREAMHUB_CONFIG`, then the current folder.

- **Relative paths**, in the settings and in the apps file, start at the config folder.
- A folder **without `streamhub.json`** runs on the defaults. The first save of the Settings tab, or the setup page, creates the file.
- The file names of the apps, users and news files can be changed with the `apps`, `users` and `news` settings.

Besides the four files, the hub writes into the config folder:

| Path | What | Setting |
|---|---|---|
| `.streamhub-secret` | The cookie secret, generated when neither `STREAMHUB_COOKIE_SECRET` nor `cookie-secret` is set | `cookie-secret` |
| `.streamhub-sessions.sqlite3` | Sessions and revocations | `sessions-db` |
| `logs/` | `<app_id>.log` per app (the previous run as `.log.1`), `usage.sqlite3`, `processes.json` | `log-folder` |
| `temp/` | The public `/temp/` folder, emptied by every memory clean | `temp` |
| `backups/` | Copies of the files replaced by a restore | – |

With an `instance-id`, logs and temp files go to per-instance subfolders (`logs/<instance-id>`, `temp/<instance-id>`).

## Validate before you start

```console
$ streamhub check my-hub
warning: streamhub-apps.json: sales-forecast: board 'finance.brd' is not defined
warning: streamhub-apps.json: sales-forecast: file not found: /srv/my-hub/apps/forecast/main.py
my-hub: 0 error(s), 2 warning(s)
```

`streamhub check` runs every check without starting anything. It covers:

- the settings and the apps, users and news files;
- undefined boards;
- missing folders, files and tools;
- raw passwords;
- risky settings: secrets in the file, hub secrets passed to apps, `bind-check` off, and development-only SSO options.

It never prints secret values, and it exits with 1 on errors, so you can use it in CI. The admin page validates every save with the same checks.

## Applying changes

| You change | It applies |
|---|---|
| Apps, users or news file (on disk or on the admin page) | On the next request: the files are re-read when they change |
| `streamhub.json` on the admin page | At once, when you save |
| `streamhub.json` on disk | After **Reload configuration** (`/update/`) |

Most settings apply immediately, including the schedule. These need a restart, and both the Settings tab and Reload configuration name them:

`port`, `ssl_port`, `ssl-cert`, `ssl-key`, `behind-proxy`, `cdf`, `temp`, `log-folder`, `template-folder`, `cookie-secret`, `port-range`, `max-ws-message-mb`, `health-interval`, `instance-id`, `sessions-db`, `usage-retention-days`.

If an edit makes the apps or news file invalid, the hub logs the error, shows it on `/admin/`, and keeps the last good version. An invalid users file grants nothing until it is fixed ([Users file](users.md#when-the-users-file-is-invalid)).

## Examples in the package

| Folder | What |
|---|---|
| `streamhub/starter/` | What `streamhub init` writes: one public board, a link, the Help page and a welcome message |
| `streamhub/demo/config/` | The demo of `streamhub demo` |
