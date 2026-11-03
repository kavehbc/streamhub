"""Shared handler base: template loader, page namespace, auth guards, session and instance cookies."""
import hmac
import logging
from pathlib import Path
from urllib.parse import quote, urlsplit

import tornado.template
import tornado.web
from tornado.ioloop import IOLoop

from streamhub import __version__, auth

log = logging.getLogger(__name__)

INSTANCE_COOKIE = "streamhub_instance"


def set_instance_cookie(handler, hub):
    """Pins the browser to this hub instance: the load balancer routes on this cookie."""
    instance = hub.settings.instance_id
    if instance and handler.get_cookie(INSTANCE_COOKIE) != instance:
        handler.set_cookie(INSTANCE_COOKIE, instance, httponly=True, samesite="Lax",
                           secure=handler.request.protocol == "https")


class ChainLoader(tornado.template.BaseLoader):
    """Looks up templates in a custom folder first, then in the bundled one."""

    def __init__(self, folders, **kwargs):
        super().__init__(**kwargs)
        self.folders = [Path(f) for f in folders if f]

    def resolve_path(self, name, parent_path=None):
        return name

    def _create_template(self, name):
        for folder in self.folders:
            path = folder / name
            if path.is_file():
                return tornado.template.Template(path.read_bytes(), name=name, loader=self)
        raise FileNotFoundError(f"Template not found: {name}")


def safe_next(target, default="/"):
    """Only same-site absolute paths are allowed as post-login redirects."""
    if not target or "\\" in target:
        return default
    parts = urlsplit(target)
    if parts.scheme or parts.netloc or not target.startswith("/") or target.startswith("//"):
        return default
    return target


class UiMixin:
    """Template variables shared by every page, including proxy error pages."""

    def get_template_namespace(self):
        namespace = super().get_template_namespace()
        settings = self.hub.settings
        user = self.current_user
        catalog = self.hub.catalog
        namespace.update(
            site_title=settings.site_title,
            team_name=settings.team_name,
            logo=settings.logo,
            footer=settings.footer,
            version=__version__,
            user=user,
            current_user=user.name if user else None,
            # the top navigation (_nav.html), on every page
            nav_boards=[(b, auth.can_view_board(user, b)) for b in catalog.boards],
            nav_has_news=bool(catalog.news()),
            nav_active="",  # "home", "news", "admin" or a board name; set by the page
            is_manager=auth.role_at_least(user, "manager"),
            is_admin=auth.role_at_least(user, "admin"),
        )
        return namespace


class BaseHandler(UiMixin, tornado.web.RequestHandler):
    """Base of every hub page and API handler."""

    def initialize(self, hub):
        self.hub = hub

    def prepare(self):
        set_instance_cookie(self, self.hub)

    def get_current_user(self):
        return self.hub.user_from_cookie(self)

    def set_session(self, user):
        """Log `user` in (any source) with a new, revocable session, and audit it."""
        sessions = self.hub.sessions
        sid = sessions.new_id()
        self.set_signed_cookie("user", auth.session_value(user, sid), expires_days=self.hub.settings.session_days,
                               httponly=True, samesite="Lax", secure=self.request.protocol == "https")
        IOLoop.current().spawn_callback(sessions.created, sid, user, self.request.remote_ip,
                                        self.request.headers.get("User-Agent", ""))
        auth.audit.info("login '%s' (%s, %s) from %s", user.name, user.role, user.source, self.request.remote_ip)

    def session_id(self):
        value = self.get_signed_cookie("user", max_age_days=self.hub.settings.session_days)
        return auth.session_meta(value.decode())[0] if value else None

    def has_internal_token(self):
        """True for calls from built-in tools, which receive the token in STREAMHUB_INTERNAL_TOKEN."""
        token = self.request.headers.get("X-Streamhub-Token", "")
        return bool(token) and hmac.compare_digest(token, self.hub.internal_token)

    def login_url(self):
        return "/login/?next=" + quote(self.request.uri, safe="/")

    def require_login(self):
        """Returns the user, or redirects to the login page and returns None."""
        if self.current_user is None:
            self.redirect(self.login_url())
        return self.current_user

    def require_role(self, role):
        """Like require_login, and raises 403 below `role`."""
        user = self.require_login()
        if user is None:
            return None
        if not auth.role_at_least(user, role):
            raise tornado.web.HTTPError(403)
        return user

    def write_error(self, status_code, **kwargs):
        """Friendly error page; tracebacks only with --debug (serve_traceback)."""
        messages = {403: "You are not allowed to do this.", 404: "Nothing here.",
                    429: "Too many attempts. Try again later."}
        self.render("message.html", title=f"{status_code} {self._reason}",
                    message=messages.get(status_code, "Something went wrong."))
