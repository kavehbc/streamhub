"""The admin page's Backup tab: download the hub's JSON files as one file, and restore them (admins only).

A backup holds the text of the config, apps, users and news files as they are on disk, password hashes and
any secrets in the config included. A restore validates every file it is given (like `streamhub check`) before
writing any, keeps a copy of the current files in `<config>/backups/`, hashes raw passwords, writes each file
atomically and applies a restored config at once.
"""
import asyncio
import json
from datetime import datetime
from pathlib import Path

from streamhub import auth
from streamhub.config import config_keys, config_target
from streamhub.handlers.admin_page import FILE_KEYS, _json_body, _ManagerHandler, write_atomically
from streamhub.validate import check_text

FORMAT = 1
BACKUP_FOLDER = "backups"


def hub_files(settings):
    """{key: path} of the files a backup holds; a hub without a config file gets one on restore."""
    return {"config": config_target(settings), "apps": settings.apps_file, "users": settings.users_file,
            "news": settings.news_file}


def snapshot(hub):
    """The backup document of the hub's files as they are now."""
    files = {}
    for key, path in hub_files(hub.settings).items():
        path = Path(path) if path else None
        files[key] = {"name": path.name if path else None,
                      "text": path.read_text(encoding="utf-8") if path and path.is_file() else None}
    return {"streamhub-backup": FORMAT, "version": hub.version, "instance": hub.settings.instance_id,
            "created": datetime.now().isoformat(timespec="seconds"), "files": files}


class BackupHandler(_ManagerHandler):
    """GET: the backup as a download."""
    admin_only = True

    def get(self):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        auth.audit.info("backup downloaded by %s", self.current_user.name)
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.set_header("Content-Disposition", f'attachment; filename="streamhub-backup-{stamp}.json"')
        self.set_header("Cache-Control", "no-store")
        self.write(json.dumps(snapshot(self.hub), indent=1))


class RestoreHandler(_ManagerHandler):
    """POST {"backup": <backup document>, "files": [keys]}: restore those files, or none if any is invalid."""
    admin_only = True

    async def post(self):
        body = _json_body(self)
        backup, wanted = body.get("backup"), body.get("files")
        if not isinstance(backup, dict) or backup.get("streamhub-backup") != FORMAT or not isinstance(backup.get("files"), dict):
            self.refuse("This is not a Streamhub backup file")
            return
        if not isinstance(wanted, list) or not wanted or not set(wanted) <= set(FILE_KEYS):
            self.refuse(f"Choose the files to restore: {', '.join(FILE_KEYS)}")
            return
        settings, targets, texts = self.hub.settings, hub_files(self.hub.settings), {}
        for key in wanted:
            entry = backup["files"].get(key)
            text = entry.get("text") if isinstance(entry, dict) else None
            if not isinstance(text, str):
                self.refuse(f"The backup has no {key} file")
                return
            errors, _ = check_text(key, text, settings)
            if errors:
                self.refuse(f"Nothing restored: the {key} file is invalid: {errors[0]}")
                return
            texts[key] = text
        if "users" in texts:  # hashing is slow on purpose: off the event loop
            users = json.loads(texts["users"])
            await asyncio.get_running_loop().run_in_executor(None, auth.hash_users, users)
            texts["users"] = json.dumps(users, indent=2) + "\n"
        safety = self.save_current()
        for key, text in texts.items():
            write_atomically(Path(targets[key]), text)
        auth.audit.info("restore of %s by %s (previous files in %s)", ", ".join(texts), self.current_user.name, safety)
        message, restart = f"Restored {', '.join(texts)}. The previous files are in {safety}.", []
        if "config" in texts:
            try:
                restart = config_keys(self.hub.reload_settings())
            except Exception as exc:  # validated above, so only a race with another edit gets here
                message += f" The config was not applied: {str(exc)[:300]}"
            else:
                message += f" These need a restart: {', '.join(restart)}." if restart else " The config is applied."
        self.write({"ok": True, "message": message, "restart": restart, "safety": str(safety)})

    def save_current(self):
        """A backup of the files as they are now, in <config>/backups/, before they are replaced."""
        folder = Path(self.hub.settings.config_dir) / BACKUP_FOLDER
        folder.mkdir(exist_ok=True)
        path = folder / f"streamhub-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}-before-restore.json"
        path.write_text(json.dumps(snapshot(self.hub), indent=1), encoding="utf-8")
        return path

    def refuse(self, error):
        self.set_status(400)
        self.write({"ok": False, "error": error})
