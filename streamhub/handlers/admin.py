"""Hub administration: memory clean, config reload, restart, exit, API, metrics."""
import hmac
import os
import time

import tornado.web
from tornado.ioloop import IOLoop

from streamhub import auth
from streamhub.config import config_keys
from streamhub.handlers.base import BaseHandler
from streamhub.launcher import LaunchError

CLEAR_OPTIONS = [("all_apps", "Stop all running apps, including ones without auto_shutdown (admin only)", False),
                 ("run_auto_start", "Run auto-start apps afterwards", True),
                 ("rerun_apps", "Relaunch the apps that were running", False)]


def _flag(handler, name):
    """A checkbox form field as a bool."""
    return handler.get_argument(name, "0") not in ("", "0", "false")


class ClearHandler(BaseHandler):
    """Memory clean for any logged-in user; only admins may also stop apps without auto_shutdown."""

    def get(self):
        user = self.require_login()
        if user is None:
            return
        options = CLEAR_OPTIONS if auth.role_at_least(user, "admin") else CLEAR_OPTIONS[1:]
        self.render("confirm.html", command="Clear Memory", action="/clear/", options=options)

    async def post(self):
        user = self.require_login()
        if user is None:
            return
        all_apps = _flag(self, "all_apps") and auth.role_at_least(user, "admin")
        auth.audit.info("clear memory by '%s' (all_apps=%s)", user.name, all_apps)
        await self.hub.clean_memory(trigger=f"Manual ({user.name})", all_apps=all_apps,
                                    run_auto_start=_flag(self, "run_auto_start"),
                                    rerun_apps=_flag(self, "rerun_apps"))
        self.render("clear.html", all_apps=all_apps)


class _AdminActionHandler(BaseHandler):
    """Admin-only action: GET renders a confirmation page, subclasses implement the POST."""
    command = ""
    action = ""

    def get(self):
        if self.require_role("admin") is None:
            return
        self.render("confirm.html", command=self.command, action=self.action, options=[])


class RestartHandler(_AdminActionHandler):
    command, action = "Restart Streamhub", "/restart/"

    def post(self):
        user = self.require_role("admin")
        if user is None:
            return
        auth.audit.info("restart by '%s'", user.name)
        self.render("restart.html")
        # In the background, so this response is sent before the listeners close.
        IOLoop.current().spawn_callback(self.hub.shutdown, restart=True, trigger=f"Restart by {user.name}")


class ExitHandler(_AdminActionHandler):
    command, action = "Stop Streamhub", "/exit/"

    def post(self):
        user = self.require_role("admin")
        if user is None:
            return
        auth.audit.info("exit by '%s'", user.name)
        self.render("exit.html")
        IOLoop.current().spawn_callback(self.hub.shutdown, trigger=f"Exit by {user.name}")


class UpdateHandler(_AdminActionHandler):
    command, action = "Reload configuration", "/update/"

    def post(self):
        user = self.require_role("admin")
        if user is None:
            return
        auth.audit.info("config reload by '%s'", user.name)
        try:
            needs_restart = self.hub.reload_settings()
        except Exception as exc:
            self.render("message.html", title="Configuration not reloaded", message=str(exc))
            return
        message = "Configuration reloaded."
        if needs_restart:
            message += " These changes need a restart: " + ", ".join(config_keys(needs_restart)) + "."
        problems = self.hub.catalog.errors()
        if problems:
            message += " These files are not in use: " + "; ".join(problems.values()) + "."
        self.render("message.html", title="Configuration", message=message)


class LegacyCommandHandler(BaseHandler):
    """Old '/clear.cmd/', '/exit.cmd/' and '/restart.cmd/' URLs."""

    def get(self, name):
        self.redirect(f"/{name}/", permanent=True)


class ApiHandler(BaseHandler):
    """Hub paths and running apps. Admins, or the built-in tools via the internal token."""

    def get(self):
        if not self.has_internal_token() and self.require_role("admin") is None:
            return
        settings = self.hub.settings
        apps = [{"app_id": "Streamhub", "port": settings.port, "auto_shutdown": False, "pid": os.getpid(),
                 "stopped": False, "state": "running", "first_check": self.hub.started_at.isoformat(),
                 "last_check": None, "app_usage": [0] * 24, "active_sessions": 0, "log": None}]
        for app_id, inst in self.hub.manager.instances.items():
            apps.append({
                "app_id": app_id,
                "port": inst.port,
                "auto_shutdown": inst.app.auto_shutdown,
                "pid": inst.pid,
                "stopped": inst.state == "stopped",
                "state": inst.state,
                "first_check": inst.started_at.isoformat(),
                "last_check": inst.last_access.isoformat() if inst.last_access else None,
                "app_usage": inst.usage_today(),
                "active_sessions": inst.active_ws,
                "log": str(inst.log_file) if inst.log_file else None,
                "runtime": inst.runtime.name if inst.runtime else "external",
                "upstream": inst.upstream,
                "healthy": inst.healthy,
            })
        self.write({
            "streamhub": str(self.hub.package_root),
            "version": self.hub.version,
            "config": str(settings.config_file) if settings.config_file else None,
            "apps": str(settings.apps_file),
            "users": str(settings.users_file),
            "news": str(settings.news_file),
            "cdf": str(settings.cdf_path),
            "cdf_temp": str(settings.temp_path),
            "logs": str(settings.log_path),
            "slack_channel": settings.slack_name,
            "scheduled": settings.schedule,
            "timezone": settings.timezone,
            "instance": settings.instance_id,
            "proxy_map": apps,
        })


class AppControlHandler(BaseHandler):
    """POST /api/apps/<id>/start|stop|restart. Managers, or the built-in tools via the internal token."""

    def check_xsrf_cookie(self):
        if not self.has_internal_token():  # tools call with the token and have no XSRF cookie
            super().check_xsrf_cookie()

    async def post(self, app_id, action):
        if not self.has_internal_token() and self.require_role("manager") is None:
            return
        app = self.hub.catalog.find(app_id)
        if app is None:
            raise tornado.web.HTTPError(404)
        who = self.current_user.name if self.current_user else "a built-in tool"
        auth.audit.info("%s %s by %s", action, app_id, who)
        if action in ("stop", "restart"):
            await self.hub.manager.stop(app_id)
        if action in ("start", "restart"):
            self.hub.manager.forget(app_id)  # a crashed instance would otherwise block start()
            try:
                await self.hub.manager.start(app)
            except LaunchError as exc:
                raise tornado.web.HTTPError(500, reason=str(exc)[:200].replace("\n", " ")) from exc
        inst = self.hub.manager.get(app_id)
        self.write({"app_id": app_id, "state": inst.state if inst else "not running"})


class HealthHandler(tornado.web.RequestHandler):
    """Liveness probe for Docker, Kubernetes and load balancers. Public, no session needed."""

    def initialize(self, hub):
        self.hub = hub

    def get(self):
        self.write({"status": "ok", "instance": self.hub.settings.instance_id, "version": self.hub.version})


def _label(value):
    """A Prometheus label value: backslash, double quote and newline escaped."""
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


class MetricsHandler(BaseHandler):
    """GET /metrics: Prometheus text format. A manager session, or `Authorization: Bearer <STREAMHUB_METRICS_TOKEN>`.

    No user names, emails or URLs are exposed: only app IDs, channel types and counts.
    """

    def check_access(self):
        token = self.hub.settings.metrics_token
        header = self.request.headers.get("Authorization", "")
        if token and header.startswith("Bearer ") and hmac.compare_digest(header[7:].strip(), token):
            return True
        if auth.role_at_least(self.current_user, "manager"):
            return True
        self.set_status(403 if self.current_user else 401)
        if not self.current_user:
            self.set_header("WWW-Authenticate", 'Bearer realm="streamhub"')
        self.finish()
        return False

    def get(self):
        if not self.check_access():
            return
        hub, manager = self.hub, self.hub.manager
        lines = []

        def metric(name, kind, help_text, samples):
            lines.append(f"# HELP streamhub_{name} {help_text}")
            lines.append(f"# TYPE streamhub_{name} {kind}")
            for labels, value in samples:
                rendered = ",".join(f'{key}="{_label(val)}"' for key, val in labels.items())
                lines.append(f"streamhub_{name}{{{rendered}}} {value}" if rendered else f"streamhub_{name} {value}")

        instances = manager.instances
        metric("info", "gauge", "Hub version and instance.",
               [({"version": hub.version, "instance": hub.settings.instance_id}, 1)])
        metric("uptime_seconds", "gauge", "Seconds since the hub started.",
               [({}, round(time.monotonic() - hub.started_mono, 1))])
        metric("app_requests_total", "counter", "Page loads and WebSocket sessions per app, kept across restarts.",
               [({"app": app_id}, usage.total) for app_id, usage in sorted(manager.usage.apps.items())])
        metric("app_up", "gauge", "1 when the app is ready to serve requests.",
               [({"app": app_id}, int(inst.ready)) for app_id, inst in sorted(instances.items())])
        metric("app_healthy", "gauge", "0 after the app failed its health checks.",
               [({"app": app_id}, int(inst.healthy)) for app_id, inst in sorted(instances.items())])
        metric("app_sessions", "gauge", "Open WebSocket sessions per app.",
               [({"app": app_id}, inst.active_ws) for app_id, inst in sorted(instances.items())])
        metric("app_restarts", "gauge", "Automatic restarts of the app in its current backoff run.",
               [({"app": app_id}, inst.restarts) for app_id, inst in sorted(instances.items())])
        metric("app_ready_seconds", "gauge", "Time from launch to ready of the app's current instance.",
               [({"app": app_id}, inst.ready_seconds) for app_id, inst in sorted(instances.items())
                if inst.ready_seconds is not None])
        metric("app_start_failures_total", "counter", "Launches that failed or timed out since the hub started.",
               [({"app": app_id}, count) for app_id, count in sorted(manager.failures.items())])
        metric("notification_failures_total", "counter", "Notifications not delivered, per channel type.",
               [({"channel": kind}, count) for kind, count in sorted(hub.notifier.failures.items())])
        metric("login_failures_total", "counter", "Failed logins since the hub started.",
               [({}, hub.login_failures)])
        metric("config_errors", "gauge", "1 for each catalog file that is currently invalid.",
               [({"file": name}, 1) for name in sorted(hub.catalog.errors())])
        self.set_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.set_header("Cache-Control", "no-store")
        self.write("\n".join(lines) + "\n")
