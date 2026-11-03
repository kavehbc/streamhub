"""Runs a real hub process against the example apps (skipped when their frameworks are missing)."""
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

requests = pytest.importorskip("requests")
pytest.importorskip("flask")
pytest.importorskip("fastapi")
pytest.importorskip("streamlit")
psutil = pytest.importorskip("psutil")

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "integration-test"
SICK_APP = """
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

class Handler(BaseHTTPRequestHandler):
    checks = 0

    def do_GET(self):
        Handler.checks += 1
        self.send_response(200 if Handler.checks <= 2 else 500)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass

HTTPServer(("127.0.0.1", int(os.environ["STREAMHUB_PORT"])), Handler).serve_forever()
"""
# What a Streamlit app sees behind the hub: st.user, a verified identity, and no hub secret.
WHOAMI_APP = """
import json, os
from pathlib import Path
import streamlit as st
from streamhub.auth import verify_identity

token = st.context.headers.get("X-Streamhub-Identity")
claims = verify_identity(token, os.environ["STREAMHUB_APP_KEY"], os.environ["STREAMHUB_APP_ID"]) if token else None
Path(__file__).with_name("seen.json").write_text(json.dumps({
    "user": st.user.to_dict(), "claims": claims, "hub_secret": "STREAMHUB_ADMIN_PASSWORD" in os.environ}))
st.write("ok")
"""


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def hub(tmp_path_factory):
    work = tmp_path_factory.mktemp("hub")
    shutil.copytree(ROOT / "streamhub" / "demo", work / "examples")
    config = work / "examples" / "config"
    port = free_port()
    data = json.loads((config / "streamhub.json").read_text(encoding="utf-8"))
    data.update({"port": port, "port-range": [port + 1, port + 50], "idle-timeout": 0,
                 "health-interval": 1, "health-failures": 2})
    (config / "streamhub.json").write_text(json.dumps(data), encoding="utf-8")
    # An app whose health endpoint answers twice, then fails: the health checks must restart it.
    (work / "examples" / "sick").mkdir()
    (work / "examples" / "sick" / "main.py").write_text(SICK_APP, encoding="utf-8")
    (work / "examples" / "whoami").mkdir()
    (work / "examples" / "whoami" / "main.py").write_text(WHOAMI_APP, encoding="utf-8")
    apps = json.loads((config / "streamhub-apps.json").read_text(encoding="utf-8"))
    apps[0]["boards"].append({"name": "private.brd", "label": "Private", "auth": True})
    apps.append({"board": ["demo.brd"], "app_id": "sick.py", "file": "main.py", "folder": "../sick",
                 "health_path": "health", "restart": "on-failure"})
    apps.append({"board": ["private.brd"], "app_id": "whoami.sl", "file": "main.py", "folder": "../whoami",
                 "streamlit_user_headers": True})
    (config / "streamhub-apps.json").write_text(json.dumps(apps), encoding="utf-8")

    env = dict(os.environ, STREAMHUB_ADMIN_PASSWORD=PASSWORD, PYTHONPATH=str(ROOT))
    log = open(work / "hub.log", "wb")  # a file, never an unread pipe
    proc = subprocess.Popen([sys.executable, "-m", "streamhub", "run", str(config)], env=env, cwd=work,
                            stdout=log, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            requests.get(base + "/api/health", timeout=1)
            break
        except requests.ConnectionError:
            time.sleep(0.1)
    yield base, proc, config
    if proc.poll() is None:
        proc.kill()
    proc.wait(10)
    log.close()
    print((work / "hub.log").read_text(encoding="utf-8", errors="replace")[-4000:])


def session(base, login=True):
    s = requests.Session()
    s.get(base + "/login/")
    if login:
        r = s.post(base + "/login/", data={"username": "admin", "password": PASSWORD, "_xsrf": s.cookies["_xsrf"]})
        assert r.status_code == 200
    return s


def launch(s, base, app_id):
    s.get(f"{base}/{app_id}/")
    for _ in range(240):
        if s.get(f"{base}/api/apps/{app_id}/status").json()["ready"]:
            return
        time.sleep(0.25)
    raise AssertionError(f"{app_id} never became ready")


def test_public_pages_and_auth(hub):
    base, _, _ = hub
    anon = requests.Session()
    assert anon.get(base + "/").status_code == 200
    assert anon.get(base + "/demo.brd/").status_code == 200
    assert anon.get(base + "/private.brd/", allow_redirects=False).status_code == 302
    assert anon.get(base + "/api/", allow_redirects=False).status_code == 302
    assert anon.get(base + "/status.cmd/", allow_redirects=False).headers["Location"] == "/admin/"
    assert anon.get(base + "/admin/", allow_redirects=False).status_code == 302
    assert anon.get(base + "/nope.curl/").status_code == 404
    assert anon.get(base + "/streamhub-docs.url/", allow_redirects=False).headers["Location"].startswith("https://")


def test_login_rejects_bad_password_and_open_redirect(hub):
    base, _, _ = hub
    s = session(base, login=False)
    assert s.post(base + "/login/", data={"username": "admin", "password": "x", "_xsrf": s.cookies["_xsrf"]}).status_code == 401
    r = s.post(base + "/login/", data={"username": "admin", "password": PASSWORD, "next": "//evil.com/",
                                       "_xsrf": s.cookies["_xsrf"]}, allow_redirects=False)
    assert r.headers["Location"] == "/"
    assert s.post(base + "/clear/").status_code == 403  # no XSRF token


def test_proxy_python_apps(hub):
    base, _, _ = hub
    s = session(base)
    launch(s, base, "flask-demo.py")
    launch(s, base, "fastapi-demo.py")
    assert "/flask-demo.py/check/" in s.get(base + "/flask-demo.py/").text
    assert s.get(base + "/flask-demo.py/go/", allow_redirects=False).headers["Location"] == "/flask-demo.py/check/"
    assert s.get(base + "/fastapi-demo.py/items/5?q=hi").json() == {"item_id": 5, "q": "hi"}
    assert s.put(base + "/fastapi-demo.py/items/5", json={"name": "n", "price": 1}).json()["item_name"] == "n"
    assert s.delete(base + "/fastapi-demo.py/items/9").json() == {"deleted": 9}
    assert "/fastapi-demo.py/openapi.json" in s.get(base + "/fastapi-demo.py/docs").text
    assert "Running on" in s.get(base + "/out/flask-demo.py/").text


def test_proxy_streamlit_websocket(hub):
    import asyncio

    from streamlit.proto.BackMsg_pb2 import BackMsg
    from streamlit.proto.ForwardMsg_pb2 import ForwardMsg
    from tornado.httpclient import HTTPRequest
    from tornado.websocket import websocket_connect

    base, _, _ = hub
    s = session(base)
    launch(s, base, "streamlit-demo.sl")
    assert s.get(base + "/streamlit-demo.sl/_stcore/health").text == "ok"

    async def run():
        ws = await websocket_connect(HTTPRequest(base.replace("http", "ws") + "/streamlit-demo.sl/_stcore/stream",
                                                 headers={"Origin": base}), subprotocols=["streamlit"])
        msg = BackMsg()
        msg.rerun_script.query_string = ""
        await ws.write_message(msg.SerializeToString(), binary=True)
        kinds = []
        while "script_finished" not in kinds:
            forward = ForwardMsg()
            forward.ParseFromString(await asyncio.wait_for(ws.read_message(), 30))
            kinds.append(forward.WhichOneof("type"))
        ws.close()
        return kinds

    assert "delta" in asyncio.run(run())


def test_streamlit_app_sees_the_hub_identity_and_no_hub_secret(hub):
    """st.user (COMPAT-5), X-Streamhub-Identity, and the filtered environment (SEC-15) in a real app."""
    import asyncio

    from streamlit.proto.BackMsg_pb2 import BackMsg
    from streamlit.proto.ForwardMsg_pb2 import ForwardMsg
    from tornado.httpclient import HTTPRequest
    from tornado.websocket import websocket_connect

    base, _, config = hub
    s = session(base)
    launch(s, base, "whoami.sl")
    cookie = "; ".join(f"{k}={v}" for k, v in s.cookies.items())

    async def run():
        ws = await websocket_connect(HTTPRequest(base.replace("http", "ws") + "/whoami.sl/_stcore/stream",
                                                 headers={"Origin": base, "Cookie": cookie}),
                                     subprotocols=["streamlit"])
        msg = BackMsg()
        msg.rerun_script.query_string = ""
        await ws.write_message(msg.SerializeToString(), binary=True)
        while True:
            forward = ForwardMsg()
            forward.ParseFromString(await asyncio.wait_for(ws.read_message(), 30))
            if forward.WhichOneof("type") == "script_finished":
                break
        ws.close()

    asyncio.run(run())
    seen = json.loads((config.parent / "whoami" / "seen.json").read_text(encoding="utf-8"))
    assert seen["user"]["name"] == "admin" and seen["user"]["role"] == "admin"
    assert seen["claims"]["sub"] == "admin" and seen["claims"]["aud"] == "whoami.sl"
    assert seen["hub_secret"] is False


def test_unhealthy_app_is_restarted(hub):
    base, _, _ = hub
    s = session(base)
    launch(s, base, "sick.py")
    first = next(e["pid"] for e in s.get(base + "/api/").json()["proxy_map"] if e["app_id"] == "sick.py")
    for _ in range(120):
        entry = next((e for e in s.get(base + "/api/").json()["proxy_map"] if e["app_id"] == "sick.py"), None)
        if entry and entry["pid"] != first and entry["state"] != "stopped":
            break
        time.sleep(0.25)
    else:
        raise AssertionError("sick.py was not restarted after failing its health checks")
    assert not psutil.pid_exists(first) or psutil.Process(first).status() == psutil.STATUS_ZOMBIE
    s.post(base + "/api/apps/sick.py/stop", headers={"X-XSRFToken": s.cookies["_xsrf"]})


def test_admin_page_and_app_list(hub):
    base, _, _ = hub
    s = session(base)
    assert s.get(base + "/admin/").status_code == 200
    state = s.get(base + "/api/admin/state").json()
    assert "streamlit-demo.sl" in [a["app_id"] for a in state["apps"]]
    listed = {a["app_id"]: a for a in requests.get(base + "/api/apps").json()["apps"]}
    assert "flask-demo.py" in listed and "admin" not in listed  # internal links are not apps


def test_api_and_clear_leave_no_orphans(hub):
    base, _, config = hub
    s = session(base)
    launch(s, base, "flask-demo.py")
    api = s.get(base + "/api/").json()
    assert api["config"].endswith("streamhub.json")
    entry = next(e for e in api["proxy_map"] if e["app_id"] == "flask-demo.py")
    tree = [entry["pid"]] + [c.pid for c in psutil.Process(entry["pid"]).children(recursive=True)]

    (config / "temp").mkdir(exist_ok=True)
    (config / "temp" / "junk.txt").write_text("x")
    assert s.post(base + "/clear/", data={"all_apps": "1", "_xsrf": s.cookies["_xsrf"]}).status_code == 200
    time.sleep(1)
    assert not [pid for pid in tree if psutil.pid_exists(pid)]
    assert not (config / "temp" / "junk.txt").exists()
    assert [e["app_id"] for e in s.get(base + "/api/").json()["proxy_map"]] == ["Streamhub"]

    launch(s, base, "flask-demo.py")  # the freed port is handed out again
    again = next(e for e in s.get(base + "/api/").json()["proxy_map"] if e["app_id"] == "flask-demo.py")
    assert again["port"] == entry["port"]


def test_exit_stops_everything(hub):
    base, proc, _ = hub
    s = session(base)
    launch(s, base, "flask-demo.py")
    pids = [e["pid"] for e in s.get(base + "/api/").json()["proxy_map"] if e["pid"]]
    assert s.post(base + "/exit/", data={"_xsrf": s.cookies["_xsrf"]}).status_code == 200
    assert proc.wait(30) == 0
    assert not [pid for pid in pids if psutil.pid_exists(pid)]
