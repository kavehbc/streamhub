"""Unit tests for the 2.1 features: health paths, runtimes, SSO, sessions and notifiers."""
import asyncio
import base64
import json
import os

import pytest

from streamhub import auth, platform_utils
from streamhub.catalog import Catalog, User
from streamhub.config import ConfigError, load_settings
from streamhub.launcher import RUNNING, AppInstance, AppManager
from streamhub.proxy import strip_hub_cookies


def write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# -- settings --
def test_config_new_keys_and_instance_folders(tmp_path, monkeypatch):
    write(tmp_path / "streamhub.json", {"health-interval": 5, "instance-id": "hub-a", "sso-default-role": "user",
                                        "notifiers": [{"type": "teams", "url": "https://x"}]})
    monkeypatch.setenv("STREAMHUB_SMTP_PASSWORD", "pw")
    s = load_settings(tmp_path)
    assert s.health_interval == 5 and s.health_failures == 3 and s.instance_id == "hub-a"
    assert s.temp_path == tmp_path / "temp" / "hub-a" and s.log_path == tmp_path / "logs" / "hub-a"
    assert s.sso_default_role == "user" and s.smtp_password == "pw"


def test_instance_id_from_environment_is_validated(tmp_path, monkeypatch):
    monkeypatch.setenv("STREAMHUB_INSTANCE_ID", "Not Valid")
    with pytest.raises(ConfigError):
        load_settings(tmp_path)


@pytest.mark.parametrize("data", [
    {"instance-id": "Hub A"}, {"sso-default-role": "boss"}, {"notifiers": [{"type": "pager"}]},
    {"oidc": {"issuer": "https://idp"}}, {"ldap": {"bind-dn": "x"}}, {"group-mapping": ["x"]},
])
def test_config_rejects_bad_values(tmp_path, data):
    write(tmp_path / "streamhub.json", data)
    with pytest.raises(ConfigError):
        load_settings(tmp_path)


# -- app spec, health paths, runtimes --
def test_health_path_defaults_and_runtime_validation(tmp_path):
    write(tmp_path / "streamhub-apps.json", [
        {"boards": []},
        {"app_id": "s.sl", "file": "x.py"},
        {"app_id": "p.py", "file": "x.py"},
        {"app_id": "q.py", "file": "x.py", "health_path": "/healthz"},
        {"app_id": "t.sl", "file": "x.py", "health_path": ""},
        {"app_id": "d.sl", "file": "x.py", "runtime": "docker", "image": "img:1"}])
    catalog = Catalog(load_settings(tmp_path))
    assert catalog.find("s.sl").health == "_stcore/health" and catalog.find("p.py").health == ""
    assert catalog.find("q.py").health == "healthz" and catalog.find("t.sl").health == ""
    docker = catalog.find("d.sl")
    assert docker.runtime == "docker" and docker.port_in_container == 8501

    write(tmp_path / "streamhub-apps.json", [{"boards": []}, {"app_id": "e.sl", "runtime": "docker"}])
    assert Catalog(load_settings(tmp_path)).find("e.sl") is None  # rejected: no image


class _App:
    def __init__(self, app_id):
        self.app_id = app_id


def test_instance_url_for():
    sl = AppInstance(app=_App("a.sl"), port=1, upstream="http://127.0.0.1:1", strip_prefix=False)
    py = AppInstance(app=_App("b.py"), port=2, upstream="http://127.0.0.1:2", strip_prefix=True)
    assert sl.url_for("_stcore/health") == "http://127.0.0.1:1/a.sl/_stcore/health"
    assert py.url_for("x/y", "q=1") == "http://127.0.0.1:2/x/y?q=1"


def test_resource_names_are_dns_labels():
    from streamhub.runtimes import resource_name

    assert resource_name("streamlit-demo.sl", "") == "streamhub-hub-streamlit-demo-sl"
    long = resource_name("A" * 100 + ".sl", "hub-1")
    assert len(long) <= 63 and long == long.lower() and not long.endswith("-")
    assert long != resource_name("A" * 99 + "B.sl", "hub-1")


def _runtime_catalog(tmp_path, **extra):
    app = {"app_id": "d.sl", "file": "app.py", "runtime": "docker", "image": "reg/app:1",
           "env": {"SECRET": "s3"}, "runtime_args": ["--memory=1g"], **extra}
    write(tmp_path / "streamhub-apps.json", [{"boards": []}, app])
    return Catalog(load_settings(tmp_path))


def test_docker_runtime_argv(tmp_path, monkeypatch):
    from streamhub.runtimes import DockerRuntime

    calls = []

    async def fake_run(argv, input=None, timeout=60):
        calls.append(argv)
        return 0, ""

    monkeypatch.setattr(platform_utils, "docker_exe", lambda: "docker")
    monkeypatch.setattr(platform_utils, "run_command", fake_run)
    catalog = _runtime_catalog(tmp_path)
    manager = AppManager(catalog.settings, catalog, None, "http://127.0.0.1:8500", "token")
    launch = asyncio.run(DockerRuntime(manager).prepare(catalog.find("d.sl"), 9100))
    argv = launch.argv
    assert calls == [["docker", "rm", "-f", "streamhub-hub-d-sl"]]
    assert argv[:5] == ["docker", "run", "--rm", "--name", "streamhub-hub-d-sl"]
    assert "127.0.0.1:9100:8501" in argv and "--memory=1g" in argv
    assert argv[argv.index("reg/app:1") + 1:][:3] == ["streamlit", "run", "app.py"]
    assert "--server.address=0.0.0.0" in argv and "--server.baseUrlPath=d.sl" in argv
    assert "SECRET" in argv and not any("s3" in a for a in argv)  # values travel in the environment
    assert launch.env["SECRET"] == "s3" and launch.env["STREAMHUB_HOST"] == "0.0.0.0"
    assert launch.env["STREAMHUB_PORT"] == "8501" and launch.upstream == "http://127.0.0.1:9100"


def test_docker_runtime_socket_and_network(tmp_path, monkeypatch):
    from streamhub.runtimes import DockerRuntime

    calls = []

    async def fake_run(argv, input=None, timeout=60):
        calls.append(argv)
        return 0, ""

    monkeypatch.setattr(platform_utils, "docker_exe", lambda: "docker")
    monkeypatch.setattr(platform_utils, "run_command", fake_run)
    write(tmp_path / "streamhub.json", {"docker-socket": "/var/run/docker.sock", "docker-network": "apps-net"})
    catalog = _runtime_catalog(tmp_path)
    manager = AppManager(catalog.settings, catalog, None, "http://127.0.0.1:8500", "token")
    runtime = DockerRuntime(manager)
    assert not runtime.uses_local_port  # no host port: the hub reaches the container on the network
    launch = asyncio.run(runtime.prepare(catalog.find("d.sl"), 0))
    assert calls == [["docker", "-H", "unix:///var/run/docker.sock", "rm", "-f", "streamhub-hub-d-sl"]]
    assert launch.argv[:4] == ["docker", "-H", "unix:///var/run/docker.sock", "run"]
    assert launch.argv[launch.argv.index("--network") + 1] == "apps-net" and "-p" not in launch.argv
    assert launch.upstream == "http://streamhub-hub-d-sl:8501"
    catalog.settings.docker_network, catalog.settings.docker_socket = "", "tcp://10.0.0.5:2376"
    assert runtime.uses_local_port and runtime.cli() == ["docker", "-H", "tcp://10.0.0.5:2376"]


def test_docker_settings_are_checked(tmp_path, monkeypatch):
    write(tmp_path / "streamhub.json", {"docker-network": "--privileged"})
    with pytest.raises(ConfigError, match="docker-network"):
        load_settings(tmp_path)
    write(tmp_path / "streamhub.json", {})
    monkeypatch.setenv("STREAMHUB_DOCKER_NETWORK", "-x")
    with pytest.raises(ConfigError, match="docker-network"):
        load_settings(tmp_path)
    monkeypatch.setenv("STREAMHUB_DOCKER_NETWORK", "streamhub-apps")
    assert load_settings(tmp_path).docker_network == "streamhub-apps"


def test_app_type_key_replaces_the_suffix(tmp_path):
    write(tmp_path / "streamhub-apps.json", [{"boards": []},
        {"app_id": "sales", "type": "streamlit", "file": "a.py"},
        {"app_id": "api", "type": "page"},                      # a hub page link may use a hub path
        {"app_id": "shop", "type": "docker", "image": "shop:1", "serves": "web", "volumes": ["/srv/x:/data:ro"]},
        {"app_id": "dash", "type": "kubernetes", "image": "dash:1", "serves": "streamlit", "file": "app.py"},
        {"app_id": "docs", "type": "url", "url": "https://example.com"},
        {"app_id": "old.sl", "file": "a.py", "runtime": "docker", "image": "img"}])  # before 2.2: suffix + runtime
    catalog = Catalog(load_settings(tmp_path))
    found = {a.app_id: (a.kind, a.runtime, a.app_type) for a in catalog.all_apps()}
    assert found == {"sales": ("sl", "process", "streamlit"), "api": ("internal", "process", "page"),
                     "shop": ("py", "docker", "docker"), "dash": ("sl", "kubernetes", "kubernetes"),
                     "docs": ("url", "process", "url"), "old.sl": ("sl", "docker", "docker")}
    assert catalog.find("shop").volumes == ["/srv/x:/data:ro"] and catalog.find("dash").port_in_container == 8501


@pytest.mark.parametrize("entry, error", [
    ({"app_id": "admin", "type": "python"}, "path of the hub"),
    ({"app_id": "x.brd", "type": "streamlit"}, "path of the hub"),
    ({"app_id": "x", "type": "flask"}, "type must be"),
    ({"app_id": "x", "type": "docker", "image": "i", "serves": "php"}, "serves must be"),
    ({"app_id": "x", "type": "docker"}, "needs an 'image'"),
    ({"app_id": "x", "type": "docker", "image": "i", "volumes": ["--privileged"]}, "volume"),
])
def test_app_type_errors(tmp_path, entry, error):
    write(tmp_path / "streamhub-apps.json", [{"boards": []}, entry])
    with pytest.raises(ValueError, match=error):
        Catalog(load_settings(tmp_path))._parse_apps(json.loads((tmp_path / "streamhub-apps.json").read_text()))


def test_docker_volumes_and_the_image_command(tmp_path, monkeypatch):
    from streamhub.runtimes import DockerRuntime

    async def fake_run(argv, input=None, timeout=60):
        return 0, ""

    monkeypatch.setattr(platform_utils, "docker_exe", lambda: "docker")
    monkeypatch.setattr(platform_utils, "run_command", fake_run)
    write(tmp_path / "streamhub-apps.json", [{"boards": []}, {"app_id": "shop", "type": "docker", "image": "shop:1",
                                                               "container_port": 80, "volumes": ["data:/var/lib/shop"]}])
    catalog = Catalog(load_settings(tmp_path))
    manager = AppManager(catalog.settings, catalog, None, "http://127.0.0.1:8500", "token")
    argv = asyncio.run(DockerRuntime(manager).prepare(catalog.find("shop"), 9100)).argv
    assert argv[argv.index("-v") + 1] == "data:/var/lib/shop" and "127.0.0.1:9100:80" in argv
    assert argv[-1] == "shop:1"  # no file or command: the image's own command runs


def test_kubernetes_runtime_manifest(tmp_path, monkeypatch):
    from streamhub.runtimes import KubernetesRuntime

    applied = []

    async def fake_run(argv, input=None, timeout=60):
        if "apply" in argv:
            applied.append((argv, json.loads(input)))
        return 0, ""

    monkeypatch.setattr(platform_utils, "kubectl_exe", lambda: "kubectl")
    monkeypatch.setattr(platform_utils, "run_command", fake_run)
    catalog = _runtime_catalog(tmp_path, runtime="kubernetes", kubernetes={
        "namespace": "apps", "resources": {"limits": {"memory": "1Gi"}}, "image_pull_secrets": ["regcred"]})
    manager = AppManager(catalog.settings, catalog, None, "http://hub:8500", "token")
    runtime = KubernetesRuntime(manager)
    launch = asyncio.run(runtime.prepare(catalog.find("d.sl"), 0))
    assert not runtime.uses_local_port
    assert launch.upstream == "http://streamhub-hub-d-sl.apps.svc:8501"
    assert launch.handle == ("apps", "streamhub-hub-d-sl")
    argv, manifest = applied[0]
    assert argv[:3] == ["kubectl", "-n", "apps"]
    pod, service = manifest["items"]
    container = pod["spec"]["containers"][0]
    assert pod["spec"]["restartPolicy"] == "Never" and pod["spec"]["imagePullSecrets"] == [{"name": "regcred"}]
    assert container["image"] == "reg/app:1" and container["args"][:3] == ["streamlit", "run", "app.py"]
    assert container["resources"] == {"limits": {"memory": "1Gi"}}
    assert {"name": "SECRET", "value": "s3"} in container["env"]
    assert service["spec"]["selector"] == {"streamhub/name": "streamhub-hub-d-sl"}
    assert launch.argv[1:4] == ["-m", "streamhub", "follow-pod"] and launch.argv[4:7] == ["kubectl", "apps", "streamhub-hub-d-sl"]


def test_health_checks_stop_an_app_after_repeated_failures(tmp_path):
    write(tmp_path / "streamhub-apps.json", [{"boards": []}, {"app_id": "a.sl", "file": "x.py"}])
    catalog = Catalog(load_settings(tmp_path))
    manager = AppManager(catalog.settings, catalog, None, "", "")
    inst = AppInstance(app=catalog.find("a.sl"), port=1, upstream="http://127.0.0.1:1", strip_prefix=False,
                       process=object(), state=RUNNING)
    manager.instances["a.sl"] = inst
    stopped, notes = [], []

    async def unhealthy(_inst, timeout=10):
        return False

    async def terminate(target):
        stopped.append(target)

    async def notify(message, event):
        notes.append(event)

    manager._health_ok, manager._terminate, manager.notify = unhealthy, terminate, notify
    for _ in range(catalog.settings.health_failures):
        asyncio.run(manager.check_health())
    assert stopped == [inst] and notes == ["health"] and not inst.healthy and not inst.stopping
    asyncio.run(manager.check_health())
    assert stopped == [inst]  # not stopped twice


# -- sessions and single sign-on --
def test_map_groups():
    mapping = [{"group": "Data", "role": "user", "boards": ["a.brd"]},
               {"group": "cn=ops,dc=x", "role": "manager", "boards": ["b.brd", "a.brd"]}]
    assert auth.map_groups(["data", "CN=Ops,DC=x"], mapping, None) == ("manager", ["a.brd", "b.brd"])
    assert auth.map_groups(["other"], mapping, None) is None
    assert auth.map_groups(["other"], mapping, "guest") == ("guest", [])
    assert auth.map_groups([], [{"group": "*", "role": "user"}], None) == ("user", [])


def test_sessions_local_legacy_and_sso(tmp_path):
    write(tmp_path / "streamhub-users.json", {
        "alice": {"password": "x", "role": "admin", "boards": ["*"]},
        "carol": {"source": "oidc", "role": "manager", "boards": ["b.brd"]},
    })
    catalog = Catalog(load_settings(tmp_path))
    alice = catalog.user("alice")
    assert auth.user_from_session(auth.session_value(alice), catalog) == alice
    assert auth.user_from_session("alice", catalog) == alice  # 2.0 cookie: a bare user name
    sso = User("bob", "", "user", ["a.brd"], source="oidc")
    restored = auth.user_from_session(auth.session_value(sso), catalog)
    assert (restored.name, restored.role, restored.boards, restored.source) == ("bob", "user", ["a.brd"], "oidc")
    # the users file decides for an SSO account it lists with the same source
    carol = auth.user_from_session(auth.session_value(User("carol", "", "guest", [], source="oidc")), catalog)
    assert carol.role == "manager"
    # an SSO login named like a local user never becomes that local user
    impostor = auth.user_from_session(auth.session_value(User("alice", "", "user", [], source="oidc")), catalog)
    assert impostor.role == "user" and impostor.source == "oidc"
    # a local cookie for an SSO-only entry, or for a removed user, is refused
    assert auth.user_from_session(auth.session_value(User("carol", "", "admin", [])), catalog) is None
    assert auth.user_from_session(auth.session_value(User("ghost", "", "admin", [])), catalog) is None


def test_id_token_checks():
    from streamhub.handlers.sso import check_id_token

    claims = {"iss": "https://idp", "aud": ["app"], "exp": 2000, "nonce": "n"}
    check_id_token(claims, "https://idp", "app", "n", now=1000)
    for issuer, client, nonce, now in [("https://other", "app", "n", 1000), ("https://idp", "x", "n", 1000),
                                       ("https://idp", "app", "m", 1000), ("https://idp", "app", "n", 3000)]:
        with pytest.raises(ValueError):
            check_id_token(claims, issuer, client, nonce, now=now)
    for extra in ({"aud": ["app", "other"]}, {"azp": "other"}):  # several audiences need azp = client
        with pytest.raises(ValueError):
            check_id_token({**claims, **extra}, "https://idp", "app", "n", now=1000)
    check_id_token({**claims, "aud": ["app", "other"], "azp": "app"}, "https://idp", "app", "n", now=1000)


def test_oidc_and_ldap_require_tls(tmp_path):
    def settings(**config):
        (tmp_path / "streamhub.json").write_text(json.dumps(config), encoding="utf-8")
        return load_settings(tmp_path)

    with pytest.raises(ConfigError, match="https"):
        settings(oidc={"issuer": "http://idp", "client-id": "c"})
    assert settings(oidc={"issuer": "http://idp", "client-id": "c", "insecure-http": True}).oidc
    with pytest.raises(ConfigError, match="algorithms"):
        settings(oidc={"issuer": "https://idp", "client-id": "c", "algorithms": ["HS256"]})
    with pytest.raises(ConfigError, match="ldaps"):
        settings(ldap={"url": "ldap://directory"})
    for ldap in ({"url": "ldaps://directory"}, {"url": "ldap://directory", "starttls": True},
                 {"url": "ldap://directory", "allow-plaintext": True}):
        assert settings(ldap=ldap).ldap


def test_oidc_provider_refuses_http_endpoints():
    from streamhub.handlers.sso import OidcProvider

    provider = OidcProvider(type("S", (), {"oidc": {"issuer": "https://idp", "client-id": "c"}})(), None)
    assert provider.check_url("https://idp/token", "token_endpoint")
    for url in ("http://idp/token", "", None):
        with pytest.raises(ValueError):
            provider.check_url(url, "token_endpoint")


def test_hub_cookies_are_not_forwarded():
    assert strip_hub_cookies("oidc=1; streamhub_instance=h1; app=2") == "app=2"


# -- notifiers --
def test_notifier_payloads_and_event_filter(tmp_path):
    from streamhub.notify import Notifier, email_message, plain, teams_payload

    assert plain(":red_circle: Streamhub stopped") == "Streamhub stopped"
    card = teams_payload(":memo: Issue", "Title")["attachments"][0]["content"]
    assert card["type"] == "AdaptiveCard" and card["body"][1]["text"] == "Issue"
    message = email_message("hub@x", ["a@x", "b@x"], "Subj", ":memo: body", reply_to="u@x")
    assert message["To"] == "a@x, b@x" and message["Reply-To"] == "u@x"
    assert message.get_content().strip() == "body"

    write(tmp_path / "streamhub.json", {"slack-hook": "https://slack/x", "notifiers": [
        {"type": "teams", "url": "https://teams/x", "events": ["report"]}]})
    notifier = Notifier(load_settings(tmp_path), enabled=True)
    assert [c["type"] for c in notifier.channels] == ["slack", "teams"]
    assert Notifier.wants(notifier.channels[0], "clean") and not Notifier.wants(notifier.channels[1], "clean")
    posted = []

    async def fake_post(url, payload):
        posted.append(url)
        return url != "https://teams/x"

    notifier._post = fake_post
    assert asyncio.run(notifier.send("hi", event="clean")).status == "sent"
    delivery = asyncio.run(notifier.send("hi", event="report", to=["dev@x"]))  # no smtp: developers skipped
    assert (delivery.sent, delivery.failed, delivery.status) == (["slack"], ["teams"], "partial")
    assert posted == ["https://slack/x", "https://slack/x", "https://teams/x"] and notifier.failures == {"teams": 1}
    assert Notifier(load_settings(tmp_path), enabled=False).channels == []
    assert asyncio.run(Notifier(load_settings(tmp_path), enabled=False).send("hi")).status == "disabled"
