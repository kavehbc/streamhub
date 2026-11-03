"""In-process tests of the 2.1 pages and endpoints: /api/apps, /admin/, the report form, the instance
cookie, and LDAP and OpenID Connect logins (against a fake identity provider)."""
import base64
import hashlib
import json
import os
import tempfile
import time
from http.cookies import SimpleCookie
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlencode, urlsplit

import tornado.httpserver
import tornado.testing
import tornado.web

from streamhub import auth, platform_utils
from streamhub.app import Hub
from streamhub.config import load_settings
from streamhub.notify import Delivery

PASSWORD = "pw"
APPS = [
    {"boards": [{"name": "open.brd", "label": "Open", "auth": False},
                {"name": "closed.brd", "label": "Closed", "auth": True}]},
    {"board": ["open.brd"], "app_id": "a.sl", "app_name": "A", "file": "a.py",
     "developer": [{"name": "Dev", "email": "dev@example.com"}]},
    {"board": ["open.brd"], "app_id": "h.py", "file": "h.py", "display": "hidden"},
    {"board": ["closed.brd"], "app_id": "b.py", "app_name": "B", "file": "b.py",
     "children": [{"board": ["closed.brd"], "app_id": "c.url", "url": "https://example.com"}]},
]


def users():
    hashed = auth.hash_password(PASSWORD, iterations=1000)
    return {"admin": {"password": hashed, "role": "admin", "boards": ["*"]},
            "mgr": {"password": hashed, "role": "manager", "boards": []},
            "usr": {"password": hashed, "role": "user", "boards": ["closed.brd"]},
            "sso-only": {"source": "oidc", "role": "admin", "boards": ["*"]}}


class Browser:
    """Keeps cookies between requests and adds the XSRF token to POSTs."""

    def __init__(self, test):
        self.test = test
        self.cookies = {}

    def fetch(self, path, method="GET", form=None, json_body=None, xsrf=True, files=None):
        headers, body = {}, None
        if method == "POST":
            if "_xsrf" not in self.cookies:
                self.fetch("/login/")
            if files is not None:  # [(file name, bytes)] as multipart "files"
                boundary = "streamhub-test-boundary"
                body = b"".join(f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="{name}"\r\n'
                                f"Content-Type: application/octet-stream\r\n\r\n".encode() + data + b"\r\n"
                                for name, data in files) + f"--{boundary}--\r\n".encode()
                headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
                headers["X-XSRFToken"] = self.cookies["_xsrf"]
            elif form is not None:
                body = urlencode(dict(form, **({"_xsrf": self.cookies["_xsrf"]} if xsrf else {})))
                headers["Content-Type"] = "application/x-www-form-urlencoded"
            else:
                body = json.dumps(json_body or {})
                headers["Content-Type"] = "application/json"
                if xsrf:
                    headers["X-XSRFToken"] = self.cookies["_xsrf"]
        if self.cookies:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        response = self.test.fetch(path, method=method, body=body, headers=headers, follow_redirects=False,
                                   raise_error=False)
        for header in response.headers.get_list("Set-Cookie"):
            jar = SimpleCookie()
            jar.load(header)
            for name, morsel in jar.items():
                if morsel.value:
                    self.cookies[name] = morsel.value
                else:
                    self.cookies.pop(name, None)
        return response

    def login(self, name, password=PASSWORD):
        return self.fetch("/login/", "POST", form={"username": name, "password": password})

    def json(self, path):
        response = self.fetch(path)
        assert response.code == 200, (path, response.code)
        return json.loads(response.body)


class HubTestCase(tornado.testing.AsyncHTTPTestCase):
    config = {}

    def runTest(self):
        pass

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.iterations, auth.HASH_ITERATIONS = auth.HASH_ITERATIONS, 1000  # fast hashes for passwords set in tests
        super().setUp()

    def tearDown(self):
        self.io_loop.run_sync(self.hub.sessions.settle)  # the session file must be closed before cleanup
        super().tearDown()
        auth.HASH_ITERATIONS = self.iterations
        self.tmp.cleanup()

    def extra_config(self):
        return {}

    def initial_users(self):
        return users()

    def get_app(self):
        (self.dir / "streamhub-apps.json").write_text(json.dumps(APPS), encoding="utf-8")
        (self.dir / "streamhub-users.json").write_text(json.dumps(self.initial_users()), encoding="utf-8")
        if self.config is not None:  # None: no config file at all
            config = {"schedule": None, "health-interval": 0, **self.config, **self.extra_config()}
            (self.dir / "streamhub.json").write_text(json.dumps(config), encoding="utf-8")
        self.hub = Hub(load_settings(self.dir))
        self.sent = []

        self.delivery = Delivery(sent=["slack"])

        async def record(message, event="system", subject=None, to=(), reply_to=None):
            self.sent.append({"message": message, "event": event, "to": list(to), "reply_to": reply_to})
            return self.delivery

        self.hub.notifier.send = record
        return self.hub.application

    def browser(self, login=None):
        b = Browser(self)
        if login:
            assert b.login(login).code == 302
        return b


class TestPages(HubTestCase):
    def test_api_apps_lists_what_the_user_can_open(self):
        anon = self.browser()
        assert [a["app_id"] for a in anon.json("/api/apps")["apps"]] == ["a.sl"]
        apps = {a["app_id"]: a for a in self.browser("usr").json("/api/apps")["apps"]}
        assert sorted(apps) == ["a.sl", "b.py", "c.url"]
        assert apps["a.sl"]["state"] == "not running" and apps["c.url"]["state"] == "link"

    def test_board_page_has_search_badges_and_favorites(self):
        page = self.browser().fetch("/open.brd/").body.decode()
        assert 'id="hub-search"' in page and 'data-badge="a.sl"' in page and 'data-fav="a.sl"' in page
        assert 'id="hub-theme"' in page and "h.py" not in page

    def test_every_page_has_the_navigation(self):
        admin = self.browser("admin")
        for path in ("/", "/open.brd/", "/news/", "/admin/", "/login/", "/report/?id=a.sl", "/out/a.sl/"):
            page = admin.fetch(path).body.decode()
            assert 'id="sh-nav"' in page and 'href="/open.brd/"' in page, path
            assert 'id="sh-user-menu"' in page and 'href="/admin/#settings"' in page and 'href="/exit/"' in page, path
        page = self.browser().fetch("/").body.decode()
        assert 'id="sh-user-menu"' not in page and 'href="/login/"' in page
        assert 'title="Sign in to open this board"' in page  # closed.brd is locked

    def test_account_menu_follows_the_role(self):
        manager = self.browser("mgr").fetch("/").body.decode()
        assert 'href="/admin/#dashboard"' in manager and 'href="/admin/#network"' in manager
        assert 'href="/admin/#sessions"' not in manager and 'href="/exit/"' not in manager  # admins only
        assert 'href="/admin/#apps"' not in manager
        user = self.browser("usr").fetch("/").body.decode()
        assert 'href="/clear/"' in user and 'action="/logout/"' in user and "/admin/#" not in user

    def test_home_news_and_brand(self):
        (self.dir / "streamhub-news.json").write_text(json.dumps(
            [{"title": f"Item {i}", "type": "warning" if i == 0 else "info"} for i in range(5)]), encoding="utf-8")
        home = self.browser().fetch("/").body.decode()
        assert "Item 2" in home and "Item 3" not in home and 'href="/news/"' in home  # the latest three
        assert 'class="sh-wordmark"' in home and "<title>Streamhub</title>" in home
        news = self.browser().fetch("/news/").body.decode()
        assert all(f"Item {i}" in news for i in range(5)) and "sh-news-warning" in news

    def test_favicons(self):
        page = self.browser().fetch("/").body.decode()
        assert "brand/logo-mark.svg" in page and "brand/favicon-32.png" in page and "apple-touch-icon" in page
        icon = self.fetch("/favicon.ico")
        assert icon.code == 200 and icon.body[:4] == b"\x00\x00\x01\x00"  # an ICO file
        assert self.fetch("/static/brand/logo-mark.svg").code == 200

    def test_admin_page_access(self):
        response = self.browser().fetch("/admin/")
        assert response.code == 302 and response.headers["Location"].startswith("/login/")
        assert self.browser("usr").fetch("/admin/").code == 403
        assert self.browser("usr").fetch("/api/admin/state").code == 403
        manager = self.browser("mgr")
        assert manager.fetch("/admin/").code == 200
        state = manager.json("/api/admin/state")
        assert {a["app_id"]: a["state"] for a in state["apps"]}["a.sl"] == "not running"
        assert "cpu_percent" in state["server"]
        assert manager.fetch("/api/admin/files/news").code == 403  # admins only
        assert self.browser().fetch("/status.cmd/").headers["Location"] == "/admin/"

    def test_admin_json_editor_validates(self):
        admin = self.browser("admin")
        news = self.dir / "streamhub-news.json"
        assert admin.fetch("/api/admin/files/news", "POST", json_body={"text": "[1,"}, xsrf=False).code == 403
        bad = admin.fetch("/api/admin/files/news", "POST", json_body={"text": "[1,"})
        assert bad.code == 400 and not news.exists()
        good = admin.fetch("/api/admin/files/news", "POST", json_body={"text": '[{"title": "Hi"}]'})
        assert good.code == 200 and json.loads(good.body)["saved"]
        assert json.loads(news.read_text(encoding="utf-8")) == [{"title": "Hi"}]
        assert admin.json("/api/admin/files/news")["text"] == '[{"title": "Hi"}]'

    def test_admin_editors_load_for_admins_only(self):
        page = self.browser("admin").fetch("/admin/").body.decode()
        assert 'data-panel="settings"' in page and "/static/admin-editors.js" in page
        assert 'data-panel="docker"' in page and 'data-panel="static"' in page and 'data-panel="backup"' in page
        meta = json.loads(page.split('<script type="application/json" id="admin-meta">')[1].split("</script>")[0])
        assert "admin" in meta["reserved"] and "docker" in meta["types"]
        form = json.loads(page.split('<script type="application/json" id="settings-form">')[1].split("</script>")[0])
        fields = {f["key"]: f for section in form for f in section["fields"]}
        assert fields["port"]["restart"] and not fields["site-title"]["restart"]
        manager = self.browser("mgr").fetch("/admin/").body.decode()
        assert "/static/admin-editors.js" not in manager and 'data-panel="settings"' not in manager
        # Option lists and the forms of the JSON settings come from the hub, labelled.
        assert ["admin", auth.ROLE_HELP["admin"]] in meta["choices"]["roles"]
        assert [t[0] for t in meta["appTypes"]][:2] == ["streamlit", "python"] and meta["appTypes"][0][2]
        assert "Europe/Paris" in meta["timezones"] and ["main.html", "Top menu"] in meta["layouts"]
        assert {f["key"] for f in meta["subforms"]["notifiers"]} == {"type", "url", "to", "events"}
        assert fields["oidc"]["kind"] == "object:oidc" and fields["notifiers"]["kind"] == "list:notifiers"
        assert {section["title"]: section["help"] for section in form}["Server"]

    def test_path_check_and_environments(self):
        admin = self.browser("admin")
        found = admin.json("/api/admin/path-check?path=streamhub-apps.json")
        assert found["exists"] and not found["dir"] and found["path"] == str((self.dir / "streamhub-apps.json").resolve())
        (self.dir / "app").mkdir()
        (self.dir / "app" / "main.py").write_text("", encoding="utf-8")
        assert admin.json("/api/admin/path-check?path=main.py&base=app")["exists"]
        assert not admin.json("/api/admin/path-check?path=nope.py&base=app")["exists"]
        assert self.browser("mgr").fetch("/api/admin/path-check?path=x").code == 403  # admins only
        envs = admin.json("/api/admin/environments")
        assert isinstance(envs["environments"], list) and envs["hub"]

    def test_getting_started_checklist(self):
        steps = {s["id"]: s for s in self.browser("admin").json("/api/admin/state")["checklist"]}
        assert steps["settings"]["done"] and steps["apps"]["done"] and steps["users"]["done"]
        assert not steps["static"]["done"] and steps["static"]["tab"] == "settings"  # the bundled cdf folder
        assert self.browser("mgr").json("/api/admin/state")["checklist"] == []  # the steps are admin work

    def test_saved_config_applies_at_once(self):
        admin = self.browser("admin")
        current = admin.json("/api/admin/files/config")
        config = dict(json.loads(current["text"]), **{"site-title": "Renamed hub"})
        saved = json.loads(admin.fetch("/api/admin/files/config", "POST", json_body={
            "text": json.dumps(config), "version": current["version"]}).body)
        assert saved["saved"] and saved["restart"] == [] and "Applied." in saved["message"]
        assert self.hub.settings.site_title == "Renamed hub"
        assert "<title>Renamed hub</title>" in self.browser().fetch("/").body.decode()
        config["port"] = self.hub.settings.port + 1  # applies only after a restart
        saved = json.loads(admin.fetch("/api/admin/files/config", "POST", json_body={"text": json.dumps(config)}).body)
        assert saved["restart"] == ["port"] and "need a restart" in saved["message"]
        assert self.hub.settings.port != config["port"]

    def test_reload_keeps_command_line_ports(self):
        self.hub.overrides = {"port": self.hub.settings.port + 7}  # as `streamhub run --port`
        self.hub.settings.port = self.hub.overrides["port"]
        assert self.hub.reload_settings() == [] and self.hub.settings.port == self.hub.overrides["port"]

    def test_admin_users_editor_never_shows_or_stores_raw_passwords(self):
        admin = self.browser("admin")
        users_file = self.dir / "streamhub-users.json"
        shown = admin.json("/api/admin/files/users")
        assert "pbkdf2_sha256" not in shown["text"] and shown["note"]
        users = json.loads(shown["text"])
        assert users["usr"]["password"] == "********" and "password" not in users["sso-only"]
        stored_mgr = json.loads(users_file.read_text(encoding="utf-8"))["mgr"]["password"]

        users["usr"]["password"] = "new-usr-pw"                            # a new password, typed raw
        users["eve"] = {"password": "eve-pw", "role": "user", "boards": []}  # a new user
        saved = admin.fetch("/api/admin/files/users", "POST", json_body={"text": json.dumps(users)})
        assert saved.code == 200 and "usr, eve" in json.loads(saved.body)["message"]
        on_disk = users_file.read_text(encoding="utf-8")
        assert "new-usr-pw" not in on_disk and "eve-pw" not in on_disk and "********" not in on_disk
        stored = json.loads(on_disk)
        assert stored["mgr"]["password"] == stored_mgr                     # masked: unchanged
        assert all(auth.is_hashed(stored[name]["password"]) for name in ("admin", "mgr", "usr", "eve"))
        assert self.browser().login("usr", "new-usr-pw").code == 302
        assert self.browser().login("eve", "eve-pw").code == 302
        assert self.browser().login("usr", PASSWORD).code == 401

        users = json.loads(admin.json("/api/admin/files/users")["text"])
        users["zed"] = {"password": "********", "role": "user"}           # masked, but has no password yet
        refused = admin.fetch("/api/admin/files/users", "POST", json_body={"text": json.dumps(users)})
        assert refused.code == 400 and "zed" in json.loads(refused.body)["error"]

    def test_raw_password_in_users_file_cannot_log_in(self):
        users_file = self.dir / "streamhub-users.json"
        data = json.loads(users_file.read_text(encoding="utf-8"))
        data["raw"] = {"password": "raw-pw", "role": "admin", "boards": ["*"]}
        users_file.write_text(json.dumps(data), encoding="utf-8")
        assert self.browser().login("raw", "raw-pw").code == 401

    def test_restart_unknown_app_is_404(self):
        assert self.browser("mgr").fetch("/api/apps/nope.sl/restart", "POST", json_body={}).code == 404

    def test_report_form_sends_and_throttles(self):
        anon = self.browser()
        assert b"Send report" in anon.fetch("/report/?id=a.sl").body
        assert anon.fetch("/report/?id=nope.sl").code == 404
        assert anon.fetch("/report/?id=a.sl", "POST", form={"message": " "}).code == 400
        sent = anon.fetch("/report/?id=a.sl", "POST", form={"message": "It crashes", "contact": "me@x.org"})
        assert sent.code == 200 and b"was sent" in sent.body
        report = self.sent[-1]
        assert report["event"] == "report" and report["to"] == ["dev@example.com"] and report["reply_to"] == "me@x.org"
        assert "It crashes" in report["message"]
        self.delivery = Delivery(sent=["slack"], failed=["email"])
        assert b"not to every destination" in anon.fetch("/report/?id=a.sl", "POST", form={"message": "x"}).body
        self.delivery = Delivery(failed=["slack"])
        failed = anon.fetch("/report/?id=a.sl", "POST", form={"message": "kept"})
        assert failed.code == 502 and b"could not be delivered" in failed.body and b"kept" in failed.body
        self.delivery = Delivery()
        assert anon.fetch("/report/?id=a.sl", "POST", form={"message": "x"}).code == 503
        anon.fetch("/report/?id=a.sl", "POST", form={"message": "again"})
        assert anon.fetch("/report/?id=a.sl", "POST", form={"message": "again"}).code == 429

    def test_sso_only_entries_cannot_log_in_with_a_password(self):
        b = self.browser()
        assert b.login("sso-only", "").code == 401 and b.login("sso-only", "anything").code == 401
        assert b.login("usr").code == 302


class TestAdminTools(HubTestCase):
    """The admin page's Docker and Static files tabs."""
    config = {"cdf": "cdf"}

    def test_static_files_list_upload_rename_delete(self):
        admin, cdf = self.browser("admin"), self.dir / "cdf"
        assert self.browser("mgr").fetch("/api/admin/cdf").code == 403  # admins only
        listed = admin.json("/api/admin/cdf")
        assert listed["root"] == str(cdf.resolve()) and not listed["exists"] and not listed["bundled"]
        up = admin.fetch("/api/admin/cdf/upload?folder=img", "POST", files=[("logo.png", b"PNG1"), ("a.css", b"x")])
        assert up.code == 200 and (cdf / "img" / "logo.png").read_bytes() == b"PNG1"
        assert self.fetch("/cdf/img/logo.png").body == b"PNG1"  # served at once
        again = admin.fetch("/api/admin/cdf/upload?folder=img", "POST", files=[("logo.png", b"PNG2")])
        assert again.code == 409 and (cdf / "img" / "logo.png").read_bytes() == b"PNG1"
        assert admin.fetch("/api/admin/cdf/upload?folder=img&overwrite=1", "POST", files=[("logo.png", b"PNG2")]).code == 200
        entries = {e["path"]: e for e in admin.json("/api/admin/cdf")["entries"]}
        assert entries["img"]["dir"] and entries["img/logo.png"]["size"] == 4
        moved = admin.fetch("/api/admin/cdf/rename", "POST", json_body={"from": "img/a.css", "to": "css/site.css"})
        assert moved.code == 200 and (cdf / "css" / "site.css").is_file() and not (cdf / "img" / "a.css").exists()
        assert admin.fetch("/api/admin/cdf/rename", "POST", json_body={"from": "img/logo.png", "to": "css/site.css"}).code == 409
        assert admin.fetch("/api/admin/cdf/delete", "POST", json_body={"path": "img"}).code == 400  # not empty
        assert admin.fetch("/api/admin/cdf/delete", "POST", json_body={"path": "img/logo.png"}).code == 200
        assert admin.fetch("/api/admin/cdf/delete", "POST", json_body={"path": "img"}).code == 200
        assert admin.fetch("/api/admin/cdf/folder", "POST", json_body={"path": "new/sub"}).code == 200
        assert (cdf / "new" / "sub").is_dir()

    def test_static_files_stay_inside_the_cdf_folder(self):
        admin, outside = self.browser("admin"), self.dir / "streamhub-users.json"
        (self.dir / "cdf").mkdir()
        for body in ({"path": "../streamhub-users.json"}, {"path": "/../../x"}, {"path": "a\\..\\..\\x"},
                     {"path": "C:/Windows/x"}, {"path": ""}, {"path": "a/con:x"}):
            assert admin.fetch("/api/admin/cdf/delete", "POST", json_body=body).code in (400, 404), body
        assert admin.fetch("/api/admin/cdf/rename", "POST",
                           json_body={"from": "../streamhub-users.json", "to": "u.json"}).code == 400
        evil = admin.fetch("/api/admin/cdf/upload?folder=..", "POST", files=[("x.txt", b"x")])
        assert evil.code == 400 and not (self.dir / "x.txt").exists() and outside.is_file()
        named = admin.fetch("/api/admin/cdf/upload", "POST", files=[("../../evil.txt", b"x")])
        assert named.code == 200 and (self.dir / "cdf" / "evil.txt").is_file()  # only the base name is kept

    def fake_docker(self, outputs):
        """Replace the docker client: `outputs` maps a subcommand to (exit code, output); calls are recorded."""
        calls = []

        async def run(argv, input=None, timeout=60):
            calls.append(argv)
            return outputs.get(argv[1] if argv[1] != "-H" else argv[3], (0, ""))

        self.patches = [(platform_utils, "docker_exe", platform_utils.docker_exe),
                        (platform_utils, "run_command", platform_utils.run_command)]
        platform_utils.docker_exe = lambda: "docker"
        platform_utils.run_command = run
        self.addCleanup(lambda: [setattr(obj, name, value) for obj, name, value in self.patches])
        return calls

    def test_docker_state_and_actions(self):
        calls = self.fake_docker({
            "version": (0, '{"Version": "29.1", "Os": "linux", "Arch": "amd64", "ApiVersion": "1.52"}'),
            "ps": (0, '{"ID": "abcdef1234567890", "Names": "streamhub-hub-d-sl", "Image": "img:1", "State": "running",'
                      ' "Status": "Up 2 minutes", "Ports": "", "CreatedAt": "x",'
                      ' "Labels": "streamhub.app=d.sl,streamhub.instance=hub"}\nnot json'),
            "images": (0, '{"ID": "cf1b", "Repository": "img", "Tag": "1", "Size": "1GB", "CreatedSince": "now",'
                          ' "Containers": "1"}\n{"ID": "dead", "Repository": "<none>", "Tag": "<none>"}'),
            "network": (0, "bridge\nhost\n"),
            "pull": (1, "manifest unknown")})
        admin = self.browser("admin")
        assert self.browser("mgr").fetch("/api/admin/docker").code == 403  # admins only
        state = admin.json("/api/admin/docker")
        assert state["server"]["Version"] == "29.1" and state["host"] == ""
        assert state["containers"] == [{"id": "abcdef123456", "name": "streamhub-hub-d-sl", "image": "img:1",
                                        "state": "running", "status": "Up 2 minutes", "ports": "", "created": "x",
                                        "app": "d.sl", "instance": "hub", "hub": False}]
        assert [i["reference"] for i in state["images"]] == ["img:1", "dead"]
        stop = admin.fetch("/api/admin/docker/containers/streamhub-hub-d-sl/stop", "POST", json_body={})
        assert json.loads(stop.body)["ok"] and calls[-1] == ["docker", "stop", "streamhub-hub-d-sl"]
        assert admin.fetch("/api/admin/docker/containers/-rf/remove", "POST", json_body={}).code == 400
        assert admin.fetch("/api/admin/docker/images/pull", "POST", json_body={"image": "--help"}).code == 400
        pulled = json.loads(admin.fetch("/api/admin/docker/images/pull", "POST", json_body={"image": "img:2"}).body)
        assert not pulled["ok"] and "manifest unknown" in pulled["output"] and calls[-1] == ["docker", "pull", "img:2"]
        self.hub.settings.docker_socket = "/run/user/docker.sock"
        admin.json("/api/admin/docker")
        assert calls[-1][:3] == ["docker", "-H", "unix:///run/user/docker.sock"]

    def test_docker_tab_without_the_client(self):
        self.fake_docker({})
        platform_utils.docker_exe = lambda: None
        state = self.browser("admin").json("/api/admin/docker")
        assert state["server"] is None and "not installed" in state["error"]


class TestBackup(HubTestCase):
    """Backup and restore of the JSON files, and the temp folder purge."""

    def test_backup_holds_every_file_as_on_disk(self):
        admin = self.browser("admin")
        assert self.browser("mgr").fetch("/api/admin/backup").code == 403  # admins only
        response = admin.fetch("/api/admin/backup")
        assert "attachment" in response.headers["Content-Disposition"]
        backup = json.loads(response.body)
        assert backup["streamhub-backup"] == 1 and set(backup["files"]) == {"config", "apps", "users", "news"}
        assert backup["files"]["apps"]["text"] == (self.dir / "streamhub-apps.json").read_text(encoding="utf-8")
        assert backup["files"]["news"] == {"name": "streamhub-news.json", "text": None}  # no news file

    def test_restore_validates_everything_first_and_keeps_a_copy(self):
        admin = self.browser("admin")
        backup = json.loads(admin.fetch("/api/admin/backup").body)
        apps_before = (self.dir / "streamhub-apps.json").read_text(encoding="utf-8")
        changed = json.loads(backup["files"]["apps"]["text"])
        changed[1]["app_name"] = "Restored A"
        backup["files"]["apps"]["text"] = json.dumps(changed)
        backup["files"]["config"]["text"] = json.dumps({**json.loads(backup["files"]["config"]["text"]),
                                                        "site-title": "From backup", "port": 1})
        users = json.loads(backup["files"]["users"]["text"])
        users["eve"] = {"password": "eve-pw", "role": "user", "boards": []}  # a raw password: hashed on restore
        backup["files"]["users"]["text"] = json.dumps(users)
        bad = dict(backup, files={**backup["files"], "news": {"text": "[1,"}})
        refused = admin.fetch("/api/admin/restore", "POST", json_body={"backup": bad, "files": ["apps", "news"]})
        assert refused.code == 400 and "news" in json.loads(refused.body)["error"]
        assert (self.dir / "streamhub-apps.json").read_text(encoding="utf-8") == apps_before  # nothing written
        assert admin.fetch("/api/admin/restore", "POST", json_body={"backup": {"x": 1}, "files": ["apps"]}).code == 400
        done = json.loads(admin.fetch("/api/admin/restore", "POST",
                                      json_body={"backup": backup, "files": ["config", "apps", "users"]}).body)
        assert done["ok"] and done["restart"] == ["port"] and self.hub.settings.site_title == "From backup"
        assert "Restored A" in self.browser().fetch("/open.brd/").body.decode()
        stored = json.loads((self.dir / "streamhub-users.json").read_text(encoding="utf-8"))
        assert auth.is_hashed(stored["eve"]["password"])
        safety = json.loads(Path(done["safety"]).read_text(encoding="utf-8"))
        assert Path(done["safety"]).parent == (self.dir / "backups").resolve() \
            and safety["files"]["apps"]["text"] == apps_before

    def test_temp_purge(self):
        temp = self.hub.settings.temp_path
        temp.mkdir(parents=True, exist_ok=True)
        (temp / "old.csv").write_text("x", encoding="utf-8")
        (temp / "readme_will_not_be_deleted.txt").write_text("keep", encoding="utf-8")
        assert self.browser("usr").fetch("/api/admin/temp/purge", "POST", json_body={}).code == 403
        purged = json.loads(self.browser("mgr").fetch("/api/admin/temp/purge", "POST", json_body={}).body)
        assert purged["files"] == 1 and not (temp / "old.csv").exists()


class TestSetup(HubTestCase):
    """The first-run setup page: while no admin exists, the logged token creates one."""

    def initial_users(self):
        return {name: entry for name, entry in users().items() if name != "admin"}  # sso-only can't log in

    def setup_form(self, **values):
        return {"token": self.hub.setup_token, "username": "owner", "password": "owner-pw-1", "confirm": "owner-pw-1",
                "site_title": "Our hub", "team_name": "", **values}

    def test_setup_creates_the_first_admin(self):
        b = self.browser()
        assert "no admin account yet" in b.fetch("/login/").body.decode()
        start = b.fetch("/")
        assert start.code == 302 and start.headers["Location"] == "/setup/"  # a new hub starts with its setup
        assert b.fetch("/news/").code == 200  # only the start page is redirected
        # One page: without the token in the URL, the form starts with a field to type or paste it in.
        first = b.fetch("/setup/").body.decode()
        assert 'id="setup-token"' in first and 'name="password"' in first and "Setup token:" in first
        wrong = b.fetch("/setup/?token=wrong")
        assert wrong.code == 403 and "not this hub" in wrong.body.decode() and 'value="wrong"' in wrong.body.decode()
        linked = b.fetch("/setup/?token=" + self.hub.setup_token).body.decode()
        assert 'id="setup-token"' not in linked and f'type="hidden" name="token" value="{self.hub.setup_token}"' in linked
        assert b.fetch("/setup/?token=%C3%A9").code == 403  # not ASCII: refused, not a server error
        refused = b.fetch("/setup/", "POST", form=self.setup_form(token="wrong"))
        assert refused.code == 403 and 'value="owner"' in refused.body.decode()  # what was typed stays
        assert not (self.dir / "streamhub-users.json").read_text(encoding="utf-8").count("owner")
        page = b.fetch("/setup/?token=" + self.hub.setup_token)
        assert page.code == 200 and 'name="password"' in page.body.decode()
        short = b.fetch("/setup/", "POST", form=self.setup_form(password="short", confirm="short"))
        assert short.code == 400 and "8 characters" in short.body.decode()
        assert b.fetch("/setup/", "POST", form=self.setup_form(confirm="other-pw-1")).code == 400
        # The token as typed into the field: the whole link pasted works too.
        done = b.fetch("/setup/", "POST", form=self.setup_form(token=f"http://localhost:8500/setup/?token={self.hub.setup_token}"))
        assert done.code == 302 and done.headers["Location"] == "/admin/"
        assert b.fetch("/admin/").code == 200  # signed in as the new admin
        stored = json.loads((self.dir / "streamhub-users.json").read_text(encoding="utf-8"))
        assert stored["owner"]["role"] == "admin" and auth.verify_password(stored["owner"]["password"], "owner-pw-1")
        assert "usr" in stored  # the other users stay
        assert json.loads((self.dir / "streamhub.json").read_text(encoding="utf-8"))["site-title"] == "Our hub"
        assert self.hub.settings.site_title == "Our hub"
        assert b.fetch("/setup/?token=" + self.hub.setup_token).code == 404  # done: the page is gone
        assert self.browser().fetch("/").code == 200
        assert "no admin account yet" not in self.browser().fetch("/login/").body.decode()

    def test_no_setup_with_an_environment_admin(self):
        with mock.patch.dict(os.environ, {"STREAMHUB_ADMIN_PASSWORD": "env-admin-pw"}):
            assert self.browser().fetch("/setup/?token=" + self.hub.setup_token).code == 404

    def test_no_setup_over_an_invalid_users_file(self):
        (self.dir / "streamhub-users.json").write_text("{broken", encoding="utf-8")
        assert self.browser().fetch("/setup/?token=" + self.hub.setup_token).code == 404


class TestSetupNotNeeded(HubTestCase):
    def test_setup_is_gone_once_an_admin_exists(self):
        assert self.browser().fetch("/setup/?token=" + self.hub.setup_token).code == 404


class TestWithoutConfigFile(HubTestCase):
    """A config folder without streamhub.json runs on the defaults; the first admin-page save creates the file."""
    config = None

    def test_settings_save_creates_the_config_file(self):
        assert self.hub.settings.config_file is None
        admin = self.browser("admin")
        current = admin.json("/api/admin/files/config")
        assert current["exists"] is False and current["text"] == ""
        saved = json.loads(admin.fetch("/api/admin/files/config", "POST", json_body={
            "text": json.dumps({"site-title": "Fresh hub"}), "version": current["version"]}).body)
        assert saved["saved"] and self.hub.settings.site_title == "Fresh hub"
        assert self.hub.settings.config_file == (self.dir / "streamhub.json").resolve()


class TestInstance(HubTestCase):
    config = {"instance-id": "hub-b"}

    def test_instance_cookie_and_health(self):
        b = self.browser()
        b.fetch("/")
        assert b.cookies.get("streamhub_instance") == "hub-b"
        assert "streamhub_instance" not in b.fetch("/").headers.get("Set-Cookie", "")
        assert b.json("/api/health")["instance"] == "hub-b"
        assert self.hub.settings.log_path == (self.dir / "logs" / "hub-b").resolve()


class TestLdap(HubTestCase):
    config = {"ldap": {"url": "ldaps://directory", "user-dn": "uid={username},dc=x"},
              "group-mapping": [{"group": "ops", "role": "manager", "boards": ["closed.brd"]}]}

    def setUp(self):
        super().setUp()
        self.original = auth.ldap_authenticate
        auth.ldap_authenticate = lambda config, bind_password, username, password: (
            (username, ["CN=x", "Ops"]) if password == "right" else None)

    def tearDown(self):
        auth.ldap_authenticate = self.original
        super().tearDown()

    def test_ldap_login_maps_groups(self):
        b = self.browser()
        assert b.login("lisa", "wrong").code == 401
        assert b.login("lisa", "right").code == 302
        assert b.fetch("/admin/").code == 200  # manager through the "ops" group
        assert "b.py" in [a["app_id"] for a in b.json("/api/apps")["apps"]]
        assert self.browser("usr").fetch("/").code == 200  # local users still log in first


def rsa_jwk(kid):
    """(private key, public JWK) of a fresh RSA signing key."""
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    return key, {**public, "kid": kid, "use": "sig", "alg": "RS256"}


class FakeIdP:
    """Discovery, JWKS, token and userinfo endpoints of an OpenID provider, on its own port.

    ID tokens are RS256-signed with `self.key`; `self.forge_with` signs them with a key the JWKS lacks.
    """

    def __init__(self):
        self.challenge = self.nonce = None
        self.groups = ["Data-Team"]
        sock, self.port = tornado.testing.bind_unused_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.issuer = self.base
        self.rotate("k1")
        self.forge_with = None
        self.jwks_fetches = 0
        idp = self

        class Discovery(tornado.web.RequestHandler):
            def get(self):
                self.write({"issuer": idp.issuer, "authorization_endpoint": idp.base + "/authorize",
                            "token_endpoint": idp.base + "/token", "userinfo_endpoint": idp.base + "/userinfo",
                            "jwks_uri": idp.base + "/jwks"})

        class Jwks(tornado.web.RequestHandler):
            def get(self):
                idp.jwks_fetches += 1
                self.write({"keys": [idp.jwk]})

        class Token(tornado.web.RequestHandler):
            def post(self):
                import jwt

                expected = "Basic " + base64.b64encode(b"hub:client-secret").decode()
                verifier = self.get_argument("code_verifier")
                digest = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
                if (self.request.headers.get("Authorization") != expected or self.get_argument("code") != "good"
                        or digest != idp.challenge):
                    self.set_status(400)
                    self.write({"error": "invalid_grant"})
                    return
                now = int(time.time())
                claims = {"iss": idp.base, "aud": "hub", "iat": now, "exp": now + 300, "nonce": idp.nonce,
                          "sub": "s1", "preferred_username": "olga"}
                key, kid = idp.forge_with or (idp.key, idp.jwk["kid"])
                token = jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid})
                self.write({"access_token": "at", "token_type": "Bearer", "id_token": token})

        class UserInfo(tornado.web.RequestHandler):
            def get(self):
                if self.request.headers.get("Authorization") != "Bearer at":
                    raise tornado.web.HTTPError(401)
                self.write({"sub": "s1", "groups": idp.groups})

        app = tornado.web.Application([(r"/.well-known/openid-configuration", Discovery), (r"/jwks", Jwks),
                                       (r"/token", Token), (r"/userinfo", UserInfo)])
        self.server = tornado.httpserver.HTTPServer(app)
        self.server.add_sockets([sock])

    def rotate(self, kid):
        self.key, self.jwk = rsa_jwk(kid)


class TestOidc(HubTestCase):
    def extra_config(self):
        self.idp = FakeIdP()
        return {"oidc": {"issuer": self.idp.base, "client-id": "hub", "label": "Sign in with Test IdP",
                         "insecure-http": True},
                "group-mapping": [{"group": "data-team", "role": "manager", "boards": ["closed.brd"]}]}

    def get_app(self):
        app = super().get_app()
        self.hub.settings.oidc_client_secret = "client-secret"
        return app

    def tearDown(self):
        self.idp.server.stop()
        super().tearDown()

    def start(self, b):
        response = b.fetch("/login/oidc/?next=/closed.brd/")
        assert response.code == 302
        target = urlsplit(response.headers["Location"])
        assert target.netloc == f"127.0.0.1:{self.idp.port}" and target.path == "/authorize"
        query = {k: v[0] for k, v in parse_qs(target.query).items()}
        assert query["code_challenge_method"] == "S256" and query["redirect_uri"].endswith("/login/oidc/callback")
        self.idp.challenge, self.idp.nonce = query["code_challenge"], query["nonce"]
        return query["state"]

    def test_login_button(self):
        assert b"Sign in with Test IdP" in self.browser().fetch("/login/").body

    def test_full_login(self):
        b = self.browser()
        state = self.start(b)
        response = b.fetch(f"/login/oidc/callback?code=good&state={state}")
        assert response.code == 302 and response.headers["Location"] == "/closed.brd/"
        assert "oidc" not in b.cookies
        assert b.fetch("/admin/").code == 200  # manager through the data-team group
        assert "b.py" in [a["app_id"] for a in b.json("/api/apps")["apps"]]

    def test_state_mismatch_is_refused(self):
        b = self.browser()
        self.start(b)
        assert b.fetch("/login/oidc/callback?code=good&state=forged").code == 401
        assert b.fetch("/admin/").code == 302  # still anonymous

    def test_unmapped_groups_are_refused(self):
        self.idp.groups = ["Nobody"]
        b = self.browser()
        state = self.start(b)
        assert b.fetch(f"/login/oidc/callback?code=good&state={state}").code == 403

    def test_forged_signature_is_refused(self):
        self.idp.forge_with = (rsa_jwk("k1")[0], "k1")  # right key ID, wrong key
        b = self.browser()
        state = self.start(b)
        assert b.fetch(f"/login/oidc/callback?code=good&state={state}").code == 401
        assert b.fetch("/admin/").code == 302

    def test_key_rotation_refetches_the_jwks(self):
        b = self.browser()
        state = self.start(b)
        assert b.fetch(f"/login/oidc/callback?code=good&state={state}").code == 302
        self.idp.rotate("k2")
        self.hub.oidc._keys_fetched -= 3600  # past the refetch interval
        b = self.browser()
        state = self.start(b)
        assert b.fetch(f"/login/oidc/callback?code=good&state={state}").code == 302
        assert self.idp.jwks_fetches == 2

    def test_discovery_must_name_the_configured_issuer(self):
        self.idp.issuer = "https://evil.example.com"
        b = self.browser()
        response = b.fetch("/login/oidc/?next=/")
        assert response.code == 502 and "Location" not in response.headers and b"unavailable" in response.body
