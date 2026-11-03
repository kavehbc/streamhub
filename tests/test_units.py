import json
import os
import socket
import sys
from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from streamhub import auth, platform_utils
from streamhub.app import KEEP_IN_TEMP, clean_folder
from streamhub.catalog import Catalog, User, app_kind
from streamhub.config import _KEYS, RESTART_ONLY, SETTINGS_FORM, ConfigError, Settings, config_keys, load_settings
from streamhub.handlers.base import safe_next
from streamhub.launcher import AppManager
from streamhub.ports import PortAllocator, PortsExhausted
from streamhub.proxy import split_app_path, strip_hub_cookies
from streamhub.scheduler import next_run


def write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# -- config --
def test_settings_form_covers_every_key_once():
    keys = [field[0] for _, fields in SETTINGS_FORM for field in fields]
    assert sorted(keys) == sorted([*_KEYS, "schedule"])
    assert set(RESTART_ONLY) <= {f for f in Settings.__dataclass_fields__}
    assert config_keys(["port_range", "cdf_path"]) == ["port-range", "cdf"]


def test_admin_forms_name_real_keys_and_choices():
    """Every sub-form key is one the hub reads, every choice list exists, and the labelled option lists
    match the values the parsers accept."""
    from pathlib import Path

    from streamhub import catalog
    from streamhub.config import BIND_CHECKS, CHOICES, SUBFORMS, settings_form

    source = "".join(p.read_text(encoding="utf-8") for p in Path(catalog.__file__).parent.rglob("*.py")
                     if p.name != "config.py")
    lists = set(CHOICES) | {"roles", "events"}
    for form, fields in SUBFORMS.items():
        for key, kind, *_ in fields:
            assert f'"{key}"' in source, f"{form}.{key} is not read anywhere"
            assert ":" not in kind or kind.split(":")[1] in lists, kind
    kinds = {f["kind"] for section in settings_form() for f in section["fields"]}
    assert {k.split(":")[1] for k in kinds if k.startswith("choice:")} <= lists
    assert {k.split(":")[1] for k in kinds if k.startswith(("object:", "list:"))} <= set(SUBFORMS)
    assert [v for v, _ in CHOICES["bind-check"]] == list(BIND_CHECKS)
    assert {t[0] for t in catalog.TYPE_CHOICES} == set(catalog.TYPES)
    assert [v for v, _ in catalog.DISPLAY_CHOICES] == list(catalog.DISPLAY_VALUES)
    assert [v for v, _ in catalog.RESTART_CHOICES] == list(catalog.RESTART_POLICIES)
    assert {v for v, _ in catalog.SERVES_CHOICES} == set(catalog.SERVES)
    assert [v for v, _ in catalog.NEWS_CHOICES] == list(catalog.NEWS_TYPES)
    assert set(auth.ROLE_HELP) == set(auth.ROLES)


def test_settings_form_flags_environment_overrides(monkeypatch):
    from streamhub.config import settings_form

    monkeypatch.setenv("STREAMHUB_COOKIE_SECRET", "from-env")
    fields = {f["key"]: f for section in settings_form() for f in section["fields"]}
    assert fields["cookie-secret"]["env"] == "STREAMHUB_COOKIE_SECRET" and fields["cookie-secret"]["envSet"]
    assert fields["slack-hook"]["env"] == "STREAMHUB_SLACK_HOOK" and not fields["slack-hook"]["envSet"]
    assert fields["port"]["env"] == "" and "from-env" not in json.dumps(settings_form())


def test_old_layout_name_still_works(tmp_path):
    write(tmp_path / "streamhub.json", {"template-file": "main_2.html"})
    settings = load_settings(tmp_path)
    assert settings.template_file == "main_side.html" and (settings.template_folder / "main_side.html").is_file()


def test_config_rejects_an_unknown_time_zone(tmp_path):
    write(tmp_path / "streamhub.json", {"timezone": "Mars/Olympus"})
    with pytest.raises(ConfigError, match="unknown time zone"):
        load_settings(tmp_path)
    write(tmp_path / "streamhub.json", {"timezone": "Europe/Paris"})
    assert load_settings(tmp_path).timezone == "Europe/Paris"


def test_config_defaults_without_file(tmp_path):
    s = load_settings(tmp_path)
    assert s.port == 8500 and s.schedule == "02:00"
    assert s.apps_file == tmp_path / "streamhub-apps.json"
    assert s.temp_path == tmp_path / "temp"
    assert (tmp_path / ".streamhub-secret").is_file() and s.cookie_secret


def test_config_nulls_relative_paths_and_schedule_off(tmp_path):
    write(tmp_path / "streamhub.json", {"port": None, "ssl_port": None, "schedule": None, "apps": "a/apps.json",
                                        "temp": "", "master-password": "x", "port-exception": [1, 2]})
    s = load_settings(tmp_path / "streamhub.json")
    assert s.port == 8500 and s.ssl_port == 0 and s.schedule is None
    assert s.apps_file == (tmp_path / "a" / "apps.json").resolve()
    assert s.port_exceptions == [1, 2]


def test_config_rejects_bad_values(tmp_path):
    write(tmp_path / "streamhub.json", {"port": "abc"})
    with pytest.raises(ConfigError):
        load_settings(tmp_path)
    write(tmp_path / "streamhub.json", {"schedule": "25:00"})
    with pytest.raises(ConfigError):
        load_settings(tmp_path)


def test_config_secrets_from_environment(tmp_path, monkeypatch):
    write(tmp_path / "streamhub.json", {"slack-hook": "from-file"})
    monkeypatch.setenv("STREAMHUB_SLACK_HOOK", "from-env")
    monkeypatch.setenv("STREAMHUB_COOKIE_SECRET", "s3cret")
    s = load_settings(tmp_path)
    assert s.slack_hook == "from-env" and s.cookie_secret == "s3cret"


# -- catalog --
APPS = [
    {"boards": [{"name": "open.brd", "label": "Open", "auth": False},
                {"name": "closed.brd", "label": "Closed", "auth": True}]},
    {"board": ["open.brd"], "app_id": "a.sl", "app_name": "A", "file": "a.py", "folder": "apps"},
    {"board": ["closed.brd"], "app_id": "b.py", "app_name": "B", "file": "b.py",
     "children": [{"board": ["closed.brd"], "app_id": "c.url", "url": "https://example.com"}]},
]


@pytest.fixture
def catalog(tmp_path):
    write(tmp_path / "streamhub-apps.json", APPS)
    return Catalog(load_settings(tmp_path))


def test_catalog_lookup_and_defaults(catalog, tmp_path):
    a = catalog.find("a.sl")
    assert a.kind == "sl" and a.children == [] and a.display == "show"
    assert a.folder == (tmp_path / "apps").resolve()
    assert catalog.find("c.url").url == "https://example.com"
    assert catalog.find("missing.sl") is None
    assert catalog.find("other.cmd") is None
    assert catalog.find("status.cmd") is None  # replaced by /admin/ in 2.1


def test_catalog_keeps_last_good_file(catalog, tmp_path):
    assert catalog.find("a.sl")
    path = tmp_path / "streamhub-apps.json"
    path.write_text("{ broken", encoding="utf-8")
    os.utime(path, ns=(1, 1))
    assert catalog.find("a.sl") is not None


def test_app_kinds():
    assert [app_kind(x) for x in ("x.sl", "x.py", "x.url", "x.curl", "x.cmd", "clear")] == \
        ["sl", "py", "url", "curl", "cmd", "internal"]


# -- auth --
def test_password_hash_roundtrip_and_raw_passwords_refused():
    hashed = auth.hash_password("secret", iterations=1000)
    assert auth.verify_password(hashed, "secret") and not auth.verify_password(hashed, "nope")
    assert auth.is_hashed(hashed) and not auth.is_hashed("plain") and not auth.is_hashed("pbkdf2_sha256$x$y$z")
    assert not auth.verify_password("plain", "plain", "legacy")  # raw passwords never log in
    assert not auth.verify_password("pbkdf2_sha256$0$AA==$AA==", "", "zero-iterations")


def test_env_admin_password_is_hashed_in_memory(tmp_path, monkeypatch):
    monkeypatch.setenv("STREAMHUB_ADMIN_PASSWORD", "env-secret")
    admin = Catalog(load_settings(tmp_path)).user("admin")
    assert auth.is_hashed(admin.password) and "env-secret" not in admin.password
    assert auth.verify_password(admin.password, "env-secret")
    ready = auth.hash_password("pre-hashed", iterations=1000)
    monkeypatch.setenv("STREAMHUB_ADMIN_PASSWORD", ready)  # a hash is used as is
    assert Catalog(load_settings(tmp_path)).user("admin").password == ready


def test_hash_users_converts_only_raw_local_passwords():
    hashed = auth.hash_password("kept", iterations=1000)
    data = {"__comment__": {"roles": []}, "a": {"password": "raw-a", "role": "user"}, "b": {"password": hashed},
            "c": {"source": "oidc", "role": "admin"}, "d": {"password": 1234}}
    assert auth.hash_users(data) == ["a", "d"]
    assert auth.verify_password(data["a"]["password"], "raw-a") and auth.verify_password(data["d"]["password"], "1234")
    assert data["b"]["password"] == hashed and "password" not in data["c"]
    assert auth.hash_users(data) == []


def test_access_rules(catalog):
    guest = None
    user = User("u", "", "user", ["closed.brd"])
    other = User("o", "", "user", [])
    manager = User("m", "", "manager", [])
    a, b = catalog.find("a.sl"), catalog.find("b.py")
    assert auth.can_access_app(guest, a, catalog)
    assert not auth.can_access_app(guest, b, catalog)
    assert auth.can_access_app(user, b, catalog)
    assert not auth.can_access_app(other, b, catalog)
    tool = replace(a, min_role="manager")
    assert not auth.can_access_app(user, tool, catalog) and auth.can_access_app(manager, tool, catalog)
    assert auth.can_access_app(guest, catalog.find("help.cmd"), catalog)


def test_login_throttle():
    t = auth.LoginThrottle(limit=2, window=60)
    t.failed("ip")
    t.failed("ip")
    assert t.blocked("ip") and not t.blocked("other")
    t.succeeded("ip")
    assert not t.blocked("ip")


@pytest.mark.parametrize("target,expected", [
    ("/demo.brd/", "/demo.brd/"), ("//evil.com/", "/"), ("https://evil.com", "/"),
    ("/\\evil.com", "/"), ("", "/"), ("relative", "/"),
])
def test_safe_next(target, expected):
    assert safe_next(target) == expected


# -- ports and platform --
def test_port_allocator_skips_and_reuses():
    busy = {5002}
    ports = PortAllocator(5000, 5003, exceptions=[5000], is_free=lambda p: p not in busy)
    assert ports.allocate() == 5001
    assert ports.allocate() == 5003
    with pytest.raises(PortsExhausted):
        ports.allocate()
    ports.release(5001)
    assert ports.allocate() == 5001


def test_port_is_free_detects_listener():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        assert not platform_utils.port_is_free(sock.getsockname()[1])


def test_env_python_defaults_and_paths(tmp_path):
    assert platform_utils.env_python("") == sys.executable
    assert platform_utils.env_python(sys.prefix) in (sys.executable, str(platform_utils.prefix_python(sys.prefix)))
    with pytest.raises(LookupError):
        platform_utils.env_python(str(tmp_path))


def test_script_argv_by_extension(tmp_path):
    assert platform_utils.script_argv(tmp_path / "x.bat")[:2] == ["cmd", "/c"]
    assert platform_utils.script_argv(tmp_path / "x.ps1")[0] == "powershell"


# -- launcher argv --
def test_build_argv(catalog):
    settings = catalog.settings
    manager = AppManager(settings, catalog, None, "http://127.0.0.1:8500", "token")
    argv = manager.build_argv(catalog.find("a.sl"), 9001)
    assert argv[1:4] == ["-m", "streamlit", "run"]
    assert "--server.baseUrlPath=a.sl" in argv and "--server.address=127.0.0.1" in argv
    argv = manager.build_argv(catalog.find("b.py"), 9002)
    assert argv[-2:] == ["--port=9002", "--app_id=b.py"]
    custom = catalog.find("b.py")
    custom.command = ["{python}", "serve.py", "--listen", "{port}", "--root", "{base_path}"]
    assert manager.build_argv(custom, 9003)[1:] == ["serve.py", "--listen", "9003", "--root", "/b.py"]


# -- proxy helpers --
def test_split_app_path():
    assert split_app_path("/a.sl/x/y") == ("a.sl", "x/y")
    assert split_app_path("/a.sl/") == ("a.sl", "")
    assert split_app_path("/a.sl") is None and split_app_path("/") is None


def test_strip_hub_cookies():
    assert strip_hub_cookies('user="abc"; _xsrf=1; app=2') == "app=2"
    assert strip_hub_cookies("user=abc") == ""


# -- scheduler and temp folder --
def test_next_run_in_time_zone():
    tz = "America/Montreal"
    now = datetime(2026, 1, 1, 3, 0, tzinfo=ZoneInfo(tz))
    run = next_run("02:00", tz, now=now)
    assert (run.day, run.hour, run.minute) == (2, 2, 0)
    assert next_run("04:30", tz, now=now).day == 1


def test_clean_folder_keeps_marker_and_survives_locked_file(tmp_path):
    (tmp_path / KEEP_IN_TEMP).write_text("keep")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "f.txt").write_text("x")
    locked = tmp_path / "locked.txt"
    with open(locked, "w", encoding="utf-8"):
        clean_folder(tmp_path)
    assert (tmp_path / KEEP_IN_TEMP).exists() and not (tmp_path / "sub").exists()


def test_terminate_stops_grandchildren(tmp_path):
    import asyncio
    from types import SimpleNamespace

    import psutil

    script = tmp_path / "parent.py"
    script.write_text("import subprocess, sys, time\n"
                      "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
                      "time.sleep(60)\n", encoding="utf-8")

    async def run():
        proc = await asyncio.create_subprocess_exec(sys.executable, str(script), **platform_utils.new_group_kwargs())
        for _ in range(50):
            if psutil.Process(proc.pid).children():
                break
            await asyncio.sleep(0.1)
        tree = [proc.pid] + [c.pid for c in psutil.Process(proc.pid).children(recursive=True)]
        manager = AppManager(SimpleNamespace(stop_timeout=5, log_path=tmp_path, usage_retention_days=0), None, None, "", "")
        await manager._terminate(SimpleNamespace(process=proc, app_id="x", pid=proc.pid, runtime=None))
        return tree

    tree = asyncio.run(run())
    assert len(tree) >= 2  # parent and child (a venv launcher on Windows can add one more)
    assert not [pid for pid in tree if psutil.pid_exists(pid) and psutil.Process(pid).status() != psutil.STATUS_ZOMBIE]
