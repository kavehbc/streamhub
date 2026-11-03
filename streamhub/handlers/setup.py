"""The first-run setup page. While the hub has no admin (auth.needs_setup), the start page redirects here, and
/setup/?token=… (the link the hub logs at startup) creates the first admin account, names the site and signs the
new admin in. Without the token, the page says where to find the link. Afterwards, 404."""
import asyncio
import hmac
import re

import tornado.web

from streamhub import auth, bootstrap, platform_utils
from streamhub.config import config_target
from streamhub.handlers.base import BaseHandler

MIN_PASSWORD = 8
USER_NAME = re.compile(r"[A-Za-z0-9._@-]{1,64}")


class SetupHandler(BaseHandler):
    def prepare(self):
        super().prepare()
        if not auth.needs_setup(self.hub.catalog, self.hub.settings):
            raise tornado.web.HTTPError(404)

    def _given(self):
        """The token of the request; a pasted setup link works too."""
        given = self.get_argument("token", "").strip()
        return given.split("token=", 1)[1].split("&", 1)[0] if "token=" in given else given

    def _token(self):
        """The token of the request when it is the hub's, else ""."""
        token = self._given()
        return token if token and hmac.compare_digest(token.encode(), self.hub.setup_token.encode()) else ""

    def _show(self, token, error="", status=200):
        """The form. Without a valid token in the request, it starts with a token field and says where to find it."""
        self.set_status(status)
        self.render("setup.html", token=token, given="" if token else self._given(), error=error,
                    min_password=MIN_PASSWORD, container=platform_utils.container_name(),
                    username=self.get_argument("username", "admin"),
                    site=self.get_argument("site_title", self.hub.settings.site_title),
                    team=self.get_argument("team_name", self.hub.settings.team_name))

    def _wrong_token(self):
        self.hub.announce_setup()
        self._show("", error="That setup token is not this hub's. Copy it again from the hub's log.", status=403)

    def get(self):
        """The start page sends a new hub here: with the token from the link, or a field to paste it in."""
        token = self._token()
        if not token and self._given():
            self._wrong_token()
            return
        if not token:
            self.hub.announce_setup()
        self._show(token)

    async def post(self):
        token = self._token()
        if not token:
            self._wrong_token()
            return
        name = self.get_argument("username", "").strip()
        password = self.get_argument("password", "")
        site, team = self.get_argument("site_title", "").strip(), self.get_argument("team_name", "").strip()
        if not USER_NAME.fullmatch(name):
            error = "The user name takes 1-64 letters, digits and . _ @ -"
        elif len(password) < MIN_PASSWORD:
            error = f"The password needs {MIN_PASSWORD} characters or more."
        elif password != self.get_argument("confirm", ""):
            error = "The passwords do not match."
        else:
            error = ""
        if error:
            self._show(token, error, status=400)
            return
        hub = self.hub
        async with hub.setup_lock:
            if not auth.needs_setup(hub.catalog, hub.settings):  # another browser finished first
                raise tornado.web.HTTPError(404)
            # Hashing is slow on purpose: keep it off the event loop.
            await asyncio.get_running_loop().run_in_executor(None, bootstrap.add_admin, hub.settings.users_file,
                                                             name, password)
            if site != hub.settings.site_title or team != hub.settings.team_name:
                bootstrap.update_config(config_target(hub.settings), **{"site-title": site or None,
                                                                        "team-name": team or None})
                hub.reload_settings()
        auth.audit.info("first admin '%s' created on the setup page from %s", name, self.request.remote_ip)
        self.set_session(hub.catalog.user(name))
        self.redirect("/admin/")
