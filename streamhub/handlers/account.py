"""Login (local users, then LDAP) and logout."""
import asyncio

import tornado.web

from streamhub import auth
from streamhub.handlers.base import BaseHandler, safe_next

AUTH_CONCURRENCY = 8      # password checks (PBKDF2, LDAP) running at once
AUTH_QUEUE_SECONDS = 10   # how long a login waits for one before HTTP 503


class LoginHandler(BaseHandler):
    """Login form. Failed attempts are throttled per client IP and written to the audit log."""

    def _target(self):
        """Where to go after login: a board (?board=) or a same-site path (?next=)."""
        board = self.get_argument("board", "")
        if board and self.hub.catalog.board(board):
            return f"/{board}/"
        return safe_next(self.get_argument("next", "/"))

    def render_login(self, login_status=0):
        oidc = self.hub.settings.oidc
        setup = auth.needs_setup(self.hub.catalog, self.hub.settings)
        if setup:
            self.hub.announce_setup()  # so the link is near the end of the console
        self.render("login.html", target=self._target(), login_status=login_status, needs_setup=setup,
                    oidc_label=(oidc.get("label") or "Single sign-on") if oidc else "")

    def get(self):
        self.render_login(int(self.get_argument("error", "0") or 0))

    async def post(self):
        client = self.request.remote_ip
        throttle = self.hub.login_throttle
        # Reserved before checking the password, so concurrent attempts count at once.
        if not throttle.reserve(client):
            auth.audit.warning("login blocked for %s (too many failures)", client)
            raise tornado.web.HTTPError(429)
        try:
            # At most AUTH_CONCURRENCY password checks at a time across all clients.
            await asyncio.wait_for(self.hub.auth_slots.acquire(), timeout=AUTH_QUEUE_SECONDS)
        except asyncio.TimeoutError:
            throttle.cancel(client)
            raise tornado.web.HTTPError(503, reason="Too many logins in progress") from None

        username = self.get_argument("username", "")
        password = self.get_argument("password", "")
        try:
            user = await self._authenticate(username, password)
        except BaseException:
            throttle.cancel(client)
            raise
        finally:
            self.hub.auth_slots.release()
        if user is None:
            throttle.failed(client, reserved=True)
            self.hub.login_failures += 1
            auth.audit.warning("login failed for '%s' from %s", username, client)
            self.set_status(401)
            self.render_login(2)
            return

        throttle.succeeded(client, reserved=True)
        self.set_session(user)
        self.redirect(self._target())

    async def _authenticate(self, username, password):
        """A local user with the right password, else an LDAP user when LDAP is configured."""
        loop = asyncio.get_running_loop()
        local = await loop.run_in_executor(None, self.hub.catalog.user, username)  # may hash the env admin once
        if local is not None and local.source == "local":
            ok = local.password and await loop.run_in_executor(
                None, auth.verify_password, local.password, password, username)  # slow on purpose
            return local if ok else None
        settings = self.hub.settings
        if not settings.ldap:
            return None
        try:
            found = await loop.run_in_executor(None, auth.ldap_authenticate, settings.ldap,
                                               settings.ldap_bind_password, username, password)
        except ImportError:
            auth.log.error("LDAP is configured but ldap3 is not installed: pip install 'streamhub[ldap]'")
            return None
        except Exception as exc:
            auth.log.error("LDAP login for '%s' failed: %s", username, exc)
            return None
        if found is None:
            return None
        return auth.sso_user(found[0], "ldap", found[1], settings, self.hub.catalog)


class LogoutHandler(BaseHandler):
    """GET asks for confirmation; the POST (with XSRF token) logs out."""

    def get(self):
        self.render("confirm.html", command="Log out", action="/logout/", options=[])

    async def post(self):
        if self.current_user:
            auth.audit.info("logout '%s'", self.current_user.name)
            sid = self.session_id()
            if sid:
                await self.hub.sessions.revoke(sid)  # the cookie is now useless, even if it was copied
        self.clear_cookie("user")
        self.redirect("/")
