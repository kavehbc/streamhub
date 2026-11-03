"""Starts, watches and stops app processes. One AppInstance per running (or just stopped) app."""
import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import tornado.httpclient
from tornado.ioloop import IOLoop, PeriodicCallback

from streamhub import auth, platform_utils
from streamhub.ports import PortsExhausted
from streamhub.runtimes import (DockerRuntime, KubernetesRuntime, LaunchError, ProcessRuntime, streamlit_flags,
                                wants_user_headers)
from streamhub.usage import DB_FILE, AppUsage, UsageStore

log = logging.getLogger(__name__)

STARTING, RUNNING, STOPPED = "starting", "running", "stopped"
REGISTRY_FILE = "processes.json"  # in the log folder: app processes of this hub, swept at the next start

__all__ = ["AppInstance", "AppManager", "LaunchError", "STARTING", "RUNNING", "STOPPED"]


@dataclass
class AppInstance:
    """A launched app: where to proxy to, its local child process, state, health and usage counters."""
    app: object
    port: int              # 0 when the hub holds no local port (Kubernetes, .curl)
    upstream: str          # base URL the proxy forwards to
    strip_prefix: bool     # remove "/<app_id>" before forwarding (non-Streamlit apps)
    process: object = None
    log_file: Path | None = None
    state: str = STARTING
    started_at: datetime = field(default_factory=datetime.now)
    started_mono: float = field(default_factory=time.monotonic)
    last_access: datetime | None = None
    last_access_mono: float = field(default_factory=time.monotonic)
    exit_code: int | None = None
    active_ws: int = 0     # open WebSocket sessions; an app with one is never idle
    stopping: bool = False  # set by stop(): the exit is expected, so no restart
    restarts: int = 0
    usage: AppUsage = field(default_factory=AppUsage)  # shared by the app's instances, saved by UsageStore
    runtime: object = None
    runtime_handle: object = None
    probe: str = "bind"
    healthy: bool = True
    health_failures: int = 0  # consecutive failed health checks
    error: str = ""           # why the app failed to start, shown on its error page
    ready_seconds: float | None = None  # from launch to the first successful probe

    @property
    def app_id(self):
        return self.app.app_id

    @property
    def pid(self):
        return self.process.pid if self.process else 0

    @property
    def ready(self):
        return self.state == RUNNING

    def url_for(self, rest, query=""):
        """Upstream URL for the hub path '/<app_id>/<rest>'."""
        query = f"?{query}" if query else ""
        if self.strip_prefix:
            return f"{self.upstream}/{rest}{query}"
        return f"{self.upstream}/{self.app_id}/{rest}{query}"

    def touch(self, count=True):
        """Record activity (resets the idle timer); `count` also adds one request to today's usage."""
        self.last_access = datetime.now()
        self.last_access_mono = time.monotonic()
        if count:
            self.usage.add()

    def usage_today(self):
        return self.usage.today()


def safe_name(app_id):
    return re.sub(r"[^A-Za-z0-9._-]", "_", app_id)


class AppManager:
    """Starts, watches and stops apps: one AppInstance per app ID, plus the idle reaper and health checks."""

    def __init__(self, settings, catalog, ports, hub_url, internal_token):
        self.settings = settings
        self.catalog = catalog
        self.ports = ports
        self.hub_url = hub_url
        self.internal_token = internal_token
        self.instances = {}
        self.runtimes = {r.name: r for r in (ProcessRuntime(self), DockerRuntime(self), KubernetesRuntime(self))}
        self.notify = None  # async callable(message, event), set by the Hub
        self.closing = False  # set by close(): no new launches
        self._starting = {}   # app_id -> the launch in progress, shared by concurrent callers
        self.usage = UsageStore(Path(settings.log_path) / DB_FILE, settings.usage_retention_days)
        self.failures = {}    # app_id -> failed launches since the hub started (/metrics)
        self._reaper = None
        self._health = None

    # -- queries --
    def get(self, app_id):
        return self.instances.get(app_id)

    def running(self, app_id):
        """The instance unless it has stopped (starting counts as running)."""
        inst = self.instances.get(app_id)
        return inst if inst and inst.state != STOPPED else None

    # -- starting --
    async def start(self, app, restarts=0):
        """Launch `app` (or return its running instance). Readiness and exit are watched in the background.

        Concurrent calls for one app share a single launch.
        """
        if app.kind == "curl":
            return self._register_curl(app)
        if not app.launchable:
            raise LaunchError(f"{app.app_id} cannot be launched")
        existing = self.running(app.app_id)
        if existing:
            return existing
        if self.closing:
            raise LaunchError("Streamhub is shutting down")
        task = self._starting.get(app.app_id)
        if task is None:
            task = asyncio.ensure_future(self._launch(app, restarts))
            self._starting[app.app_id] = task
            task.add_done_callback(lambda done, app_id=app.app_id: self._launched(app_id, done))
        return await asyncio.shield(task)  # a caller that gives up does not cancel the launch

    def _failed(self, app_id):
        self.failures[app_id] = self.failures.get(app_id, 0) + 1

    def _launched(self, app_id, task):
        if self._starting.get(app_id) is task:
            del self._starting[app_id]
        if not task.cancelled():
            task.exception()  # retrieved here, so an unawaited failure is not reported as lost

    async def _launch(self, app, restarts):
        runtime = self.runtimes[app.runtime]
        try:
            port = self.ports.allocate() if runtime.uses_local_port else 0
        except PortsExhausted as exc:
            raise LaunchError(str(exc)) from exc
        launch = None
        try:
            launch = await runtime.prepare(app, port)
            process, log_file = await self._spawn(app, launch)
        except BaseException as exc:
            self.ports.release(port)
            self._failed(app.app_id)
            if launch is not None and launch.handle is not None:  # a container or pod may exist already
                await self._release(AppInstance(app=app, port=port, upstream=launch.upstream, strip_prefix=False,
                                                runtime=runtime, runtime_handle=launch.handle))
            if isinstance(exc, Exception):
                raise LaunchError(f"Could not start {app.app_id}: {exc}") from exc
            raise

        inst = AppInstance(app=app, port=port, upstream=launch.upstream, strip_prefix=not app.is_streamlit,
                           process=process, log_file=log_file, restarts=restarts, runtime=runtime,
                           runtime_handle=launch.handle, probe=launch.probe, usage=self.usage.for_app(app.app_id))
        self.instances[app.app_id] = inst
        self._record(app.app_id, process.pid)
        log.info("Started %s (pid %s, %s) on %s: %s", app.app_id, process.pid, runtime.name, launch.upstream,
                 " ".join(launch.argv))
        IOLoop.current().spawn_callback(self._watch_ready, inst)
        IOLoop.current().spawn_callback(self._watch_exit, inst)
        return inst

    def _register_curl(self, app):
        """A .curl app has no process: it is "running" as soon as it is registered."""
        inst = self.running(app.app_id)
        if inst is None:
            inst = AppInstance(app=app, port=0, upstream=app.url.rstrip("/"), strip_prefix=True,
                               state=RUNNING, usage=self.usage.for_app(app.app_id))
            self.instances[app.app_id] = inst
        return inst

    def python_for(self, app):
        """Interpreter for an app: built-in tools use the hub's own, then python_executable, then the env."""
        if app.kind == "cmd":
            return platform_utils.hub_python()
        if app.python_executable:
            return app.python_executable
        return platform_utils.env_python(app.virtual_environment or self.settings.virtual_environment)

    def build_argv(self, app, port):
        """Command line of a local-process app. Precedence: `command`, `bash_file`, then `file`."""
        if app.is_streamlit:
            flags = streamlit_flags(app.app_id, port, "127.0.0.1", self.settings.max_ws_message_mb,
                                    wants_user_headers(app, self.settings))
        else:
            flags = [f"--port={port}", f"--app_id={app.app_id}"]

        if app.command:
            python = self.python_for(app)
            values = {"python": python, "port": port, "app_id": app.app_id, "base_path": f"/{app.app_id}"}
            return [str(arg).format(**values) for arg in app.command] + app.args

        if app.bash_file:
            if not app.bash_file.is_file():
                raise LaunchError(f"bash_file not found: {app.bash_file}")
            return platform_utils.script_argv(app.bash_file) + flags + app.args

        if not app.file:
            raise LaunchError(f"{app.app_id} has no 'file', 'bash_file' or 'command'")
        main = Path(app.file)
        if not main.is_absolute() and app.folder:
            main = app.folder / main
        if app.activate and app.kind != "cmd":
            conda = platform_utils.conda_exe()
            env = app.virtual_environment or self.settings.virtual_environment
            if not conda or not env:
                raise LaunchError("'activate' needs conda and a virtual_environment")
            python = [conda, "run", "-n", env, "--no-capture-output", "python"]
        else:
            python = [self.python_for(app)]
        if app.is_streamlit:
            return python + ["-m", "streamlit", "run", str(main)] + flags + app.args
        return python + [str(main)] + flags + app.args

    def passthrough_env(self, app):
        """Hub variables the app opted into (`env-passthrough`, the app's `env_passthrough`)."""
        return platform_utils.child_env(self.settings.env_passthrough + app.env_passthrough, base=False)

    def app_env(self, app, port, host):
        """Variables Streamhub gives every app: opted-in hub variables, its own, then the app's `env`.

        The hub's other variables (secrets included) are not passed on (SEC-15).
        """
        env = {
            **self.passthrough_env(app),
            "PYTHONUNBUFFERED": "1",
            "PYTHONIOENCODING": "utf-8",
            "STREAMHUB_PORT": str(port),
            "STREAMHUB_HOST": host,
            "STREAMHUB_APP_ID": app.app_id,
            "STREAMHUB_BASE_PATH": f"/{app.app_id}",
            "STREAMHUB_URL": self.hub_url,
        }
        if self.internal_token:
            env["STREAMHUB_APP_KEY"] = auth.app_key(self.internal_token, app.app_id)  # verifies X-Streamhub-Identity
        if app.kind == "cmd":
            env["STREAMHUB_INTERNAL_TOKEN"] = self.internal_token
        env.update(app.env)
        return env

    def _working_dir(self, app):
        for candidate in (app.folder, app.bash_file.parent if app.bash_file else None):
            if candidate and Path(candidate).is_dir():
                return str(candidate)
        return str(self.settings.config_dir)

    async def _spawn(self, app, launch):
        """Start the child with stdout/stderr in logs/<app_id>.log; the previous run is kept as .log.1."""
        log_dir = self.settings.log_path
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{safe_name(app.app_id)}.log"
        try:
            if log_file.exists():
                os.replace(log_file, log_file.with_suffix(".log.1"))
        except OSError:
            pass  # still held open on Windows by a dying process: append instead
        handle = open(log_file, "ab")
        try:
            process = await asyncio.create_subprocess_exec(
                *launch.argv, cwd=self._working_dir(app), env=launch.env,
                stdin=asyncio.subprocess.DEVNULL, stdout=handle, stderr=asyncio.subprocess.STDOUT,
                **platform_utils.new_group_kwargs())
        finally:
            handle.close()  # the child keeps its own handle
        return process, log_file

    async def _probe(self, inst):
        """True when the app answers: its health path, else its port (bind test or TCP connect)."""
        if inst.app.health:
            return await self._health_ok(inst)
        if inst.probe == "bind":
            return not platform_utils.port_is_free(inst.port)
        target = urlsplit(inst.upstream)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, platform_utils.port_accepts, target.hostname, target.port)

    async def _health_ok(self, inst, timeout=10):
        """GET the app's health path straight from the upstream (not through the proxy, so no usage counted)."""
        request = tornado.httpclient.HTTPRequest(inst.url_for(inst.app.health), connect_timeout=timeout,
                                                 request_timeout=timeout, follow_redirects=False)
        try:
            response = await tornado.httpclient.AsyncHTTPClient().fetch(request, raise_error=False)
        except Exception:  # connection refused, timeout
            return False
        return 200 <= response.code < 400

    async def _watch_ready(self, inst):
        """Mark the app running once it answers. Not answering within startup_timeout is a failure:
        the app is stopped, its error page says why, and its restart policy applies as for a crash."""
        deadline = time.monotonic() + self.settings.startup_timeout
        while inst.state == STARTING:
            if await self._probe(inst):
                if inst.state == STARTING and await self._bind_ok(inst):
                    inst.state = RUNNING
                    inst.ready_seconds = round(time.monotonic() - inst.started_mono, 3)
                    log.info("%s is ready on %s", inst.app_id, inst.upstream)
                return
            if time.monotonic() > deadline:
                where = f"/{inst.app.health}" if inst.app.health else f"port {inst.port or inst.upstream}"
                inst.error = f"The app did not answer on {where} within {self.settings.startup_timeout} s."
                log.warning("%s: %s", inst.app_id, inst.error)
                self._failed(inst.app_id)
                if inst.process and inst.state == STARTING and not inst.stopping:
                    await self._terminate(inst)  # not `stopping`: _watch_exit applies the restart policy
                return
            await asyncio.sleep(0.25)

    async def _bind_ok(self, inst):
        """`bind-check` (SEC-12): a process app listening beyond loopback is reported, or refused and stopped."""
        mode = self.settings.bind_check
        if mode == "off" or inst.runtime is None or inst.runtime.name != "process" or not inst.pid:
            return True
        exposed = await asyncio.get_running_loop().run_in_executor(None, platform_utils.exposed_listeners, inst.pid)
        if not exposed:
            return True
        message = (f"{inst.app_id} listens on {', '.join(exposed)}, which bypasses the hub's access control; "
                   "bind it to 127.0.0.1 (STREAMHUB_HOST)")
        if mode != "refuse":
            log.warning(message)
            return True
        log.error("%s; stopping it (bind-check: refuse)", message)
        inst.error = message[0].upper() + message[1:] + "."
        self._failed(inst.app_id)
        inst.stopping = True  # restarting would only repeat it
        await self._terminate(inst)
        return False

    async def _watch_exit(self, inst):
        """On an unexpected exit, apply the restart policy with exponential backoff (1 s to 60 s)."""
        inst.exit_code = await inst.process.wait()
        inst.state = STOPPED
        self.ports.release(inst.port)
        self._record(inst.app_id, exited=inst.pid)
        if inst.stopping:
            return
        log.warning("%s exited with code %s", inst.app_id, inst.exit_code)
        policy = inst.app.restart
        if policy == "always" or (policy == "on-failure" and inst.exit_code != 0):
            if time.monotonic() - inst.started_mono > 600:
                inst.restarts = 0  # it ran for 10 minutes: start the backoff over
            # Restart only if nobody stopped or replaced the instance while we waited.
            delay = min(60, 2 ** inst.restarts)
            log.info("Restarting %s in %ss (policy %s)", inst.app_id, delay, policy)
            await asyncio.sleep(delay)
            if self.instances.get(inst.app_id) is inst:
                del self.instances[inst.app_id]
                app = self.catalog.find(inst.app_id) or inst.app
                try:
                    await self.start(app, restarts=inst.restarts + 1)
                except LaunchError as exc:
                    log.error("Restart of %s failed: %s", inst.app_id, exc)

    # -- stopping --
    async def stop(self, app_id):
        """Stop an app on purpose (no restart) and forget it. A launch in progress is awaited first."""
        pending = self._starting.get(app_id)
        if pending is not None:
            await asyncio.wait([pending])
        inst = self.instances.pop(app_id, None)
        if inst is None:
            return
        inst.stopping = True
        if inst.process and inst.state != STOPPED:
            await self._terminate(inst)
        inst.state = STOPPED
        if inst.port:
            self.ports.release(inst.port)
        log.info("Stopped %s", app_id)

    async def close(self):
        """Refuse new launches, let the ones in progress finish, then stop every app."""
        self.closing = True
        if self._starting:
            await asyncio.wait(list(self._starting.values()))
        await self.stop_where(lambda inst: True)

    async def _release(self, inst):
        """Stop what the local child process does not own (a container, a pod); errors are logged."""
        if inst.runtime is not None:
            try:
                await inst.runtime.release(inst)
            except Exception as exc:
                log.warning("Could not release %s: %s", inst.app_id, exc)

    async def _terminate(self, inst):
        """Stop the app: its container or pod first, then the local process tree (SIGTERM, grace, SIGKILL)."""
        await self._release(inst)
        tree = platform_utils.process_tree(inst.process.pid)
        descendants = tree[1:]
        platform_utils.signal_tree(tree)
        grace = 0 if platform_utils.IS_WINDOWS else self.settings.stop_timeout
        try:
            await asyncio.wait_for(inst.process.wait(), timeout=grace or 5)
        except asyncio.TimeoutError:
            platform_utils.signal_tree(tree, kill=True)
        loop = asyncio.get_running_loop()
        alive = await loop.run_in_executor(None, platform_utils.wait_gone, descendants, 2)
        platform_utils.signal_tree(alive, kill=True)
        try:
            await asyncio.wait_for(inst.process.wait(), timeout=5)
        except asyncio.TimeoutError:
            log.error("%s (pid %s) did not exit", inst.app_id, inst.pid)

    async def stop_where(self, predicate):
        targets = [app_id for app_id, inst in self.instances.items() if predicate(inst)]
        await asyncio.gather(*(self.stop(app_id) for app_id in targets))
        return targets

    def forget(self, app_id):
        """Drop a stopped instance so the next request launches the app again."""
        inst = self.instances.get(app_id)
        if inst and inst.state == STOPPED:
            del self.instances[app_id]

    # -- leftovers of a crashed hub --
    @property
    def registry_path(self):
        return Path(self.settings.log_path) / REGISTRY_FILE

    def _read_registry(self):
        try:
            data = json.loads(self.registry_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _record(self, app_id, pid=None, exited=None):
        """Add `app_id`'s process `pid` to the registry, or remove its entry if it is for the `exited` PID."""
        entries = self._read_registry()
        if pid is not None:
            entries[app_id] = {"pid": pid, "created": platform_utils.process_started(pid)}
        elif exited is not None and entries.get(app_id, {}).get("pid") == exited:
            del entries[app_id]
        else:
            return
        try:
            path = self.registry_path
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(path.name + ".tmp")
            temporary.write_text(json.dumps(entries), encoding="utf-8")
            os.replace(temporary, path)
        except OSError as exc:
            log.warning("Cannot update %s: %s", self.registry_path, exc)

    async def sweep(self):
        """Remove app processes, containers and pods left behind by a hub that did not stop cleanly."""
        entries = self._read_registry()
        loop = asyncio.get_running_loop()
        for app_id, entry in entries.items():
            try:
                killed = await loop.run_in_executor(None, platform_utils.kill_leftover, int(entry["pid"]),
                                                    float(entry["created"]))
            except (KeyError, TypeError, ValueError):
                continue
            if killed:
                log.warning("Stopped %d leftover process(es) of %s from a previous run", killed, app_id)
        if entries:
            try:
                self.registry_path.unlink()
            except OSError:
                pass
        apps = list(self.catalog.all_apps())
        for runtime in self.runtimes.values():
            try:
                await runtime.sweep(apps)
            except Exception as exc:
                log.warning("Cleanup of %s leftovers failed: %s", runtime.name, exc)

    # -- idle shutdown --
    def start_idle_reaper(self, interval_ms=60_000):
        self._reaper = PeriodicCallback(self._reap_idle, interval_ms)
        self._reaper.start()

    def stop_idle_reaper(self):
        if self._reaper:
            self._reaper.stop()

    async def _reap_idle(self):
        """Stop auto_shutdown apps with no open session and no request within their idle timeout."""
        now = time.monotonic()

        def idle(inst):
            minutes = inst.app.idle_timeout if inst.app.idle_timeout is not None else self.settings.idle_timeout
            return (minutes and inst.process and inst.app.auto_shutdown and inst.state == RUNNING
                    and inst.active_ws == 0 and now - inst.last_access_mono > minutes * 60)

        stopped = await self.stop_where(idle)
        if stopped:
            log.info("Stopped idle apps: %s", ", ".join(stopped))

    # -- health checks --
    def start_health_checks(self):
        if self.settings.health_interval > 0:
            self._health = PeriodicCallback(self.check_health, self.settings.health_interval * 1000)
            self._health.start()

    def stop_health_checks(self):
        if self._health:
            self._health.stop()

    async def check_health(self):
        """One round of health checks; stops an app after `health-failures` failures in a row."""
        targets = [inst for inst in self.instances.values()
                   if inst.state == RUNNING and inst.process and inst.app.health and inst.healthy
                   and not inst.stopping]
        results = await asyncio.gather(*(self._health_ok(inst) for inst in targets))
        for inst, ok in zip(targets, results):
            if ok:
                inst.healthy, inst.health_failures = True, 0
                continue
            inst.health_failures += 1
            if inst.health_failures < self.settings.health_failures:
                continue
            inst.healthy = False
            message = (f":warning: {inst.app_id} failed {inst.health_failures} health checks on "
                       f"/{inst.app.health}; stopping it (restart policy: {inst.app.restart}).")
            log.warning(message)
            if self.notify:
                await self.notify(message, "health")
            # Not marked `stopping`: _watch_exit applies the restart policy as for a crash.
            await self._terminate(inst)
