# The admin panel

The admin panel, at `/admin/`, is where you monitor and configure a hub in the browser. Open it from the account menu: each section has its own entry, and its own address (`/admin/#apps`, `/admin/#users`…).

```{figure} /_static/screenshots/admin-dashboard.png
:alt: The admin panel's dashboard with the section menu at the left
:class: screenshot

The admin panel. The section menu at the left collapses to icons; on a phone it becomes a scrolling strip.
```

## Who sees what

| Section | Manager | Admin | Page |
|---|:-:|:-:|---|
| Dashboard | ✓ | ✓ | [Dashboard and network](dashboard.md) |
| Network | ✓ | ✓ | [Dashboard and network](dashboard.md#network) |
| Apps (and boards) | | ✓ | [Apps and boards](apps-and-boards.md) |
| Users | | ✓ | [Users and sessions](users-and-sessions.md) |
| News | | ✓ | [News](news.md) |
| Settings | | ✓ | [Settings](settings.md) |
| Docker | | ✓ | [Docker](docker.md) |
| Static files | | ✓ | [Static files](static-files.md) |
| Sessions | | ✓ | [Users and sessions](users-and-sessions.md#sessions) |
| JSON files (and git) | | ✓ | [JSON files and backup](json-files-and-backup.md) |
| Backup | | ✓ | [JSON files and backup](json-files-and-backup.md#backup-and-restore) |

```{figure} /_static/screenshots/phone-admin.png
:alt: The admin dashboard on a phone
:class: screenshot phone

On a phone, the sections become a scrolling strip and the app table turns into cards.
```

Users and guests don't see the panel. The hub actions of the account menu (Clear memory, Reload configuration, Restart hub, Stop hub) are described in [Hub actions](hub-actions.md).

## How the editors save

The Apps, Users, News and Settings tabs are forms over the hub's JSON files. Every save:

- is **validated** like `streamhub check`, and refused with the reason when something is wrong;
- writes **only the fields you changed**, and keeps keys the form doesn't show;
- is refused (409) when the file changed on disk since you opened it, so two admins can't overwrite each other;
- is written **atomically**: readers see the old file or the new one, never half a file;
- applies **at once**. Apps, users and news apply on the next request. A saved `streamhub.json` is applied immediately, and the page names the keys that need a restart, with a **Restart now** button.

Every admin action is written to the `streamhub.audit` log.

## Getting started checklist

Until its steps are done, or you click **Hide**, the dashboard shows a **Getting started** checklist for admins:

1. **Replace the demo admin password** (only while `admin` / `admin` is in use).
2. **Save your settings**, which creates `streamhub.json`.
3. **Add your first app.**
4. **Invite your team**: add users, or connect single sign-on.
5. **Keep your images safe**: point the static folder (`cdf`) at a folder of your config, so uploaded logos and icons survive upgrades.

## Problems banner

When a catalog file is invalid, for example after a bad edit on disk, a red banner at the top of the panel names the file and the error. The hub keeps using the last good apps and news files. An invalid **users** file is different: it grants nothing until it is fixed, and only the `STREAMHUB_ADMIN_PASSWORD` admin can still log in. See [Users file](../configuration/users.md).
