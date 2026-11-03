"""Launching apps, their status, output and developer contacts."""
import re

import tornado.web

from streamhub import auth
from streamhub.handlers.base import BaseHandler
from streamhub.launcher import STOPPED, LaunchError

BLANK_ICON = "/cdf/streamhub/blank_transparent_icon.png"
MAX_REPORT = 5000


class AppHandlerMixin:
    """Access check shared by the handlers that act on one app."""

    def accessible_app(self, app_id):
        """The catalog entry for `app_id` if the current user may use it; otherwise redirects or raises."""
        app = self.hub.catalog.find(app_id)
        if app is None or app.kind == "internal":
            raise tornado.web.HTTPError(404)
        if not auth.can_access_app(self.current_user, app, self.hub.catalog):
            if self.current_user is None:
                self.redirect(self.login_url())
                return None
            raise tornado.web.HTTPError(403)
        return app


class LaunchHandler(AppHandlerMixin, BaseHandler):
    """Reached for '/<app_id>/...' while the app is not running (running apps are matched by the proxy)."""

    async def get(self, app_id, rest=""):
        app = self.accessible_app(app_id)
        if app is None:
            return
        if app.kind == "url":
            self.redirect(app.url)
            return

        manager = self.hub.manager
        if self.hub.draining:
            raise tornado.web.HTTPError(503, reason="Streamhub is stopping")
        inst = manager.get(app_id)
        if inst is not None and inst.state == STOPPED:
            manager.forget(app_id)
            self.set_status(503)
            reason = inst.error or f"The app stopped (exit code {inst.exit_code})."
            self.render("error.html", app=app, port=inst.port, log_tail=self.hub.log_tail(inst),
                        message=f"{reason} Refresh to start it again.")
            return
        if inst is None:
            try:
                inst = await manager.start(app)
            except LaunchError as exc:
                self.set_status(500)
                self.render("error.html", app=app, port=0, log_tail="", message=str(exc))
                return
        if inst.ready:
            self.redirect(self.request.uri)  # the proxy route takes it from here
            return
        self.render("loading.html", app=app, port=inst.port)

    async def post(self, app_id, rest=""):
        raise tornado.web.HTTPError(503, reason="App is not running")

    put = patch = delete = post


class AppRedirectHandler(BaseHandler):
    """'/<app_id>' -> '/<app_id>/'."""

    def get(self, app_id):
        if self.hub.catalog.find(app_id) is None:
            raise tornado.web.HTTPError(404)
        self.redirect(f"/{app_id}/")


class AppStatusHandler(AppHandlerMixin, BaseHandler):
    """Polled by the loading page until the app is ready."""

    def get(self, app_id):
        if self.accessible_app(app_id) is None:
            return
        inst = self.hub.manager.get(app_id)
        self.write({"app_id": app_id,
                    "state": inst.state if inst else "not running",
                    "ready": bool(inst and inst.ready),
                    "error": inst.error if inst else ""})


class OutHandler(AppHandlerMixin, BaseHandler):
    """Tail of an app's combined stdout/stderr log."""

    def get(self, app_id):
        if self.require_login() is None or self.accessible_app(app_id) is None:
            return
        inst = self.hub.manager.get(app_id)
        self.render("out.html", appid=app_id, output=self.hub.log_tail(inst, app_id=app_id))


class AppListHandler(BaseHandler):
    """GET /api/apps: the apps the current user can open, with their state (landing-page badges)."""

    def get(self):
        user, catalog = self.current_user, self.hub.catalog
        rows = []
        for app in catalog.all_apps():
            if app.display == "hidden" or app.kind == "internal" or not auth.can_access_app(user, app, catalog):
                continue
            inst = self.hub.manager.get(app.app_id)
            state = {"url": "link", "curl": "external"}.get(app.kind, inst.state if inst else "not running")
            rows.append({"app_id": app.app_id, "name": app.name, "icon": app.icon or BLANK_ICON, "href": app.href,
                         "boards": app.boards, "display": app.display, "state": state,
                         "healthy": inst.healthy if inst else None})
        self.set_header("Cache-Control", "no-store")
        self.write({"apps": rows})


class ReportHandler(BaseHandler):
    """Developer contacts, and a form that sends the report to the `report` notifiers and the developers."""

    def _app(self):
        app = self.hub.catalog.find(self.get_argument("id", ""))
        if app is None or app.kind == "internal":
            raise tornado.web.HTTPError(404)
        return app

    def get(self):
        self.render("report.html", app=self._app(), outcome="", error="", message="", contact="")

    async def post(self):
        app = self._app()
        client = self.request.remote_ip
        throttle = self.hub.report_throttle
        if throttle.blocked(client):
            raise tornado.web.HTTPError(429)
        message = self.get_argument("message", "").strip()
        contact = re.sub(r"[\r\n]+", " ", self.get_argument("contact", "")).strip()[:200]
        error = ""
        if not message:
            error = "Describe the problem first."
        elif len(message) > MAX_REPORT:
            error = f"The description is limited to {MAX_REPORT} characters."
        if error:
            self.set_status(400)
            self.render("report.html", app=app, outcome="", error=error, message=message, contact=contact)
            return
        throttle.failed(client)  # every report counts toward the limit
        who = self.current_user.name if self.current_user else "an anonymous user"
        text = (f":memo: Issue reported for {app.name} ({app.app_id}) by {who} from {client}"
                + (f", contact: {contact}" if contact else "") + f"\n\n{message}")
        auth.audit.info("issue report for %s by %s from %s", app.app_id, who, client)
        delivery = await self.hub.notifier.send(
            text, event="report", subject=f"{self.hub.settings.site_title}: issue with {app.name}",
            to=[email for _, email in app.developers if email], reply_to=contact if "@" in contact else None)
        outcome = delivery.status  # sent, partial, failed, none or disabled
        auth.audit.info("issue report for %s: %s", app.app_id, outcome)
        if outcome in ("failed", "none"):
            self.set_status(502 if outcome == "failed" else 503)
            self.render("report.html", app=app, outcome=outcome, error="", message=message, contact=contact)
            return
        self.render("report.html", app=app, outcome=outcome, error="", message="", contact="")
