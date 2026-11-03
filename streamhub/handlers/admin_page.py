"""The /admin/ page and its JSON endpoints: server load, apps, logs, usage, CPU affinity, ports,
temp folder, and (admins only) the apps, users, news and settings editors, the JSON file editor and git.
Replaces the old status.cmd dashboard."""
import asyncio
import hashlib
import json
import sys
from pathlib import Path

import psutil
import tornado.web

from streamhub import auth, platform_utils
from streamhub.bootstrap import write_atomically
from streamhub.catalog import (DISPLAY_CHOICES, NEWS_CHOICES, RESERVED_IDS, RESTART_CHOICES, SERVES_CHOICES,
                               TYPE_CHOICES, TYPES)
from streamhub.config import (CHOICES, PACKAGE_DIR, RENAMED_LAYOUTS, config_keys, config_target, settings_form,
                              subforms)
from streamhub.notify import EVENTS
from streamhub.handlers.base import BaseHandler
from streamhub.validate import check_text

FILE_KEYS = ("config", "apps", "users", "news")
GIT_TIMEOUT = 120


def _json_body(handler):
    """The request body as a JSON object, or HTTP 400."""
    try:
        data = json.loads(handler.request.body or b"{}")
    except ValueError as exc:
        raise tornado.web.HTTPError(400, reason="Invalid JSON body") from exc
    if not isinstance(data, dict):
        raise tornado.web.HTTPError(400, reason="Expected a JSON object")
    return data


class _ManagerHandler(BaseHandler):
    """Every endpoint needs a manager; `admin_only` raises the bar to admin."""
    admin_only = False

    def prepare(self):
        super().prepare()
        self.require_role("admin" if self.admin_only else "manager")  # redirects (and finishes) or raises 403

    def app_or_404(self, app_id):
        app = self.hub.catalog.find(app_id)
        if app is None:
            raise tornado.web.HTTPError(404)
        return app


LAYOUTS = {"main.html": "Top menu", "main_side.html": "Sidebar menu on wide screens", "main_nomenu.html": "No menu"}


def layouts(settings):
    """[file, label] of the page layouts: the bundled ones and the main*.html of the template folder."""
    names = {p.name for folder in (settings.template_folder, PACKAGE_DIR / "templates")
             for p in Path(folder).glob("main*.html")}
    return [[name, LAYOUTS.get(name, name)] for name in sorted(names, key=lambda n: (list(LAYOUTS).index(n) if n in LAYOUTS else len(LAYOUTS), n))]


def admin_meta(settings):
    """What the admin page's editors offer: option lists, descriptions and the forms of the JSON objects."""
    from zoneinfo import available_timezones

    def pairs(options):
        return [list(option) for option in options]

    return {"reserved": RESERVED_IDS, "types": list(TYPES), "appTypes": pairs(TYPE_CHOICES),
            "serves": pairs(SERVES_CHOICES), "display": pairs(DISPLAY_CHOICES), "restart": pairs(RESTART_CHOICES),
            "newsTypes": pairs(NEWS_CHOICES), "layouts": layouts(settings), "renamedLayouts": RENAMED_LAYOUTS,
            "timezones": sorted(available_timezones()), "subforms": subforms(),
            "choices": {**{name: pairs(options) for name, options in CHOICES.items()},
                        "roles": [[role, auth.ROLE_HELP[role]] for role in auth.ROLES],
                        "events": [[event, event] for event in EVENTS]}}


class AdminPageHandler(_ManagerHandler):
    def get(self):
        # JSON inside <script type="application/json">: "<" escaped so no "</script>" can end it.
        form = json.dumps(settings_form()).replace("<", "\\u003c")
        meta = json.dumps(admin_meta(self.hub.settings)).replace("<", "\\u003c")
        self.render("admin.html", nav_active="admin", xsrf=self.xsrf_token.decode(),
                    instance=self.hub.settings.instance_id, settings_form=form, admin_meta=meta)


class EnvironmentsHandler(_ManagerHandler):
    """GET: the Python environments apps can use, as suggestions for the environment fields."""
    admin_only = True

    async def get(self):
        envs = await asyncio.get_running_loop().run_in_executor(None, platform_utils.conda_envs)
        self.write({"environments": [{"name": name, "path": str(path)} for name, path in sorted(envs.items())],
                    "conda": bool(platform_utils.conda_exe()), "hub": sys.executable})


class PathCheckHandler(_ManagerHandler):
    """GET ?path=…[&base=…]: whether a path exists on the server. Relative paths start at `base`, itself
    relative to the config folder, like the app's `folder`, `file` and the settings' paths."""
    admin_only = True

    def get(self):
        base = Path(self.hub.settings.config_dir) / Path(self.get_argument("base", "")).expanduser()
        path = (base / Path(self.get_argument("path")).expanduser()).resolve()
        self.set_header("Cache-Control", "no-store")
        self.write({"path": str(path), "exists": path.exists(), "dir": path.is_dir()})


def checklist(hub):
    """The admin dashboard's Getting started steps: (id, done, title, hint, tab)."""
    settings, catalog = hub.settings, hub.catalog
    file_users = [u for u in catalog.users().values() if u.source == "local"]
    apps = [a for a in catalog.all_apps() if a.kind != "cmd"]
    steps = [
        ("settings", settings.config_file is not None, "Save your settings",
         "Name your site and check the defaults; this creates streamhub.json.", "settings"),
        ("apps", any(a.launchable for a in apps), "Add your first app",
         "Point the hub at a Streamlit or Python app, or a Docker image.", "apps"),
        ("users", len(file_users) > 1 or bool(settings.oidc or settings.ldap), "Invite your team",
         "Add users, or connect single sign-on in Settings.", "users"),
        ("static", Path(settings.cdf_path).resolve() != (PACKAGE_DIR / "cdf").resolve(), "Keep your images safe",
         "Set the static folder in Settings, so logos and icons survive upgrades.", "settings"),
    ]
    if auth.demo_password_in_use():
        steps.insert(0, ("password", False, "Replace the demo admin password",
                         "Anyone can guess admin / admin: set STREAMHUB_ADMIN_PASSWORD, or add an admin on the Users tab.",
                         "users"))
    return [{"id": i, "done": done, "title": title, "hint": hint, "tab": tab} for i, done, title, hint, tab in steps]


class AdminStateHandler(_ManagerHandler):
    """Everything the page shows, refreshed every few seconds."""

    async def get(self):
        hub = self.hub
        rows = {}
        for app in hub.catalog.all_apps():
            if app.launchable or app.kind == "curl":
                rows[app.app_id] = {"app_id": app.app_id, "name": app.name, "runtime": app.runtime,
                                    "state": "not running", "auto_shutdown": app.auto_shutdown,
                                    "restart": app.restart, "health_path": app.health}
        loop = asyncio.get_running_loop()
        for app_id, inst in hub.manager.instances.items():
            memory, cpu = (await loop.run_in_executor(None, platform_utils.tree_stats, inst.pid)
                           if inst.pid else (None, None))
            row = rows.setdefault(app_id, {"app_id": app_id, "name": inst.app.name, "runtime": inst.app.runtime,
                                           "auto_shutdown": inst.app.auto_shutdown, "restart": inst.app.restart,
                                           "health_path": inst.app.health})
            row.update(state=inst.state, healthy=inst.healthy, pid=inst.pid, port=inst.port,
                       upstream=inst.upstream, sessions=inst.active_ws, memory_kb=memory, cpu_percent=cpu,
                       started=inst.started_at.isoformat(timespec="seconds"),
                       last_access=inst.last_access.isoformat(timespec="seconds") if inst.last_access else None,
                       exit_code=inst.exit_code, usage=inst.usage_today())
        temp_bytes, temp_files = await loop.run_in_executor(None, platform_utils.folder_size, hub.settings.temp_path)
        server = await loop.run_in_executor(None, platform_utils.server_stats)
        problems = [f"The {name} file is not in use: {error}" for name, error in hub.catalog.errors().items()]
        if auth.demo_password_in_use():
            problems.append("The admin password is the demo default 'admin': set STREAMHUB_ADMIN_PASSWORD.")
        self.set_header("Cache-Control", "no-store")
        self.write({"version": hub.version, "instance": hub.settings.instance_id, "problems": problems,
                    "checklist": checklist(hub) if self.current_user.role == "admin" else [],
                    "started": hub.started_at.isoformat(timespec="seconds"), "server": server,
                    "apps": sorted(rows.values(), key=lambda r: (r["state"] == "not running", r["app_id"])),
                    "temp": {"path": str(hub.settings.temp_path), "bytes": temp_bytes, "files": temp_files}})


class TempPurgeHandler(_ManagerHandler):
    """POST: empty the temp folder. Returns its size afterwards."""

    async def post(self):
        loop, hub = asyncio.get_running_loop(), self.hub
        await loop.run_in_executor(None, hub.purge_temp)
        size, count = await loop.run_in_executor(None, platform_utils.folder_size, hub.settings.temp_path)
        auth.audit.info("temp folder purged by %s (%s file(s) left)", self.current_user.name, count)
        self.write({"bytes": size, "files": count})


class PortsHandler(_ManagerHandler):
    async def get(self):
        try:
            rows = await asyncio.get_running_loop().run_in_executor(None, platform_utils.listening_ports)
        except psutil.AccessDenied:
            self.write({"ports": [], "error": "Listing sockets needs more privileges on this system."})
            return
        self.write({"ports": rows})


class AppLogHandler(_ManagerHandler):
    def get(self, app_id):
        self.app_or_404(app_id)
        limit = min(int(self.get_argument("bytes", "65536") or 65536), 1024 * 1024)
        self.set_header("Content-Type", "text/plain; charset=utf-8")
        self.set_header("Cache-Control", "no-store")
        self.write(self.hub.log_tail(self.hub.manager.get(app_id), app_id=app_id, limit=limit))


class AffinityHandler(_ManagerHandler):
    """Read or set the CPUs an app's root process may run on."""

    def _pid(self, app_id):
        inst = self.hub.manager.running(app_id)
        if inst is None or not inst.pid:
            raise tornado.web.HTTPError(409, reason="The app is not running")
        return inst.pid

    def get(self, app_id):
        self.write({"cpus": platform_utils.cpu_affinity(self._pid(app_id)), "count": psutil.cpu_count()})

    def post(self, app_id):
        cpus = _json_body(self).get("cpus")
        if not isinstance(cpus, list) or not all(isinstance(c, int) for c in cpus):
            raise tornado.web.HTTPError(400, reason="'cpus' must be a list of integers")
        try:
            applied = platform_utils.cpu_affinity(self._pid(app_id), cpus)
        except (ValueError, psutil.Error) as exc:
            raise tornado.web.HTTPError(400, reason=str(exc)[:200]) from exc
        auth.audit.info("CPU affinity of %s set to %s by %s", app_id, applied, self.current_user.name)
        self.write({"cpus": applied})


PASSWORD_MASK = "********"


def _local_users(data):
    """(name, entry) of users-file entries that hold a password."""
    return [(name, entry) for name, entry in data.items()
            if isinstance(entry, dict) and "password" in entry and entry.get("source", "local") == "local"]


def file_version(path):
    """Fingerprint of a file's content ("" when it does not exist), to detect concurrent edits."""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]
    except OSError:
        return ""


class FileHandler(_ManagerHandler):
    """Read or replace one of the hub's JSON files.

    A save is refused unless the content is valid for that file (the same checks as `streamhub check`),
    and with HTTP 409 when the file changed on disk since it was opened (`version`). It is written
    atomically. In the users file, passwords are never shown (PASSWORD_MASK instead) and never stored
    raw: on save, a masked value keeps the stored password, a hash is kept, and anything else is hashed.
    A saved config file is applied at once, like Reload configuration; `restart` lists the keys that
    still need a restart. The other files apply on the next request.
    """
    admin_only = True

    def _path(self, key):
        settings = self.hub.settings
        return Path({"config": config_target(settings), "apps": settings.apps_file, "users": settings.users_file,
                     "news": settings.news_file}[key])

    def get(self, key):
        path = self._path(key)
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        version = file_version(path)
        if key == "users" and text:
            try:
                data = json.loads(text)
            except ValueError:
                self.write({"path": str(path), "exists": True, "text": "", "version": version,
                            "error": "The users file is not valid JSON; fix it on disk (it is not shown, "
                                     "so no password is revealed)."})
                return
            for _, entry in _local_users(data) if isinstance(data, dict) else []:
                entry["password"] = PASSWORD_MASK
            text = json.dumps(data, indent=2)
        self.write({"path": str(path), "exists": path.is_file(), "text": text, "version": version,
                    "note": f"Passwords show as {PASSWORD_MASK}: keep it to leave a password unchanged, or type "
                            "a new one, which is hashed when you save." if key == "users" else ""})

    async def post(self, key):
        path = self._path(key)
        body = _json_body(self)
        text = body.get("text")
        if not isinstance(text, str):
            raise tornado.web.HTTPError(400, reason="'text' is required")
        if "version" in body and body["version"] != file_version(path):
            self._refuse(f"Not saved: {path.name} changed on disk since you opened it. Reload it, then apply "
                         "your changes again.", status=409)
            return
        errors, warnings = check_text(key, text, self.hub.settings)
        if errors:
            self._refuse(f"Not saved: {errors[0]}")
            return
        data = json.loads(text)
        hashed = []
        if key == "users":
            if not isinstance(data, dict):
                self._refuse("Not saved: the users file must be a JSON object")
                return
            try:
                stored = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
            except ValueError:
                stored = {}
            for name, entry in _local_users(data):
                if entry["password"] == PASSWORD_MASK:
                    previous = stored.get(name) if isinstance(stored, dict) else None
                    if not isinstance(previous, dict) or "password" not in previous:
                        self._refuse(f"Not saved: type a password for '{name}' (it has none yet)")
                        return
                    entry["password"] = previous["password"]  # unchanged; hashed below if it was still raw
            # Hashing is slow on purpose: keep it off the event loop.
            hashed = await asyncio.get_running_loop().run_in_executor(None, auth.hash_users, data)
            text = json.dumps(data, indent=2) + "\n"
        write_atomically(path, text)
        auth.audit.info("%s saved by %s%s", path, self.current_user.name,
                        f" (new password for {', '.join(hashed)})" if hashed else "")
        note, restart = "It applies on the next request.", []
        if key == "config":
            note, restart = self._apply_config()
        if hashed:
            note += f" Hashed the new password(s) of {', '.join(hashed)}."
        if warnings:
            note += " Warnings: " + "; ".join(warnings[:5]) + ("; …" if len(warnings) > 5 else "")
        self.write({"saved": True, "message": f"Saved {path.name}. {note}", "version": file_version(path),
                    "warnings": warnings, "restart": restart})

    def _apply_config(self):
        """Reload the saved config file into the running hub. Returns (note, keys that need a restart)."""
        try:
            restart = config_keys(self.hub.reload_settings())
        except Exception as exc:  # validated before saving, so only a race with another edit gets here
            return f"Not applied: {str(exc)[:300]}", []
        auth.audit.info("config reload by '%s' (saved from the admin page)", self.current_user.name)
        if restart:
            return f"Applied. These need a restart: {', '.join(restart)}.", restart
        return "Applied.", []

    def _refuse(self, error, status=400):
        self.set_status(status)
        self.write({"saved": False, "error": error})


class SessionsHandler(_ManagerHandler):
    """GET: the active sessions. POST {"id"}: revoke one; POST {"user", "source"}: revoke all of a user's."""
    admin_only = True

    async def get(self):
        rows = await asyncio.get_running_loop().run_in_executor(None, self.hub.sessions.active)
        self.set_header("Cache-Control", "no-store")
        self.write({"sessions": rows, "current": self.session_id()})

    async def post(self):
        body = _json_body(self)
        sessions = self.hub.sessions
        if isinstance(body.get("id"), str) and body["id"]:
            await sessions.revoke(body["id"])
            auth.audit.info("session %s… revoked by %s", body["id"][:6], self.current_user.name)
        elif isinstance(body.get("user"), str) and body.get("source") in ("local", *auth.SSO_SOURCES):
            await sessions.revoke_user(body["user"], body["source"])
            auth.audit.info("every session of '%s' (%s) revoked by %s", body["user"], body["source"],
                            self.current_user.name)
        else:
            raise tornado.web.HTTPError(400, reason="Give 'id', or 'user' and 'source'")
        self.write({"revoked": True})


class GitHandler(_ManagerHandler):
    """git status, pull, or commit + push in the config folder. Argument lists, never a shell.

    A commit includes only the config, apps and news files: never the users file, and never other files
    that happen to be in the folder.
    """
    admin_only = True

    def committed_files(self, folder):
        settings = self.hub.settings
        files = [settings.config_file, settings.apps_file, settings.news_file]
        return [str(Path(f).resolve()) for f in files
                if f and Path(f).is_file() and Path(f).resolve().is_relative_to(Path(folder).resolve())]

    async def post(self, action):
        settings = self.hub.settings
        folder = str(Path(settings.config_file or settings.apps_file).parent)
        message = str(_json_body(self).get("message") or "Update from the Streamhub admin page")[:500]
        files = self.committed_files(folder)
        steps = {
            "status": [["git", "-C", folder, "status"]],
            "pull": [["git", "-C", folder, "pull", "--ff-only"]],
            "push": [["git", "-C", folder, "add", "--", *files],
                     ["git", "-C", folder, "commit", "-m", message, "--", *files],
                     ["git", "-C", folder, "push"]],
        }[action]
        auth.audit.info("git %s in %s by %s", action, folder, self.current_user.name)
        output, ok = [], True
        for argv in steps:
            try:
                code, out = await platform_utils.run_command(argv, timeout=GIT_TIMEOUT)
            except FileNotFoundError:
                code, out = 127, "git is not installed"
            output.append(f"$ {' '.join(argv)}\n{out}")
            if code:
                ok = False
                break
        self.write({"ok": ok, "output": "\n".join(output)})
