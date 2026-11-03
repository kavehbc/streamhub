"""The Hub: owns every piece of runtime state, the route table and the lifecycle."""
import asyncio
import logging
import os
import secrets
import shutil
import ssl
import subprocess
import sys
import time
from dataclasses import fields
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import tornado.httpclient
import tornado.httpserver
import tornado.ioloop
import tornado.web

from streamhub import __version__, auth, catalog as catalog_mod, platform_utils
from streamhub.config import PACKAGE_DIR, RESTART_ONLY, load_settings
from streamhub.handlers import (account, admin, admin_page, apps, backup_admin, cdf_admin, docker_admin, pages,
                                setup, sso)
from streamhub.handlers.base import ChainLoader
from streamhub.launcher import AppManager, LaunchError, safe_name
from streamhub.notify import Notifier
from streamhub.ports import PortAllocator
from streamhub.proxy import ProxyHTTPHandler, ProxyWSHandler, RunningAppMatcher
from streamhub.scheduler import DailyJob
from streamhub.sessions import REFRESH_SECONDS, SessionStore, user_key

log = logging.getLogger(__name__)

KEEP_IN_TEMP = "readme_will_not_be_deleted.txt"
EXIT_RESTART = 3
USAGE_FLUSH_MS = 60_000
MAX_BODY = 16 * 1024 ** 2  # hub pages; uploads to apps are streamed, up to max-upload-mb


class Hub:
    """One per process: settings, catalog, running apps, notifier, web application and lifecycle."""
    version = __version__
    package_root = PACKAGE_DIR.parent

    def __init__(self, settings, debug=False, supervised=False, relaunch_argv=None, overrides=None):
        self.settings = settings
        self.overrides = dict(overrides or {})  # settings given on the command line; they win over the file
        self.debug = debug
        self.supervised = supervised
        self.relaunch_argv = relaunch_argv
        self.internal_token = secrets.token_urlsafe(32)
        self.setup_token = secrets.token_urlsafe(24)  # opens /setup/ while the hub has no admin
        self.setup_lock = asyncio.Lock()
        self._setup_logged = None
        self.started_at = datetime.now()
        self.started_mono = time.monotonic()
        self.login_failures = 0
        self.catalog = catalog_mod.Catalog(settings)
        first, last = settings.internal_port_range
        self.ports = PortAllocator(first, last, settings.port_exceptions + [settings.port, settings.ssl_port])
        self.hub_url = f"http://127.0.0.1:{settings.port}" if settings.port else f"https://127.0.0.1:{settings.ssl_port}"
        self.manager = AppManager(settings, self.catalog, self.ports, self.hub_url, self.internal_token)
        # Looked up at call time: reload_settings() replaces self.notifier.
        self.manager.notify = lambda message, event: self.notifier.send(message, event=event)
        self.notifier = Notifier(settings, enabled=not debug)
        self.sessions = SessionStore(settings.sessions_file, settings.session_days)
        self._sessions_refresh = None
        self.login_throttle = auth.LoginThrottle()
        self.auth_slots = asyncio.Semaphore(account.AUTH_CONCURRENCY)
        self.report_throttle = auth.LoginThrottle(limit=5, window=600)
        self.servers = []
        self.exit_code = 0
        self._job = None
        self._usage_flush = None
        self._stopping = False
        self.draining = False     # set by shutdown(): no new launches or WebSocket sessions
        self.active_requests = 0  # proxied HTTP requests in progress
        self.stopped = asyncio.Event()
        tornado.httpclient.AsyncHTTPClient.configure(None, max_clients=200, max_body_size=10 * 1024 ** 3)
        self.http_client = tornado.httpclient.AsyncHTTPClient()
        self.oidc = sso.OidcProvider(settings, self.http_client)
        self.application = self.make_application()

    # -- web application --
    def make_application(self):
        """Routes are tried in order: fixed hub pages first, then running apps (proxy), then launching."""
        hub = {"hub": self}
        s = self.settings
        return tornado.web.Application(
            [
                (r"/", pages.BoardPageHandler, hub),
                (r"/([^/]+\.brd)/", pages.BoardPageHandler, hub),
                (r"/news/", pages.NewsPageHandler, hub),
                (r"/login/", account.LoginHandler, hub),
                (r"/login/oidc/", sso.OidcLoginHandler, hub),
                (r"/login/oidc/callback", sso.OidcCallbackHandler, hub),
                (r"/logout/", account.LogoutHandler, hub),
                (r"/setup/", setup.SetupHandler, hub),
                (r"/report/", apps.ReportHandler, hub),
                (r"/out/([^/]+)/?", apps.OutHandler, hub),
                (r"/admin/", admin_page.AdminPageHandler, hub),
                (r"/api/", admin.ApiHandler, hub),
                (r"/api/health", admin.HealthHandler, hub),
                (r"/metrics", admin.MetricsHandler, hub),
                (r"/api/apps", apps.AppListHandler, hub),
                (r"/api/apps/([^/]+)/status", apps.AppStatusHandler, hub),
                (r"/api/apps/([^/]+)/(start|stop|restart)", admin.AppControlHandler, hub),
                (r"/api/apps/([^/]+)/log", admin_page.AppLogHandler, hub),
                (r"/api/apps/([^/]+)/affinity", admin_page.AffinityHandler, hub),
                (r"/api/admin/state", admin_page.AdminStateHandler, hub),
                (r"/api/admin/ports", admin_page.PortsHandler, hub),
                (r"/api/admin/environments", admin_page.EnvironmentsHandler, hub),
                (r"/api/admin/path-check", admin_page.PathCheckHandler, hub),
                (r"/api/admin/files/(config|apps|users|news)", admin_page.FileHandler, hub),
                (r"/api/admin/git/(status|pull|push)", admin_page.GitHandler, hub),
                (r"/api/admin/sessions", admin_page.SessionsHandler, hub),
                (r"/api/admin/temp/purge", admin_page.TempPurgeHandler, hub),
                (r"/api/admin/backup", backup_admin.BackupHandler, hub),
                (r"/api/admin/restore", backup_admin.RestoreHandler, hub),
                (r"/api/admin/docker", docker_admin.DockerStateHandler, hub),
                (r"/api/admin/docker/containers/([^/]+)/(start|stop|restart|remove)",
                 docker_admin.DockerContainerHandler, hub),
                (r"/api/admin/docker/containers/([^/]+)/logs", docker_admin.DockerLogsHandler, hub),
                (r"/api/admin/docker/images/(pull|remove)", docker_admin.DockerImageHandler, hub),
                (r"/api/admin/cdf", cdf_admin.CdfListHandler, hub),
                (r"/api/admin/cdf/upload", cdf_admin.CdfUploadHandler, hub),
                (r"/api/admin/cdf/(rename|delete|folder)", cdf_admin.CdfActionHandler, hub),
                (r"/status\.cmd(?:/.*)?", tornado.web.RedirectHandler, {"url": "/admin/", "permanent": True}),
                (r"/update/", admin.UpdateHandler, hub),
                (r"/clear/", admin.ClearHandler, hub),
                (r"/restart/", admin.RestartHandler, hub),
                (r"/exit/", admin.ExitHandler, hub),
                (r"/(clear|exit|restart)\.cmd/", admin.LegacyCommandHandler, hub),
                (r"/cdf/(.*)", tornado.web.StaticFileHandler, {"path": str(s.cdf_path)}),
                (r"/temp/(.*)", tornado.web.StaticFileHandler, {"path": str(s.temp_path)}),
                # Match only apps that are ready; anything else falls through to LaunchHandler.
                (RunningAppMatcher(self.manager, websocket=True), ProxyWSHandler, hub),
                (RunningAppMatcher(self.manager, websocket=False), ProxyHTTPHandler, hub),
                (r"/([^/]+)/(.*)", apps.LaunchHandler, hub),
                (r"/([^/]+)", apps.AppRedirectHandler, hub),
            ],
            template_loader=ChainLoader([s.template_folder, PACKAGE_DIR / "templates"]),
            static_path=str(PACKAGE_DIR / "static"),  # bundled Bootstrap and Font Awesome, at /static/
            cookie_secret=s.cookie_secret,
            xsrf_cookies=True,
            xsrf_cookie_kwargs={"httponly": True, "samesite": "Lax"},
            websocket_max_message_size=s.max_ws_message_mb * 1024 * 1024,
            serve_traceback=self.debug,
        )

    def user_from_cookie(self, handler):
        """The signed-in User for a request, or None: revoked sessions, and SSO sessions older than
        `sso-session-minutes`, are refused."""
        value = handler.get_signed_cookie("user", max_age_days=self.settings.session_days)
        if not value:
            return None
        value = value.decode()
        sid, issued, name, source = auth.session_meta(value)
        if not self.sessions.is_valid(sid, user_key(name, source), issued):
            return None
        minutes = self.settings.sso_session_minutes
        if minutes and source in auth.SSO_SOURCES and time.time() - (issued or 0) > minutes * 60:
            return None  # sign in again, so directory group changes apply
        return auth.user_from_session(value, self.catalog)

    def announce_setup(self):
        """While the hub has no admin, log the one-time setup link (at most once a minute)."""
        if not auth.needs_setup(self.catalog, self.settings):
            return
        if self._setup_logged is not None and time.monotonic() - self._setup_logged < 60:
            return
        self._setup_logged = time.monotonic()
        url = self.public_url()
        log.warning("No admin account yet: open %s/ and enter the setup token below, or open %s/setup/?token=%s",
                    url, url, self.setup_token)
        log.warning("Setup token: %s", self.setup_token)

    def public_url(self):
        """`server-url` plus the hub port, unless the URL names a port or a reverse proxy fronts the hub."""
        url = self.settings.server_url.rstrip("/")
        if self.settings.behind_proxy or urlsplit(url).port is not None or not self.settings.port:
            return url
        return f"{url}:{self.settings.port}"

    def log_tail(self, inst, app_id=None, limit=256 * 1024):
        """Last `limit` bytes of an app's log; falls back to logs/<app_id>.log once the app is gone."""
        path = inst.log_file if inst and inst.log_file else None
        if path is None and app_id:
            path = self.settings.log_path / f"{safe_name(app_id)}.log"
        if path is None or not path.is_file():
            return ""
        with open(path, "rb") as handle:
            handle.seek(max(0, path.stat().st_size - limit))
            return handle.read().decode("utf-8", errors="replace")

    # -- lifecycle --
    def listen(self):
        """Open the HTTP and/or HTTPS listeners; both serve the same application."""
        s = self.settings
        options = {"xheaders": s.behind_proxy, "max_body_size": MAX_BODY}
        if s.port:
            server = tornado.httpserver.HTTPServer(self.application, **options)
            server.listen(s.port)
            self.servers.append(server)
            log.info("HTTP server listening on port %s", s.port)
        if s.ssl_port:
            context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            context.load_cert_chain(str(s.ssl_cert), str(s.ssl_key))
            server = tornado.httpserver.HTTPServer(self.application, ssl_options=context, **options)
            server.listen(s.ssl_port)
            self.servers.append(server)
            log.info("HTTPS server listening on port %s", s.ssl_port)
        if not self.servers:
            raise RuntimeError("Neither port nor ssl_port is set")

    async def startup(self):
        """Folders, background jobs, leftover cleanup, startup notification, then auto-start apps."""
        if auth.demo_password_in_use():
            log.warning("The admin login is admin / admin (the demo default): set STREAMHUB_ADMIN_PASSWORD")
        self.settings.temp_path.mkdir(parents=True, exist_ok=True)
        self.settings.log_path.mkdir(parents=True, exist_ok=True)
        self.announce_setup()
        self._schedule()
        await asyncio.get_running_loop().run_in_executor(None, self.manager.usage.load)
        await self.sessions.refresh()
        self._sessions_refresh = tornado.ioloop.PeriodicCallback(self.sessions.refresh, REFRESH_SECONDS * 1000)
        self._sessions_refresh.start()
        self._usage_flush = tornado.ioloop.PeriodicCallback(self.manager.usage.flush, USAGE_FLUSH_MS)
        self._usage_flush.start()
        self.manager.start_idle_reaper()
        self.manager.start_health_checks()
        await self.manager.sweep()
        instance = f" instance *{self.settings.instance_id}*" if self.settings.instance_id else ""
        await self.notifier.send(
            f":rocket: Streamhub {self.version}{instance} (PID: *{os.getpid()}*) started on port "
            f"*{self.settings.port}* using '{self.settings.config_dir}'"
            + (f" with memory cleaning at *{self.settings.schedule}*." if self.settings.schedule else ".")
            + f" - <{self.public_url()}/|Check Server>", event="system")
        await self.start_auto_apps()

    def _schedule(self):
        """(Re)arm the daily memory clean from the current settings."""
        if self._job:
            self._job.cancel()
            self._job = None
        if self.settings.schedule:
            self._job = DailyJob(self.settings.schedule, self.settings.timezone,
                                 lambda: self.clean_memory(trigger="Scheduled", run_auto_start=True))
            self._job.start()

    async def start_auto_apps(self):
        for app in self.catalog.all_apps():
            if app.auto_start and app.launchable:
                try:
                    await self.manager.start(app)
                except LaunchError as exc:
                    log.error("Auto-start of %s failed: %s", app.app_id, exc)

    async def clean_memory(self, trigger="Manual", all_apps=False, run_auto_start=False, rerun_apps=False):
        """Stop `auto_shutdown` apps (or all of them) and empty temp/. Returns the stopped app IDs.

        `run_auto_start` starts the auto-start apps afterwards; `rerun_apps` relaunches the stopped ones.
        """
        log.info("Cleaning memory (%s)", trigger)
        stopped = await self.manager.stop_where(lambda inst: all_apps or inst.app.auto_shutdown)
        clean_folder(self.settings.temp_path)
        await self.notifier.send(f":shower: Streamhub (PID: *{os.getpid()}*) memory cleaned. {trigger} trigger.",
                                 event="clean")
        if run_auto_start:
            await self.start_auto_apps()
        if rerun_apps:
            for app_id in stopped:
                app = self.catalog.find(app_id)
                if app is not None and app.launchable:
                    try:
                        await self.manager.start(app)
                    except LaunchError as exc:
                        log.error("Relaunch of %s failed: %s", app_id, exc)
        return stopped

    def purge_temp(self):
        """Empty temp/ (the readme marker and files still in use stay)."""
        clean_folder(self.settings.temp_path)

    def reload_settings(self):
        """Apply a changed config file. Returns the settings that still need a restart."""
        fresh = load_settings(self.settings.config_file or self.settings.config_dir)
        for name, value in self.overrides.items():
            setattr(fresh, name, value)
        needs_restart = [f.name for f in fields(fresh)
                         if f.name in RESTART_ONLY and getattr(fresh, f.name) != getattr(self.settings, f.name)]
        for f in fields(fresh):
            if f.name not in RESTART_ONLY:
                setattr(self.settings, f.name, getattr(fresh, f.name))
        self.catalog = self.manager.catalog = catalog_mod.Catalog(self.settings)
        self.ports.exceptions = set(self.settings.port_exceptions) | {self.settings.port, self.settings.ssl_port}
        failures = self.notifier.failures
        self.notifier = Notifier(self.settings, enabled=not self.debug)
        self.notifier.failures = failures  # /metrics counters run from the start
        self.oidc = sso.OidcProvider(self.settings, self.http_client)
        self._schedule()
        return needs_restart

    async def shutdown(self, restart=False, trigger="Signal"):
        """Stop listeners, jobs and every app. A restart exits with code 3 when supervised, else relaunches."""
        if self._stopping:
            return
        self._stopping = True
        log.info("Stopping Streamhub (%s)", trigger)
        await asyncio.sleep(0.2)  # let the confirmation page reach the browser
        for server in self.servers:
            server.stop()  # no new connections; open ones keep going while draining
        self.draining = True
        if self._job:
            self._job.cancel()
        self.manager.stop_idle_reaper()
        self.manager.stop_health_checks()
        for job in (self._usage_flush, self._sessions_refresh):
            if job:
                job.stop()
        await self.drain()
        await self.manager.close()
        await self.manager.usage.flush()
        await self.sessions.settle()
        clean_folder(self.settings.temp_path)
        await self.notifier.send(f":red_circle: Streamhub (PID: *{os.getpid()}*) "
                                 f"{'is restarting' if restart else 'stopped'}. {trigger}.", event="system")
        if restart:
            if self.supervised:
                self.exit_code = EXIT_RESTART
            else:
                self._relaunch()
        self.stopped.set()

    def open_sessions(self):
        return sum(inst.active_ws for inst in self.manager.instances.values())

    async def drain(self):
        """Wait up to `drain-timeout` seconds for proxied requests and WebSocket sessions to end."""
        deadline = time.monotonic() + self.settings.drain_timeout
        while (self.active_requests or self.open_sessions()) and time.monotonic() < deadline:
            await asyncio.sleep(0.1)
        if self.active_requests or self.open_sessions():
            log.warning("Stopping with %d request(s) and %d session(s) still open (drain-timeout %ss)",
                        self.active_requests, self.open_sessions(), self.settings.drain_timeout)

    def _relaunch(self):
        """Start a fresh copy of the hub with the same arguments (the listeners are already closed)."""
        env = platform_utils.relaunch_env(os.environ.copy())
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(self.package_root), env.get("PYTHONPATH")]))
        argv = self.relaunch_argv or platform_utils.self_command() + sys.argv[1:]
        log.info("Relaunching: %s", " ".join(argv))
        platform_utils.release_children()  # the new hub must outlive this one
        subprocess.Popen(argv, env=env, cwd=os.getcwd())


def clean_folder(path):
    """Empty `path` but keep the folder and the readme marker. Files still in use are skipped."""
    path = Path(path)
    if not path.is_dir():
        return
    for entry in path.iterdir():
        if entry.name == KEEP_IN_TEMP:
            continue
        try:
            if entry.is_dir() and not entry.is_symlink():
                shutil.rmtree(entry)
            else:
                entry.unlink()
        except OSError as exc:
            log.warning("Could not delete %s: %s", entry, exc)


def run(config_path, port=0, ssl_port=0, debug=False, supervised=False):
    """Run the hub until it is stopped. Returns the process exit code."""
    settings = load_settings(config_path)
    overrides = {name: value for name, value in (("port", port), ("ssl_port", ssl_port)) if value > 0}
    for name, value in overrides.items():
        setattr(settings, name, value)
    return asyncio.run(_serve(settings, debug, supervised, overrides))


async def _serve(settings, debug, supervised, overrides=None):
    hub = Hub(settings, debug=debug, supervised=supervised, overrides=overrides)
    platform_utils.kill_children_with_hub()
    hub.listen()
    tasks = set()  # strong references, so pending tasks are not garbage-collected

    def spawn(coro):
        task = asyncio.ensure_future(coro)
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    platform_utils.install_signal_handlers(lambda signum: spawn(hub.shutdown(trigger=f"Signal {signum}")))
    spawn(hub.startup())
    log.info("Streamhub %s started (PID %s)", hub.version, os.getpid())
    await hub.stopped.wait()
    return hub.exit_code
