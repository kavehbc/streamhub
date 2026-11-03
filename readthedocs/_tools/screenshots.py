"""Retake the screenshots of the documentation site (readthedocs/_static/screenshots/).

Builds a sample hub in a temporary folder (three boards, sample apps, users and news), starts it on port 8600
and an empty hub on 8610 (for the setup page), drives them with Playwright and saves one PNG per screen.
Local paths are replaced with neutral ones before each screenshot.

    pip install -e ".[tools,examples]" playwright     # in the repository root
    python -m playwright install chromium             # or pass --channel chrome / msedge to use an installed one
    python readthedocs/_tools/screenshots.py [--hub-python PATH] [--channel chrome] [name ...]

Names limit the run to those screenshots (the whole tour still runs). --hub-python is the interpreter that runs
the hubs and their apps (it needs streamhub's `tools` and `examples` extras); it defaults to this one.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "readthedocs" / "_static" / "screenshots"
HUB, EMPTY = "http://localhost:8600", "http://localhost:8610"
NEUTRAL = r"C:\streamhub" if os.name == "nt" else "/srv/streamhub"


def build_sample(root, hub_python):
    """The sample hub: the demo apps, plus Sales and Operations boards, users and news."""
    subprocess.run([hub_python, "-c", "import sys; from streamhub.bootstrap import prepare_demo; "
                    "prepare_demo(sys.argv[1])", str(root / "hub")], check=True, env=hub_env())
    config = root / "hub" / "config"
    (root / "hub" / "broken").mkdir(exist_ok=True)
    (root / "hub" / "broken" / "main.py").write_text("import pandas_profiling_v9  # not installed\n", encoding="utf-8")
    (root / "empty").mkdir()
    dev = [{"name": "Jane Doe", "email": "jane.doe@example.com"}, {"name": "Sam Lee", "email": "sam.lee@example.com"}]
    logo = "/static/brand/icon-192.png"
    apps = [
        {"boards": [{"name": "demo.brd", "label": "Demo", "auth": False},
                    {"name": "sales.brd", "label": "Sales", "auth": True},
                    {"name": "ops.brd", "label": "Operations", "auth": True}]},
        {"board": ["demo.brd"], "app_id": "streamlit-demo", "type": "streamlit", "app_name": "Streamlit demo",
         "description": "A minimal Streamlit app", "file": "main.py", "folder": "../streamlit",
         "auto_shutdown": True, "icon": "/cdf/icons/monitor.png", "developer": dev[:1]},
        {"board": ["demo.brd"], "app_id": "flask-demo", "type": "python", "app_name": "Flask demo",
         "description": "A Flask app behind the proxy (prefix-aware links and redirects)", "file": "main.py",
         "folder": "../flask", "auto_shutdown": True, "restart": "on-failure", "health_path": "health/",
         "icon": "/cdf/icons/server.png", "developer": dev[:1],
         "children": [{"board": ["demo.brd"], "app_id": "fastapi-demo", "type": "python",
                       "app_name": "FastAPI demo", "description": "Open /docs for the API documentation",
                       "file": "main.py", "folder": "../fastapi", "auto_shutdown": True,
                       "icon": "/cdf/icons/running.png"}]},
        {"board": ["demo.brd"], "app_id": "streamhub-docs", "type": "url", "app_name": "Streamhub on GitHub",
         "description": "Source code and documentation", "url": "https://github.com/kavehbc/streamhub", "icon": logo},
        {"board": ["demo.brd"], "app_id": "help.cmd", "app_name": "Help", "description": "Streamhub user guide",
         "icon": logo},
        {"board": ["sales.brd"], "app_id": "sales-forecast", "type": "streamlit", "app_name": "Sales forecast",
         "description": "Weekly forecast by region", "file": "main.py", "folder": "../streamlit",
         "auto_shutdown": True, "restart": "on-failure", "icon": "/cdf/icons/running.png", "developer": dev},
        {"board": ["sales.brd"], "app_id": "price-monitor", "type": "python", "app_name": "Price monitor",
         "description": "Competitor prices, refreshed hourly", "file": "main.py", "folder": "../flask",
         "health_path": "health/", "icon": "/cdf/icons/monitor.png", "developer": dev[1:]},
        {"board": ["ops.brd"], "app_id": "factory-kpis", "type": "streamlit", "app_name": "Factory KPIs",
         "description": "Throughput and downtime per line", "file": "main.py", "folder": "../streamlit",
         "icon": "/cdf/icons/server.png", "developer": dev[1:]},
        {"board": ["ops.brd"], "app_id": "etl-monitor", "type": "python", "app_name": "ETL monitor",
         "description": "Nightly pipeline status", "file": "main.py", "folder": "../broken",
         "icon": "/cdf/icons/server.png", "developer": dev[1:]},
        {"board": ["ops.brd"], "app_id": "legacy-reports", "type": "url", "app_name": "Legacy reports",
         "description": "Retired: use Factory KPIs", "url": "https://example.com/", "display": "disabled",
         "icon": "/cdf/icons/monitor.png"},
    ]
    news = [
        {"title": "Sales forecast v2", "date": "2026-11-02", "type": "info",
         "message": "The forecast now covers every region and refreshes each Monday."},
        {"title": "Maintenance on Saturday", "date": "2026-10-30", "type": "warning",
         "message": "The hub restarts at 06:00. Save your work before then."},
        {"title": "Welcome to the Analytics Hub", "date": "2026-10-15", "type": "normal",
         "message": "Open a board, pick an app and it starts on demand. Use the star to keep your favorites on top."},
        {"title": "New board: Operations", "date": "2026-10-01", "type": "normal",
         "message": "Factory KPIs and the ETL monitor moved to the Operations board."},
    ]
    hashes = subprocess.run([hub_python, "-c", "import sys; from streamhub.auth import hash_password; "
                             "print('\\n'.join(hash_password(p) for p in sys.argv[1:]))",
                             "admin-password", "alice-password", "bob-password"],
                            check=True, capture_output=True, text=True, env=hub_env()).stdout.split()
    users = {"admin": {"password": hashes[0], "role": "admin", "boards": ["*"]},
             "alice": {"password": hashes[1], "role": "manager", "boards": ["*"]},
             "bob": {"password": hashes[2], "role": "user", "boards": ["sales.brd"]}}
    settings = {"server-url": "http://localhost", "site-title": "Analytics Hub", "team-name": "Data Platform Team",
                "port": 8600, "port-range": [8601, 8700], "port-exception": [], "schedule": "02:00",
                "timezone": "America/Toronto", "idle-timeout": 60}
    for name, data in [("streamhub-apps.json", apps), ("streamhub-news.json", news),
                       ("streamhub-users.json", users), ("streamhub.json", settings)]:
        (config / name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return config


def hub_env():
    env = {k: v for k, v in os.environ.items() if not k.startswith("STREAMHUB_")}
    env["PYTHONPATH"] = str(REPO) + os.pathsep + env.get("PYTHONPATH", "")
    return env


def start_hub(hub_python, config, port, log):
    proc = subprocess.Popen([hub_python, "-m", "streamhub", "run", "--debug", "--port", str(port), str(config)],
                            stdout=log, stderr=subprocess.STDOUT, env=hub_env())
    for _ in range(60):
        try:
            urllib.request.urlopen(f"http://localhost:{port}/api/health", timeout=2)
            return proc
        except OSError:
            time.sleep(0.5)
    proc.terminate()
    raise RuntimeError(f"the hub on port {port} did not start (see {log.name})")


class Tour:
    def __init__(self, only, scrub):
        self.only, self.scrub = only, scrub

    def shot(self, page, name, full=False):
        if self.only and name not in self.only:
            return
        page.evaluate("""(pairs) => {
          const fix = (s) => { if (!s) return s; for (const [a, b] of pairs) { s = s.split(a).join(b); } return s; };
          const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
          for (let n = walk.nextNode(); n; n = walk.nextNode()) { const v = fix(n.nodeValue); if (v !== n.nodeValue) n.nodeValue = v; }
          document.querySelectorAll('input, textarea').forEach(e => { e.value = fix(e.value); if (e.placeholder) e.placeholder = fix(e.placeholder); });
          document.querySelectorAll('[title]').forEach(e => { e.title = fix(e.title); });
        }""", self.scrub)
        page.screenshot(path=OUT / f"{name}.png", full_page=full)
        print("saved", name)


def wait_ready(page, app_id, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        if page.context.request.get(f"{HUB}/api/apps/{app_id}/status").json().get("ready"):
            return
        time.sleep(0.5)
    raise RuntimeError(f"{app_id} did not become ready")


def login(page, user, password):
    page.goto(f"{HUB}/login/")
    page.fill("input[name=username]", user)
    page.fill("input[name=password]", password)
    page.click("button[type=submit]")
    page.wait_for_load_state("networkidle")


def admin_tab(page, tab, wait=1500):
    page.goto("about:blank")  # a new load, so dialogs of the previous tab are gone
    page.goto(f"{HUB}/admin/#{tab}")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(wait)


def tour(browser, t):
    ctx = browser.new_context(viewport={"width": 1400, "height": 880}, color_scheme="light")
    page = ctx.new_page()
    page.goto(f"{EMPTY}/")
    page.wait_for_load_state("networkidle")
    t.shot(page, "setup")

    page.goto(f"{HUB}/")
    page.wait_for_load_state("networkidle")
    t.shot(page, "home-anonymous")
    page.goto(f"{HUB}/login/")
    t.shot(page, "login")

    login(page, "admin", "admin-password")
    page.goto(f"{HUB}/sales-forecast/")
    page.wait_for_timeout(700)
    t.shot(page, "loading")
    for app_id in ("sales-forecast", "streamlit-demo", "flask-demo"):
        page.goto(f"{HUB}/{app_id}/")
        wait_ready(page, app_id)
    page.goto(f"{HUB}/streamlit-demo/")
    page.wait_for_timeout(5000)
    t.shot(page, "streamlit-app")
    page.goto(f"{HUB}/etl-monitor/")
    page.wait_for_timeout(8000)
    page.reload()
    page.wait_for_timeout(1500)
    t.shot(page, "app-error")

    page.goto(f"{HUB}/sales.brd/")
    page.wait_for_load_state("networkidle")
    page.click('button[data-fav="sales-forecast"]')
    page.goto(f"{HUB}/demo.brd/")
    page.wait_for_load_state("networkidle")
    page.click('button[data-fav="streamlit-demo"]')
    page.wait_for_timeout(2500)
    t.shot(page, "board")
    page.goto(f"{HUB}/ops.brd/")
    page.wait_for_timeout(2000)
    t.shot(page, "board-ops")
    page.goto(f"{HUB}/demo.brd/")
    page.wait_for_timeout(1500)
    page.click('button[data-filter="running"]')
    page.fill("#hub-search", "demo")
    page.wait_for_timeout(800)
    t.shot(page, "board-filter")

    page.goto(f"{HUB}/")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)
    t.shot(page, "home")
    page.click("#sh-user-btn")
    page.wait_for_timeout(400)
    t.shot(page, "account-menu")
    page.goto(f"{HUB}/news/")
    t.shot(page, "news")
    page.goto(f"{HUB}/report/?id=sales-forecast")
    t.shot(page, "report")
    page.goto(f"{HUB}/out/flask-demo/")
    t.shot(page, "app-output")
    page.goto(f"{HUB}/clear/")
    t.shot(page, "clear")
    page.goto(f"{HUB}/help.cmd/")
    wait_ready(page, "help.cmd")
    page.goto(f"{HUB}/help.cmd/")
    page.wait_for_timeout(6000)
    t.shot(page, "help")

    admin_tab(page, "dashboard", 3500)
    t.shot(page, "admin-dashboard")
    t.shot(page, "admin-dashboard-full", full=True)
    page.click('#apps button[title="Log"]')
    page.wait_for_timeout(1500)
    t.shot(page, "admin-log")
    admin_tab(page, "network", 2500)
    page.fill("#ports-search", "86")  # only the sample hub's apps
    page.wait_for_timeout(500)
    t.shot(page, "admin-network")
    admin_tab(page, "apps")
    t.shot(page, "admin-apps")
    page.locator('#catalog button[title="Edit"]').first.click()
    page.wait_for_timeout(1200)
    t.shot(page, "admin-app-editor")
    page.select_option("#f-type", "docker")
    page.wait_for_timeout(800)
    t.shot(page, "admin-app-editor-docker")
    admin_tab(page, "users")
    t.shot(page, "admin-users")
    page.locator('#users button[title="Edit"]').nth(2).click()
    page.wait_for_timeout(800)
    t.shot(page, "admin-user-editor")
    admin_tab(page, "news")
    t.shot(page, "admin-news")
    admin_tab(page, "settings", 2500)
    t.shot(page, "admin-settings")
    t.shot(page, "admin-settings-full", full=True)
    admin_tab(page, "docker", 4000)
    page.click('button[data-containers="apps"]')  # only Streamhub's containers and images, not the machine's
    page.fill("#images-search", "streamhub")
    page.wait_for_timeout(700)
    t.shot(page, "admin-docker")
    admin_tab(page, "static", 2000)
    t.shot(page, "admin-static")
    page.locator("#cdf a, #cdf button", has_text="icons").first.click()
    page.wait_for_timeout(1500)
    t.shot(page, "admin-static-icons")
    admin_tab(page, "sessions", 2000)
    t.shot(page, "admin-sessions")
    admin_tab(page, "files")
    page.locator("#file-keys button").nth(1).click()
    page.wait_for_timeout(1200)
    t.shot(page, "admin-files")
    admin_tab(page, "backup")
    t.shot(page, "admin-backup")

    dark = browser.new_context(viewport={"width": 1400, "height": 880}, color_scheme="dark",
                               storage_state=ctx.storage_state())
    dpage = dark.new_page()
    dpage.goto(f"{HUB}/")
    dpage.wait_for_timeout(2000)
    t.shot(dpage, "home-dark")
    dpage.goto(f"{HUB}/admin/#dashboard")
    dpage.wait_for_timeout(3500)
    t.shot(dpage, "admin-dashboard-dark")

    phone = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True,
                                has_touch=True, storage_state=ctx.storage_state())
    ppage = phone.new_page()
    ppage.goto(f"{HUB}/demo.brd/")
    ppage.wait_for_timeout(2000)
    t.shot(ppage, "phone-board")
    ppage.click("#sh-nav-toggle")
    ppage.wait_for_timeout(500)
    t.shot(ppage, "phone-menu")
    ppage.goto(f"{HUB}/admin/#dashboard")
    ppage.wait_for_timeout(3000)
    t.shot(ppage, "phone-admin")

    upage = browser.new_context(viewport={"width": 1400, "height": 880}).new_page()
    upage.goto(f"{HUB}/login/")
    upage.fill("input[name=username]", "bob")
    upage.fill("input[name=password]", "bob-password")
    upage.click("button[type=submit]")
    upage.wait_for_load_state("networkidle")
    upage.wait_for_timeout(1500)
    t.shot(upage, "home-user")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--hub-python", default=sys.executable, help="Interpreter that runs the hubs and apps")
    parser.add_argument("--channel", default=None, help="Installed browser to use: chrome, msedge…")
    parser.add_argument("names", nargs="*", help="Only these screenshots")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="streamhub-shots-"))
    hubs = []
    try:
        config = build_sample(root, args.hub_python)
        log = open(root / "hubs.log", "w", encoding="utf-8")
        hubs = [start_hub(args.hub_python, config, 8600, log), start_hub(args.hub_python, root / "empty", 8610, log)]
        package = str(REPO / "streamhub")
        site = "C:\\Python312\\Lib\\site-packages\\streamhub" if os.name == "nt" else \
            "/usr/local/lib/python3.12/site-packages/streamhub"
        sep = "\\" if os.name == "nt" else "/"
        scrub = [(str(root / "hub"), NEUTRAL), (str(root / "empty"), NEUTRAL + "-new"),
                 (root.as_posix() + "/hub", NEUTRAL.replace("\\", "/")), (package, site),
                 (str(Path.home()), sep.join(["C:", "Users", "analyst"]) if os.name == "nt" else "/home/analyst")]
        with sync_playwright() as p:
            browser = p.chromium.launch(channel=args.channel)
            tour(browser, Tour(set(args.names), scrub))
            browser.close()
    finally:
        for proc in hubs:
            proc.terminate()  # Linux: a clean stop; Windows: the hub's job object takes its apps with it
            proc.wait(timeout=30)
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
