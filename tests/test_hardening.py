"""Regression tests for the 2.2 changes: app environments, LDAP and OIDC transport, login throttling, the users
file, launches, readiness, notifications, process cleanup, request streaming, usage and sessions."""
import asyncio
import json
import os
import sys
import time
import types

import pytest

from streamhub import auth, platform_utils
from streamhub.catalog import Catalog
from streamhub.config import load_settings
from streamhub.launcher import AppManager
from streamhub.runtimes import DockerRuntime, ProcessRuntime


def write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def make_catalog(tmp_path, apps=(), config=None):
    write(tmp_path / "streamhub.json", {"schedule": None, **(config or {})})
    write(tmp_path / "streamhub-apps.json", [{"boards": []}, *apps])
    return Catalog(load_settings(tmp_path))


# -- SEC-15: app environments --
def test_child_env_keeps_what_programs_need_and_drops_the_rest():
    environ = {"PATH": "/bin", "LANG": "C", "LC_ALL": "C", "STREAMHUB_SMTP_PASSWORD": "s3cret", "AWS_KEY": "k",
               "DOCKER_HOST": "unix://x"}
    env = platform_utils.child_env(environ=environ)
    assert env == {"PATH": "/bin", "LANG": "C", "LC_ALL": "C"}
    assert platform_utils.child_env(["AWS_*"], base=False, environ=environ) == {"AWS_KEY": "k"}
    assert "DOCKER_HOST" in platform_utils.child_env(platform_utils.DOCKER_ENV, environ=environ)


def test_process_apps_do_not_inherit_hub_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("STREAMHUB_OIDC_CLIENT_SECRET", "s3cret")
    monkeypatch.setenv("STREAMHUB_ADMIN_PASSWORD", "admin")
    monkeypatch.setenv("SHARED_TOKEN", "for-apps")
    monkeypatch.setenv("APP_ONLY", "for-one-app")
    catalog = make_catalog(tmp_path, [
        {"app_id": "a.py", "file": "a.py"},
        {"app_id": "b.py", "file": "b.py", "env_passthrough": ["APP_*"], "env": {"OWN": "1"}},
    ], {"env-passthrough": ["SHARED_TOKEN"]})
    manager = AppManager(catalog.settings, catalog, None, "http://127.0.0.1:8500", "token")
    a = asyncio.run(ProcessRuntime(manager).prepare(catalog.find("a.py"), 9100)).env
    b = asyncio.run(ProcessRuntime(manager).prepare(catalog.find("b.py"), 9101)).env
    for env in (a, b):
        assert "STREAMHUB_OIDC_CLIENT_SECRET" not in env and "STREAMHUB_ADMIN_PASSWORD" not in env
        assert env["SHARED_TOKEN"] == "for-apps" and env["STREAMHUB_PORT"] and "PATH" in env
    assert "APP_ONLY" not in a and b["APP_ONLY"] == "for-one-app" and b["OWN"] == "1"


def test_docker_client_env_and_container_variables(tmp_path, monkeypatch):
    monkeypatch.setattr(platform_utils, "docker_exe", lambda: "docker")

    async def no_command(argv, input=None, timeout=60):
        return 0, ""

    monkeypatch.setattr(platform_utils, "run_command", no_command)
    monkeypatch.setenv("STREAMHUB_SMTP_PASSWORD", "s3cret")
    monkeypatch.setenv("DOCKER_HOST", "unix:///run/docker.sock")
    catalog = make_catalog(tmp_path, [{"app_id": "d.sl", "runtime": "docker", "image": "img", "file": "a.py"}])
    manager = AppManager(catalog.settings, catalog, None, "http://127.0.0.1:8500", "token")
    launch = asyncio.run(DockerRuntime(manager).prepare(catalog.find("d.sl"), 9100))
    assert launch.env["DOCKER_HOST"] and "STREAMHUB_SMTP_PASSWORD" not in launch.env
    passed = {launch.argv[i + 1] for i, arg in enumerate(launch.argv) if arg == "-e"}
    assert "DOCKER_HOST" not in passed and "PATH" not in passed and "STREAMHUB_APP_ID" in passed


# -- LDAP --
class FakeLdap:
    """Just enough of ldap3 to follow ldap_authenticate's control flow."""

    def __init__(self, starttls_ok=True):
        self.starttls_ok = starttls_ok
        self.events = []
        fake = self

        class Connection:
            def __init__(self, server, dn, secret, **kwargs):
                self.entries = []

            def open(self):
                fake.events.append("open")

            def start_tls(self):
                fake.events.append("start_tls")
                return fake.starttls_ok

            def bind(self):
                fake.events.append("bind")
                return True

            def search(self, *args, **kwargs):
                fake.events.append("search")

            def unbind(self):
                fake.events.append("unbind")

        module = types.ModuleType("ldap3")
        module.NONE, module.BASE = "NONE", "BASE"
        module.Connection = Connection
        module.Server = lambda url, **kwargs: fake.events.append(("server", kwargs["tls"])) or url
        module.Tls = lambda **kwargs: ("tls", kwargs)
        conv, dn = types.ModuleType("ldap3.utils.conv"), types.ModuleType("ldap3.utils.dn")
        conv.escape_filter_chars = dn.escape_rdn = lambda value: value
        self.modules = {"ldap3": module, "ldap3.utils": types.ModuleType("ldap3.utils"),
                        "ldap3.utils.conv": conv, "ldap3.utils.dn": dn}


@pytest.fixture
def fake_ldap(monkeypatch):
    def install(**kwargs):
        fake = FakeLdap(**kwargs)
        for name, module in fake.modules.items():
            monkeypatch.setitem(sys.modules, name, module)
        return fake
    return install


def test_failed_starttls_never_binds(fake_ldap):
    fake = fake_ldap(starttls_ok=False)
    config = {"url": "ldap://directory", "starttls": True, "user-dn": "uid={username},dc=x"}
    with pytest.raises(auth.LdapTlsError):
        auth.ldap_authenticate(config, "", "lisa", "pw")
    assert "bind" not in fake.events and fake.events[-1] == "unbind"


def test_ldap_verifies_certificates(fake_ldap):
    import ssl

    fake = fake_ldap()
    config = {"url": "ldaps://directory", "user-dn": "uid={username},dc=x", "ca-file": "/etc/ca.pem"}
    assert auth.ldap_authenticate(config, "", "lisa", "pw") == ("lisa", [])
    tls = fake.events[0][1]
    assert tls[1] == {"validate": ssl.CERT_REQUIRED, "ca_certs_file": "/etc/ca.pem"}
    fake = fake_ldap()
    auth.ldap_authenticate({"url": "ldap://directory", "allow-plaintext": True, "user-dn": "u={username}"},
                           "", "lisa", "pw")
    assert fake.events[0] == ("server", None)


# -- login throttling --
def test_throttle_counts_attempts_in_progress():
    t = auth.LoginThrottle(limit=2, window=60)
    assert t.reserve("ip") and t.reserve("ip") and not t.reserve("ip")
    t.failed("ip", reserved=True)
    assert not t.reserve("ip")  # one failure + one attempt still running
    t.succeeded("ip", reserved=True)
    assert t.reserve("ip")
    t.cancel("ip")
    assert t._pending == {} and t._failures == {}


def test_throttle_forgets_idle_clients(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(auth.time, "monotonic", lambda: clock[0])
    t = auth.LoginThrottle(limit=2, window=60)
    for client in ("a", "b", "c"):
        assert t.reserve(client)
        t.failed(client, reserved=True)
    clock[0] += 61
    t.reserve("d")
    assert t._failures == {} and t._pending == {"d": 1}


# -- users file --
def test_invalid_or_removed_users_file_fails_closed(tmp_path, monkeypatch):
    from streamhub.catalog import User

    monkeypatch.delenv("STREAMHUB_ADMIN_PASSWORD", raising=False)
    catalog = make_catalog(tmp_path)
    users = tmp_path / "streamhub-users.json"
    hashed = auth.hash_password("pw", iterations=1000)
    write(users, {"alice": {"password": hashed, "role": "admin", "boards": ["*"]},
                  "olga": {"source": "oidc", "role": "guest", "boards": []}})
    local = auth.session_value(User("alice", "", "admin", ["*"]))
    sso = auth.session_value(User("sam", "", "user", [], source="oidc"))
    assert auth.user_from_session(local, catalog) and auth.user_from_session(sso, catalog)
    assert catalog.errors() == {}

    users.write_text("{ broken", encoding="utf-8")
    os.utime(users, ns=(1, 1))
    assert auth.user_from_session(local, catalog) is None
    assert auth.user_from_session(sso, catalog) is None  # the file may hold an override for sam
    assert auth.sso_user("olga", "oidc", ["x"], catalog.settings, catalog) is None
    assert "users" in catalog.errors()
    monkeypatch.setenv("STREAMHUB_ADMIN_PASSWORD", "recover")
    assert catalog.user("admin") is not None  # the recovery path
    monkeypatch.delenv("STREAMHUB_ADMIN_PASSWORD")

    write(users, {"alice": {"password": hashed, "role": "admin", "boards": ["*"]}})
    assert auth.user_from_session(local, catalog) and catalog.users_error == ""
    users.unlink()
    assert auth.user_from_session(local, catalog) is None and auth.user_from_session(sso, catalog) is None
    assert "disappeared" in catalog.users_error


def test_users_file_rejects_unknown_roles(tmp_path):
    catalog = make_catalog(tmp_path)
    write(tmp_path / "streamhub-users.json", {"bob": {"password": "x", "role": "superuser"}})
    assert catalog.users() == {} and "role" in catalog.users_error


# -- launches, readiness and bind check (SEC-12) --
class FakeProcess:
    pid = 0

    def __init__(self):
        self.exited = asyncio.Event()

    async def wait(self):
        await self.exited.wait()
        return 0


class SlowRuntime:
    name, uses_local_port = "process", True

    def __init__(self):
        self.prepared, self.released = 0, []

    async def prepare(self, app, port):
        from streamhub.runtimes import Launch

        self.prepared += 1
        await asyncio.sleep(0.05)
        return Launch(argv=["app"], upstream=f"http://127.0.0.1:{port}", probe="bind", handle=f"res-{port}")

    async def release(self, inst):
        self.released.append(inst.runtime_handle)


def slow_manager(tmp_path, runtime, monkeypatch, fail_spawn=False):
    from streamhub.ports import PortAllocator

    catalog = make_catalog(tmp_path, [{"app_id": "a.py", "file": "a.py", "health_path": ""}],
                           {"startup-timeout": 60})
    ports = PortAllocator(42000, 42010, [])
    manager = AppManager(catalog.settings, catalog, ports, "http://127.0.0.1:8500", "token")
    manager.runtimes["process"] = runtime

    async def spawn(app, launch):
        if fail_spawn:
            raise OSError("no such interpreter")
        return FakeProcess(), None

    monkeypatch.setattr(manager, "_spawn", spawn)
    return catalog, manager, ports


def test_concurrent_starts_share_one_launch(tmp_path, monkeypatch):
    runtime = SlowRuntime()
    catalog, manager, ports = slow_manager(tmp_path, runtime, monkeypatch)

    async def scenario():
        app = catalog.find("a.py")
        results = await asyncio.gather(*(manager.start(app) for _ in range(5)))
        assert runtime.prepared == 1 and len({id(r) for r in results}) == 1
        assert len(ports.leased) == 1 and manager._starting == {}
        manager.instances.clear()

    asyncio.run(scenario())


def test_failed_launch_releases_port_and_resources(tmp_path, monkeypatch):
    from streamhub.launcher import LaunchError

    runtime = SlowRuntime()
    catalog, manager, ports = slow_manager(tmp_path, runtime, monkeypatch, fail_spawn=True)

    async def scenario():
        results = await asyncio.gather(*(manager.start(catalog.find("a.py")) for _ in range(3)),
                                       return_exceptions=True)
        assert all(isinstance(r, LaunchError) for r in results) and runtime.prepared == 1
        assert ports.leased == set() and len(runtime.released) == 1 and runtime.released[0].startswith("res-")

    asyncio.run(scenario())


def test_no_launch_after_close(tmp_path, monkeypatch):
    from streamhub.launcher import LaunchError

    catalog, manager, _ = slow_manager(tmp_path, SlowRuntime(), monkeypatch)

    async def scenario():
        await manager.close()
        with pytest.raises(LaunchError, match="shutting down"):
            await manager.start(catalog.find("a.py"))

    asyncio.run(scenario())


SILENT_APP = "import time\ntime.sleep(60)\n"


def test_startup_timeout_is_a_failure(tmp_path):
    from streamhub.launcher import STOPPED
    from streamhub.ports import PortAllocator

    (tmp_path / "silent.py").write_text(SILENT_APP, encoding="utf-8")
    catalog = make_catalog(tmp_path, [{"app_id": "s.py", "file": "silent.py", "health_path": ""}],
                           {"startup-timeout": 1, "stop-timeout": 1})
    manager = AppManager(catalog.settings, catalog, PortAllocator(42100, 42110, []), "http://127.0.0.1:8500", "t")

    async def scenario():
        inst = await manager.start(catalog.find("s.py"))
        for _ in range(150):
            if inst.state == STOPPED:
                break
            await asyncio.sleep(0.1)
        assert inst.state == STOPPED and not inst.ready
        assert "did not answer" in inst.error and inst.exit_code is not None

    asyncio.run(scenario())


def test_bind_check_refuses_exposed_apps(tmp_path, monkeypatch):
    from streamhub.launcher import AppInstance

    catalog = make_catalog(tmp_path, [{"app_id": "a.py", "file": "a.py"}], {"bind-check": "refuse"})
    manager = AppManager(catalog.settings, catalog, None, "", "")
    monkeypatch.setattr(platform_utils, "exposed_listeners", lambda pid: ["0.0.0.0:9100"])
    terminated = []

    async def terminate(inst):
        terminated.append(inst.app_id)

    monkeypatch.setattr(manager, "_terminate", terminate)
    inst = AppInstance(app=catalog.find("a.py"), port=9100, upstream="", strip_prefix=True, process=FakeProcess(),
                       runtime=manager.runtimes["process"])
    inst.process.pid = 1234
    assert asyncio.run(manager._bind_ok(inst)) is False
    assert terminated == ["a.py"] and inst.stopping and "0.0.0.0:9100" in inst.error
    manager.settings.bind_check = "warn"
    assert asyncio.run(manager._bind_ok(inst)) is True


def test_exposed_listeners_ignores_loopback():
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        assert platform_utils.exposed_listeners(os.getpid()) == []


# -- identity assertions --
def test_identity_assertion_is_bound_to_one_app_and_expires():
    from streamhub.catalog import User

    key_a, key_b = auth.app_key("hub-secret", "a.sl"), auth.app_key("hub-secret", "b.sl")
    assert key_a != key_b
    token = auth.identity_assertion(key_a, User("ann", "", "manager", []), "a.sl", now=1000)
    claims = auth.verify_identity(token, key_a, "a.sl", now=1010)
    assert claims["sub"] == "ann" and claims["role"] == "manager" and claims["aud"] == "a.sl"
    for key, app_id, now in [(key_b, "a.sl", 1010), (key_a, "b.sl", 1010), (key_a, "a.sl", 2000)]:
        with pytest.raises(ValueError):
            auth.verify_identity(token, key, app_id, now=now)
    header, _, signature = token.split(".")
    forged = auth._b64url(json.dumps({**claims, "role": "admin"}).encode())
    with pytest.raises(ValueError):
        auth.verify_identity(f"{header}.{forged}.{signature}", key_a, "a.sl", now=1010)
    with pytest.raises(ValueError):
        auth.verify_identity("garbage", key_a, "a.sl")


def test_identity_assertion_is_a_standard_jwt():
    jwt = pytest.importorskip("jwt")
    from streamhub.catalog import User

    key = auth.app_key("hub-secret", "a.sl")
    token = auth.identity_assertion(key, User("ann", "", "user", []), "a.sl")
    claims = jwt.decode(token, key, algorithms=["HS256"], audience="a.sl", issuer="streamhub")
    assert claims["sub"] == "ann"


# -- apps of a crashed hub --
SLEEPER = [sys.executable, "-c", "import time; time.sleep(60)"]


def wait_dead(proc, seconds=10):
    import psutil

    try:
        psutil.Process(proc.pid).wait(seconds)
    except psutil.NoSuchProcess:
        pass
    return proc.poll() is not None


def test_kill_leftover_checks_the_start_time():
    import subprocess

    proc = subprocess.Popen(SLEEPER, **platform_utils.new_group_kwargs())
    try:
        created = platform_utils.process_started(proc.pid)
        assert platform_utils.kill_leftover(proc.pid, created + 3600) == 0  # PID reused by someone else
        assert proc.poll() is None
        assert platform_utils.kill_leftover(proc.pid, created) >= 1
        assert wait_dead(proc)
    finally:
        proc.kill()


def test_sweep_stops_processes_left_by_a_previous_hub(tmp_path):
    import subprocess

    catalog = make_catalog(tmp_path)
    manager = AppManager(catalog.settings, catalog, None, "", "")
    proc = subprocess.Popen(SLEEPER, **platform_utils.new_group_kwargs())
    try:
        manager._record("old.py", proc.pid)
        assert json.loads(manager.registry_path.read_text(encoding="utf-8"))["old.py"]["pid"] == proc.pid
        asyncio.run(manager.sweep())
        assert wait_dead(proc) and not manager.registry_path.exists()
    finally:
        proc.kill()


HUB_STANDIN = """
import subprocess, sys, time
from streamhub import platform_utils
assert platform_utils.kill_children_with_hub()
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
print(child.pid, flush=True)
time.sleep(60)
"""


@pytest.mark.skipif(not platform_utils.IS_WINDOWS, reason="Job Objects are Windows only")
def test_windows_job_kills_apps_with_a_killed_hub():
    import subprocess

    import psutil

    hub = subprocess.Popen([sys.executable, "-c", HUB_STANDIN], stdout=subprocess.PIPE, text=True)
    try:
        child = psutil.Process(int(hub.stdout.readline()))
        hub.kill()  # TerminateProcess: no cleanup code runs in the hub
        child.wait(10)
        assert not child.is_running()
    finally:
        hub.kill()


# -- usage survives restarts --
def test_usage_is_saved_and_restored(tmp_path):
    from datetime import datetime, timedelta

    from streamhub.usage import UsageStore

    store = UsageStore(tmp_path / "usage.sqlite3", retention_days=30)
    now = datetime.now()
    usage = store.for_app("a.sl")
    for _ in range(3):
        usage.add(now)
    store.for_app("old.sl").add(now - timedelta(days=40))
    asyncio.run(store.flush())
    usage.add(now)
    asyncio.run(store.flush())

    restored = UsageStore(tmp_path / "usage.sqlite3", retention_days=30)
    restored.load()
    assert restored.for_app("a.sl").today()[now.hour] == 4 and restored.for_app("a.sl").total == 4
    assert restored.for_app("old.sl") == {} and restored.for_app("old.sl").total == 1  # day pruned, total kept


def test_usage_write_failure_keeps_the_counts(tmp_path):
    from streamhub.usage import UsageStore

    store = UsageStore(tmp_path / "missing" / "usage.sqlite3")
    (tmp_path / "missing").write_text("a file, not a folder", encoding="utf-8")
    store.for_app("a.sl").add()
    asyncio.run(store.flush())
    assert sum(store.for_app("a.sl").pending.values()) == 1


# -- COMPAT-5: st.user --
def test_streamlit_user_headers_are_opt_in(tmp_path):
    catalog = make_catalog(tmp_path, [{"app_id": "a.sl", "file": "a.py"},
                                      {"app_id": "b.sl", "file": "b.py", "streamlit_user_headers": True}])
    manager = AppManager(catalog.settings, catalog, None, "", "")

    def flag(app_id):
        argv = manager.build_argv(catalog.find(app_id), 9000)
        return next((a for a in argv if a.startswith("--server.trustedUserHeaders=")), None)

    assert flag("a.sl") is None and flag("help.cmd") is None
    assert json.loads(flag("b.sl").split("=", 1)[1]) == {"X-Streamhub-User": "name", "X-Streamhub-Role": "role"}
    catalog.settings.streamlit_user_headers = True
    assert flag("a.sl") and flag("help.cmd") is None


# -- streamhub check --
def test_check_command(tmp_path):
    from click.testing import CliRunner

    from streamhub import cli

    write(tmp_path / "streamhub.json", {"slack-hook": "https://hooks.example/secret-path", "env-passthrough": ["STREAMHUB_*"]})
    write(tmp_path / "streamhub-apps.json", [{"boards": [{"name": "a.brd"}]},
                                             {"app_id": "a.py", "file": "missing.py", "board": ["b.brd"]}])
    write(tmp_path / "streamhub-users.json", {"bob": {"password": "raw", "role": "user"}})
    result = CliRunner().invoke(cli.main, ["check", str(tmp_path)])
    assert result.exit_code == 1
    output = result.output + (result.stderr if result.stderr_bytes is not None else "")
    assert "raw passwords for bob" in output and "board 'b.brd' is not defined" in output
    assert "file not found" in output and "'slack-hook' is in the file" in output and "passes hub secrets" in output
    assert "secret-path" not in output and not (tmp_path / ".streamhub-secret").exists()

    write(tmp_path / "streamhub-users.json", {})
    write(tmp_path / "streamhub.json", {})
    (tmp_path / "missing.py").write_text("", encoding="utf-8")
    write(tmp_path / "streamhub-apps.json", [{"boards": [{"name": "a.brd"}]}, {"app_id": "a.py", "file": "missing.py"}])
    result = CliRunner().invoke(cli.main, ["check", str(tmp_path)])
    assert result.exit_code == 0 and "0 error(s), 0 warning(s)" in result.output
    assert CliRunner().invoke(cli.main, ["check", "streamhub/demo/config"]).exit_code == 0


# -- revocable sessions across instances --
def test_revocation_reaches_other_instances(tmp_path):
    from streamhub.catalog import User
    from streamhub.sessions import SessionStore, user_key

    path = tmp_path / ".streamhub-sessions.sqlite3"
    a, b = SessionStore(path, 7), SessionStore(path, 7)
    user = User("ann", "", "user", [])

    async def scenario():
        await a.created("s1", user, "10.0.0.1", "browser")
        await a.created("s2", user, "10.0.0.2", "browser")
        assert b.is_valid("s1", user_key("ann", "local"), 1000)
        await a.revoke("s1")
        await b.refresh()
        assert not b.is_valid("s1", user_key("ann", "local"), 1000) and b.is_valid("s2", "local:ann", 1000)
        await b.revoke_user("ann", "local")
        await a.refresh()
        assert not a.is_valid("s2", "local:ann", 1000) and not a.is_valid(None, "local:ann", None)  # pre-2.2 cookie
        assert a.is_valid("s3", "local:ann", time.time() + 1)  # a login after the revocation
        assert a.active() == []

    asyncio.run(scenario())


# -- handlers: concurrent logins, streamed uploads, identity headers --
import tornado.gen  # noqa: E402
import tornado.httpserver  # noqa: E402
import tornado.testing  # noqa: E402
import tornado.web  # noqa: E402

from pathlib import Path  # noqa: E402

from test_handlers import HubTestCase  # noqa: E402


class UpstreamApp:
    """A plain HTTP app on its own port that records what the proxy sends it."""

    def __init__(self):
        self.requests = []
        self.delay = 0
        sock, self.port = tornado.testing.bind_unused_port()
        upstream = self

        @tornado.web.stream_request_body
        class Echo(tornado.web.RequestHandler):
            def prepare(self):
                self.size, self.chunks = 0, 0

            def data_received(self, chunk):
                self.size += len(chunk)
                self.chunks += 1

            def post(self):
                upstream.requests.append({"headers": self.request.headers, "size": self.size, "chunks": self.chunks})
                self.write({"size": self.size})

            put = post

            async def get(self):
                upstream.requests.append({"headers": self.request.headers, "size": 0, "chunks": 0})
                await asyncio.sleep(upstream.delay)
                self.write("ok")

        self.server = tornado.httpserver.HTTPServer(tornado.web.Application([(r"/.*", Echo)]),
                                                    max_body_size=1024 ** 3)
        self.server.add_sockets([sock])


class TestProxyAndLogin(HubTestCase):
    def get_app(self):
        from streamhub.launcher import RUNNING, AppInstance

        app = super().get_app()
        self.upstream = UpstreamApp()
        catalog = self.hub.catalog
        self.hub.manager.instances["a.sl"] = AppInstance(
            app=catalog.find("a.sl"), port=0, upstream=f"http://127.0.0.1:{self.upstream.port}", strip_prefix=True,
            state=RUNNING)
        return app

    def tearDown(self):
        self.upstream.server.stop()
        super().tearDown()

    def test_uploads_are_streamed_with_their_length(self):
        body = b"x" * (3 * 1024 * 1024 + 7)
        response = self.fetch("/a.sl/upload", method="POST", body=body)
        assert response.code == 200 and json.loads(response.body) == {"size": len(body)}
        seen = self.upstream.requests[-1]
        assert seen["headers"]["Content-Length"] == str(len(body)) and seen["chunks"] > 1

    def test_upload_limit(self):
        self.hub.settings.max_upload_mb = 1
        try:
            code = self.fetch("/a.sl/upload", method="PUT", body=b"x" * (2 * 1024 * 1024), raise_error=False).code
        except OSError:  # the hub closes the connection once the limit is passed
            code = 0
        assert code in (0, 400) and not self.upstream.requests

    def test_apps_get_a_verifiable_identity(self):
        b = self.browser("usr")
        assert b.fetch("/a.sl/page").code == 200
        headers = self.upstream.requests[-1]["headers"]
        key = auth.app_key(self.hub.internal_token, "a.sl")
        claims = auth.verify_identity(headers["X-Streamhub-Identity"], key, "a.sl")
        assert claims["sub"] == "usr" and claims["role"] == "user" and headers["X-Streamhub-User"] == "usr"
        # a client cannot send its own
        self.fetch("/a.sl/page", headers={"X-Streamhub-Identity": "forged", "X-Streamhub-User": "admin"})
        headers = self.upstream.requests[-1]["headers"]
        assert "X-Streamhub-Identity" not in headers and "X-Streamhub-User" not in headers

    def test_metrics_need_a_manager_or_the_token(self):
        assert self.fetch("/metrics").code == 401
        assert self.browser("usr").fetch("/metrics").code == 403
        self.browser("usr").fetch("/a.sl/page")
        body = self.browser("mgr").fetch("/metrics").body.decode()
        assert 'streamhub_app_up{app="a.sl"} 1' in body and "streamhub_login_failures_total 0" in body
        assert "usr" not in body  # no user names
        self.hub.settings.metrics_token = "scrape-me"
        assert self.fetch("/metrics", headers={"Authorization": "Bearer wrong"}).code == 401
        assert self.fetch("/metrics", headers={"Authorization": "Bearer scrape-me"}).code == 200

    def test_pages_need_no_cdn(self):
        import re

        page = self.fetch("/login/").body.decode()
        assert "cdnjs" not in page and "jsdelivr" not in page
        for url in re.findall(r'href="(/static/[^"]+)"', page):
            assert self.fetch(url).code == 200, url
        css = self.fetch("/static/vendor/font-awesome/css/font-awesome.min.css").body.decode()
        assert self.fetch("/static/vendor/font-awesome/fonts/fontawesome-webfont.woff2").code == 200 and "woff2" in css

    def test_editor_validates_schemas_and_detects_concurrent_edits(self):
        admin = self.browser("admin")
        apps = admin.json("/api/admin/files/apps")
        data = json.loads(apps["text"])
        duplicate = data + [{"app_id": "a.sl", "file": "x.py"}]
        refused = admin.fetch("/api/admin/files/apps", "POST", json_body={"text": json.dumps(duplicate),
                                                                         "version": apps["version"]})
        assert refused.code == 400 and "used twice" in json.loads(refused.body)["error"]
        bad_role = admin.fetch("/api/admin/files/users", "POST",
                               json_body={"text": json.dumps({"x": {"password": "pw", "role": "boss"}})})
        assert bad_role.code == 400 and "role" in json.loads(bad_role.body)["error"]
        # someone else saves in between: the stale editor is refused
        (self.dir / "streamhub-apps.json").write_text(json.dumps(data[:2]), encoding="utf-8")
        stale = admin.fetch("/api/admin/files/apps", "POST", json_body={"text": json.dumps(data),
                                                                       "version": apps["version"]})
        assert stale.code == 409
        fresh = admin.json("/api/admin/files/apps")
        warned = data + [{"app_id": "z.py", "file": "z.py", "board": ["nowhere.brd"]}]
        saved = admin.fetch("/api/admin/files/apps", "POST", json_body={"text": json.dumps(warned),
                                                                       "version": fresh["version"]})
        result = json.loads(saved.body)
        assert saved.code == 200 and any("nowhere.brd" in w for w in result["warnings"])
        assert not list(self.dir.glob(".*.tmp"))  # written through a temporary file, then replaced

    def test_admin_page_shows_file_problems(self):
        users = self.dir / "streamhub-users.json"
        admin = self.browser("admin")
        users.write_text("{ broken", encoding="utf-8")
        os.utime(users, ns=(1, 1))
        os.environ["STREAMHUB_ADMIN_PASSWORD"] = "recover"
        try:
            recovery = self.browser()
            assert recovery.login("admin", "recover").code == 302
            problems = recovery.json("/api/admin/state")["problems"]
        finally:
            del os.environ["STREAMHUB_ADMIN_PASSWORD"]
        assert problems and "users" in problems[0]
        assert admin.fetch("/admin/").code == 302  # the file admin's session ended with the file

    def test_demo_admin_password_is_flagged(self):
        os.environ["STREAMHUB_ADMIN_PASSWORD"] = "admin"
        try:
            demo = self.browser()
            assert demo.login("admin", "admin").code == 302
            assert any("demo default" in p for p in demo.json("/api/admin/state")["problems"])
            os.environ["STREAMHUB_ADMIN_PASSWORD"] = "a-real-one"
            assert not any("demo default" in p for p in demo.json("/api/admin/state")["problems"])
        finally:
            del os.environ["STREAMHUB_ADMIN_PASSWORD"]

    def test_git_commits_only_the_hub_files(self):
        from streamhub.handlers.admin_page import GitHandler

        handler = GitHandler.__new__(GitHandler)
        handler.hub = self.hub
        (self.dir / "streamhub-news.json").write_text("[]", encoding="utf-8")
        files = handler.committed_files(self.dir)
        names = sorted(Path(f).name for f in files)
        assert names == ["streamhub-apps.json", "streamhub-news.json", "streamhub.json"]

    def test_sessions_can_be_listed_and_revoked(self):
        usr, admin = self.browser("usr"), self.browser("admin")
        self.io_loop.run_sync(self.hub.sessions.settle)
        listed = admin.json("/api/admin/sessions")
        assert {s["name"] for s in listed["sessions"]} == {"usr", "admin"} and listed["current"]
        target = next(s["id"] for s in listed["sessions"] if s["name"] == "usr")
        assert self.browser("mgr").fetch("/api/admin/sessions").code == 403  # admins only
        assert usr.fetch("/api/apps").code == 200 and usr.fetch("/out/b.py/").code == 200
        assert admin.fetch("/api/admin/sessions", "POST", json_body={"id": target}).code == 200
        assert usr.fetch("/out/b.py/").code == 302  # signed out
        again = self.browser("usr")
        assert again.fetch("/out/b.py/").code == 200  # a new login works
        assert admin.fetch("/api/admin/sessions", "POST", json_body={"user": "usr", "source": "local"}).code == 200
        assert again.fetch("/out/b.py/").code == 302

    def test_logout_revokes_a_copied_cookie(self):
        usr = self.browser("usr")
        copied = dict(usr.cookies)
        usr.fetch("/logout/", "POST", form={})
        thief = self.browser()
        thief.cookies = copied
        assert thief.fetch("/out/b.py/").code == 302

    def test_sso_sessions_expire_after_sso_session_minutes(self):
        from streamhub.catalog import User

        self.hub.settings.sso_session_minutes = 60
        user = User("sam", "", "admin", ["*"], source="oidc")
        fresh = auth.session_value(user, "sid-1", time.time() - 59 * 60)
        stale = auth.session_value(user, "sid-2", time.time() - 61 * 60)
        for value, code in ((fresh, 200), (stale, 302)):
            cookie = self.hub.application.settings["cookie_secret"]
            signed = tornado.web.create_signed_value(cookie, "user", value).decode()
            assert self.fetch("/admin/", headers={"Cookie": f"user={signed}"}, follow_redirects=False).code == code

    @tornado.testing.gen_test
    async def test_shutdown_drains_requests_then_gives_up(self):
        self.hub.settings.drain_timeout = 5
        self.upstream.delay = 0.5
        request = self.http_client.fetch(self.get_url("/a.sl/slow"), raise_error=False)
        await asyncio.sleep(0.2)
        assert self.hub.active_requests == 1
        started = time.monotonic()
        await self.hub.shutdown(trigger="test")
        response = await request
        assert response.code == 200 and self.hub.active_requests == 0 and time.monotonic() - started < 3
        # an open WebSocket session that never ends: shutdown waits drain-timeout, then goes on
        self.hub._stopping, self.hub.settings.drain_timeout = False, 0.3
        from streamhub.launcher import RUNNING, AppInstance

        self.hub.manager.instances["a.sl"] = AppInstance(app=self.hub.catalog.find("a.sl"), port=0, upstream="",
                                                         strip_prefix=True, state=RUNNING, active_ws=1)
        started = time.monotonic()
        await self.hub.shutdown(trigger="test")
        assert 0.3 <= time.monotonic() - started < 2
        assert (await self.http_client.fetch(self.get_url("/h.py/"), raise_error=False)).code == 503  # no launches

    @tornado.testing.gen_test
    async def test_concurrent_failed_logins_stay_within_the_limit(self):
        self.hub.login_throttle = auth.LoginThrottle(limit=2, window=60)
        checked = []
        handler_class = None
        for rule in self.hub.application.wildcard_router.rules:
            if getattr(rule.matcher, "_path", None) == "/login/":
                handler_class = rule.target
        original = handler_class._authenticate

        async def slow(handler, username, password):
            checked.append(username)
            await asyncio.sleep(0.2)
            return None

        handler_class._authenticate = slow
        try:
            first = await self.http_client.fetch(self.get_url("/login/"))
            xsrf = first.headers["Set-Cookie"].split("_xsrf=")[1].split(";")[0]
            body = f"username=x&password=y&_xsrf={xsrf}"
            responses = await tornado.gen.multi([
                self.http_client.fetch(self.get_url("/login/"), method="POST", body=body, raise_error=False,
                                       headers={"Cookie": f"_xsrf={xsrf}"}) for _ in range(8)])
        finally:
            handler_class._authenticate = original
        codes = sorted(r.code for r in responses)
        assert len(checked) == 2 and codes == [401, 401] + [429] * 6
