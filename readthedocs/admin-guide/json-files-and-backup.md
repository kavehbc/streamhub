# JSON files and backup

## JSON files

The **JSON files** tab edits the four configuration files as text: **Config** (`streamhub.json`), **Apps**, **Users** and **News**.

```{figure} /_static/screenshots/admin-files.png
:alt: The JSON editor showing streamhub-apps.json
:class: screenshot

The JSON editor.
```

- The editor says as you type whether the text is valid JSON. **Format** re-indents it, and **Ctrl+S** saves.
- A save is validated like `streamhub check`, and its warnings are shown. It is refused (409) if the file changed on disk since you opened it, and it is written atomically. A saved config applies at once, and the page lists the keys that need a restart.
- **Reload from disk** discards your edits.
- In the users file, passwords show as `********`. Keeping `********` leaves a password unchanged; typing a new value stores its hash.

### Git

When the config folder is a git repository, the **Git** card shows its status and can **pull**, and **commit and push** with a message. A commit includes only the config, apps and news files, never the users file or anything else in the folder.

## Backup and restore

The **Backup** tab saves and restores the four files at once.

```{figure} /_static/screenshots/admin-backup.png
:alt: The Backup tab
:class: screenshot

The Backup tab.
```

- **Download backup** gives one JSON file with `streamhub.json` and the apps, users and news files, as they are on disk. It holds the password hashes and any secret written in the config, so keep it somewhere safe. Static files are not included.
- **Choose a backup file** reads such a file and lets you pick which files to restore. Each file is checked first, and if any of them is invalid, nothing changes. The current files are copied to `<config>/backups/` before they are replaced, raw passwords are hashed, and a restored config applies at once.

For automated backups, copy the config folder itself, or call `GET /api/admin/backup` as an admin ([Endpoints](../reference/endpoints.md)).
