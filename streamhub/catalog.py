"""Apps, boards, users and news, read from JSON files and re-read only when a file changes."""
import json
import logging
import os
from dataclasses import dataclass, field, replace
from pathlib import Path

from streamhub.auth import ROLES, env_password
from streamhub.config import PACKAGE_DIR

log = logging.getLogger(__name__)

KINDS = {".sl": "sl", ".py": "py", ".url": "url", ".curl": "curl", ".cmd": "cmd"}
# The `type` key; without it, the app_id suffix decides (KINDS). docker and kubernetes run an image that
# `serves` a Streamlit app or another web server.
TYPES = {"streamlit": "sl", "python": "py", "url": "url", "curl": "curl", "page": "internal",
         "docker": None, "kubernetes": None}
SERVES = {"streamlit": "sl", "web": "py"}
# Paths the hub routes itself: an app with one of these IDs could never be reached (hub page links excepted).
RESERVED_IDS = ("admin", "api", "cdf", "clear", "exit", "favicon.ico", "login", "logout", "metrics", "news", "out",
                "report", "restart", "setup", "static", "status.cmd", "temp", "update", "clear.cmd", "exit.cmd", "restart.cmd")
LAUNCHABLE = ("sl", "py", "cmd")
DISPLAY_VALUES = ("show", "disabled", "hidden")
RUNTIMES = ("process", "docker", "kubernetes")
RESTART_POLICIES = ("never", "on-failure", "always")
NEWS_TYPES = ("normal", "info", "warning")
STREAMLIT_HEALTH_PATH = "_stcore/health"

# What the admin page's selects show for these values: (value, label[, help]).
TYPE_CHOICES = (
    ("streamlit", "Streamlit app", "A Streamlit script, run on this server in the Python environment you pick"),
    ("python", "Python web app (Flask, Dash, FastAPI…)", "A Python web server, run on this server"),
    ("docker", "Docker image", "A container started from an image (pulled when missing)"),
    ("kubernetes", "Kubernetes pod", "A pod in the cluster the hub runs in"),
    ("url", "Link to a URL", "The card opens another website"),
    ("curl", "Proxy to a URL", "The hub serves another website under /<app ID>/, behind its own login"),
    ("page", "Hub page", "A card that opens a page of the hub, /<app ID>/"),
)
SERVES_CHOICES = (("web", "A web server (Flask, FastAPI, Node, nginx…)"), ("streamlit", "A Streamlit app"))
DISPLAY_CHOICES = (("show", "Show"), ("disabled", "Disabled (listed, can't open)"), ("hidden", "Hidden (opens by URL)"))
RESTART_CHOICES = (("never", "Never"), ("on-failure", "When it fails"), ("always", "Whenever it stops"))
NEWS_CHOICES = (("normal", "Normal"), ("info", "Info (blue)"), ("warning", "Warning (orange)"))


@dataclass
class Board:
    """A group of apps (`<name>.brd`). `auth` boards are visible only to users who list them."""
    name: str
    label: str
    auth: bool


@dataclass
class AppSpec:
    """One entry of the apps file. Keys are documented in docs/configuration.md (App entry)."""
    app_id: str
    kind: str  # from `type`, else the app_id suffix: sl, py, url, curl, cmd, or internal (hub page links)
    boards: list = field(default_factory=list)
    name: str = ""
    description: str = ""
    icon: str = ""
    display: str = "show"
    developers: list = field(default_factory=list)
    children: list = field(default_factory=list)
    url: str = ""
    file: str = ""
    folder: Path | None = None
    virtual_environment: str = ""
    bash_file: Path | None = None
    command: list | None = None
    python_executable: str = ""
    activate: bool = False
    env: dict = field(default_factory=dict)
    env_passthrough: list = field(default_factory=list)  # hub variables (globs) the app may see
    args: list = field(default_factory=list)
    auto_shutdown: bool = True
    auto_start: bool = False
    idle_timeout: int | None = None
    restart: str = "never"
    health_path: str | None = None  # None: the default for the app type; "": no health checks
    runtime: str = "process"
    image: str = ""
    container_port: int | None = None
    runtime_args: list = field(default_factory=list)
    volumes: list = field(default_factory=list)  # docker: `-v` values
    kubernetes: dict = field(default_factory=dict)
    streamlit_user_headers: bool | None = None  # None: the hub's `streamlit-user-headers`
    min_role: str | None = None   # built-in tools only

    @property
    def app_type(self):
        """The `type` name of what the app is and where it runs, also for apps typed by their suffix."""
        if self.runtime != "process":
            return self.runtime
        return {"sl": "streamlit", "py": "python", "cmd": "builtin", "internal": "page"}.get(self.kind, self.kind)

    @property
    def href(self):
        return f"/{self.app_id}/"

    @property
    def launchable(self):
        return self.kind in LAUNCHABLE

    @property
    def is_streamlit(self):
        return self.kind in ("sl", "cmd")

    @property
    def health(self):
        """Path under '/<app_id>/' polled for readiness and health, or "" for none."""
        if self.health_path is not None:
            return self.health_path.lstrip("/")
        return STREAMLIT_HEALTH_PATH if self.is_streamlit and self.kind != "curl" else ""

    @property
    def port_in_container(self):
        return self.container_port or (8501 if self.is_streamlit else 8000)


@dataclass
class User:
    """A signed-in user. `password` is a PBKDF2 hash (or legacy plain text); empty for SSO users."""
    name: str
    password: str
    role: str
    boards: list     # board names, or "*" for all
    source: str = "local"  # local, oidc or ldap


@dataclass
class NewsItem:
    """An announcement on the landing page; `type` is normal, info or warning."""
    title: str
    date: str
    message: str
    type: str


BUILTIN_TOOLS = {
    "help.cmd": AppSpec(app_id="help.cmd", kind="cmd", name="Help", file="help.py",
                        folder=PACKAGE_DIR / "tools", auto_shutdown=True),
}


def app_kind(app_id):
    """App type from the ID suffix; IDs without a known suffix are links to hub pages ("internal")."""
    return KINDS.get(os.path.splitext(app_id)[1].lower(), "internal")


class _JsonFile:
    """Parses a JSON file on first use and again whenever its mtime changes.

    On an invalid or unreadable file, `error` is set and the last good copy is kept, or, with
    `fail_closed`, the default is used instead. A file that disappears after it was loaded counts as
    unreadable for a `fail_closed` file. A file that never existed is simply empty.
    """

    def __init__(self, path, parse, default, fail_closed=False):
        self.path = Path(path)
        self._parse = parse
        self._default = default
        self._value = default
        self._mtime = None
        self.fail_closed = fail_closed
        self.error = ""

    def _fail(self, error):
        if error != self.error:
            log.error("%s; %s", error, "ignoring its content until it is fixed" if self.fail_closed
                      else "keeping the last loaded content")
        self.error = error
        if self.fail_closed:
            self._value = self._default

    def get(self):
        try:
            mtime = self.path.stat().st_mtime_ns
        except FileNotFoundError:
            if self._mtime is not None:
                self._mtime = None
                self._fail(f"{self.path} disappeared")
            return self._value
        except OSError as exc:
            self._mtime = None
            self._fail(f"Cannot read {self.path} ({exc})")
            return self._value
        if mtime != self._mtime:
            try:
                self._value = self._parse(json.loads(self.path.read_text(encoding="utf-8")))
                self.error = ""
            except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
                self._fail(f"Invalid {self.path} ({exc})")
            self._mtime = mtime
        return self._value


class Catalog:
    """Read-only view of the apps, users and news files, re-read whenever a file changes."""

    def __init__(self, settings):
        self.settings = settings
        self._apps = _JsonFile(settings.apps_file, self._parse_apps, ([], []))
        # Fail closed: an unreadable users file grants nothing, and SSO sessions are refused.
        self._users = _JsonFile(settings.users_file, _parse_users, {}, fail_closed=True)
        self._news = _JsonFile(settings.news_file, _parse_news, [])

    # -- apps and boards --
    @property
    def boards(self):
        return self._apps.get()[0]

    @property
    def apps(self):
        return self._apps.get()[1]

    def board(self, name):
        return next((b for b in self.boards if b.name == name), None)

    def all_apps(self):
        """Every app, children included (one level deep)."""
        for app in self.apps:
            yield app
            yield from app.children

    def find(self, app_id):
        """Catalog entry for `app_id`. Built-in tools resolve even when the apps file does not list them."""
        found = next((a for a in self.all_apps() if a.app_id == app_id), None)
        builtin = BUILTIN_TOOLS.get(app_id)
        if builtin:
            if found is None:
                return builtin
            return replace(builtin, boards=found.boards, name=found.name or builtin.name,
                           description=found.description, icon=found.icon, display=found.display,
                           developers=found.developers)
        if found is None or found.kind == "cmd":
            return None
        return found

    def _parse_apps(self, data):
        if not isinstance(data, list) or not data or "boards" not in data[0]:
            raise ValueError("the first element must be {\"boards\": [...]}")
        boards = [Board(name=b["name"], label=b.get("label", b["name"]), auth=bool(b.get("auth", False)))
                  for b in data[0]["boards"]]
        apps, seen = [], set()
        for raw in data[1:]:
            if not isinstance(raw, dict) or "app_id" not in raw:
                continue
            app = self._parse_app(raw)
            app.children = [self._parse_app(child) for child in raw.get("children") or []
                            if isinstance(child, dict) and "app_id" in child]
            for entry in (app, *app.children):
                if entry.app_id in seen:
                    raise ValueError(f"app_id '{entry.app_id}' is used twice")
                seen.add(entry.app_id)
            apps.append(app)
        return boards, apps

    def _parse_app(self, raw):
        base = self.settings.config_dir

        def path_or_none(value):
            if not value:
                return None
            path = Path(value).expanduser()
            return path if path.is_absolute() else (base / path).resolve()

        app_id = raw["app_id"]
        if not isinstance(app_id, str) or not app_id or "/" in app_id or app_id != app_id.strip():
            raise ValueError(f"app_id {app_id!r}: must be a non-empty name without '/' or surrounding spaces")
        kind, runtime = self._app_type(app_id, raw)
        if raw.get("restart", "never") not in RESTART_POLICIES:
            raise ValueError(f"{app_id}: restart must be one of {RESTART_POLICIES}")
        for key in ("idle_timeout", "container_port"):
            if raw.get(key) is not None and (isinstance(raw[key], bool) or not isinstance(raw[key], int)):
                raise ValueError(f"{app_id}: {key} must be an integer")
        for key, expected in (("command", list), ("args", list), ("env", dict), ("env_passthrough", list),
                              ("runtime_args", list), ("volumes", list), ("kubernetes", dict), ("health_path", str)):
            if raw.get(key) is not None and not isinstance(raw[key], expected):
                raise ValueError(f"{app_id}: {key} must be a "
                                 f"{'list' if expected is list else 'JSON object' if expected is dict else 'string'}")
        for volume in raw.get("volumes") or []:
            if not isinstance(volume, str) or not volume or volume.startswith("-"):
                raise ValueError(f"{app_id}: each volume is 'host path or volume:container path[:ro]'")
        display = raw.get("display", "show")
        if display not in DISPLAY_VALUES:
            raise ValueError(f"{raw['app_id']}: display must be one of {DISPLAY_VALUES}")
        if runtime != "process" and not raw.get("image"):
            raise ValueError(f"{raw['app_id']}: runtime '{runtime}' needs an 'image'")
        board = raw.get("board", [])
        return AppSpec(
            app_id=raw["app_id"],
            kind=kind,
            boards=[board] if isinstance(board, str) else list(board),
            name=raw.get("app_name") or raw["app_id"],
            description=raw.get("description", ""),
            icon=raw.get("icon") or "",
            display=display,
            developers=[(d.get("name", ""), d.get("email", "")) for d in raw.get("developer") or []],
            url=raw.get("url", ""),
            file=raw.get("file", ""),
            folder=path_or_none(raw.get("folder")),
            virtual_environment=raw.get("virtual_environment") or "",
            bash_file=path_or_none(raw.get("bash_file")),
            command=raw.get("command"),
            python_executable=raw.get("python_executable") or "",
            activate=bool(raw.get("activate", False)),
            env={str(k): str(v) for k, v in (raw.get("env") or {}).items()},
            env_passthrough=[str(n) for n in raw.get("env_passthrough") or []],
            args=[str(a) for a in raw.get("args") or []],
            auto_shutdown=bool(raw.get("auto_shutdown", True)),
            auto_start=bool(raw.get("auto_start", False)),
            idle_timeout=raw.get("idle_timeout"),
            restart=raw.get("restart", "never"),
            health_path=raw.get("health_path"),
            runtime=runtime,
            image=raw.get("image") or "",
            container_port=raw.get("container_port"),
            runtime_args=[str(a) for a in raw.get("runtime_args") or []],
            volumes=list(raw.get("volumes") or []),
            kubernetes=dict(raw.get("kubernetes") or {}),
            streamlit_user_headers=raw.get("streamlit_user_headers"),
        )

    @staticmethod
    def _app_type(app_id, raw):
        """(kind, runtime) from `type` (and `serves`), else from the app_id suffix and `runtime`."""
        app_type = raw.get("type")
        runtime = raw.get("runtime") or "process"
        if app_type is None:
            kind = app_kind(app_id)
        elif app_type not in TYPES:
            raise ValueError(f"{app_id}: type must be one of {', '.join(TYPES)}")
        elif TYPES[app_type] is None:  # docker or kubernetes
            runtime = app_type
            serves = raw.get("serves", "web")
            if serves not in SERVES:
                raise ValueError(f"{app_id}: serves must be streamlit or web")
            kind = SERVES[serves]
        else:
            kind = TYPES[app_type]
        if runtime not in RUNTIMES:
            raise ValueError(f"{app_id}: runtime must be one of {RUNTIMES}")
        if app_type is not None and kind != "internal" and (app_id.lower() in RESERVED_IDS or app_id.endswith(".brd")):
            raise ValueError(f"app_id '{app_id}' is a path of the hub itself: pick another")
        return kind, runtime

    # -- users --
    def users(self):
        """Users from the file, plus the admin defined by STREAMHUB_ADMIN_PASSWORD (it wins on a name clash)."""
        users = dict(self._users.get())
        admin_password = os.environ.get("STREAMHUB_ADMIN_PASSWORD")
        if admin_password:
            name = os.environ.get("STREAMHUB_ADMIN_USER", "admin")
            users[name] = User(name=name, password=env_password(admin_password), role="admin", boards=["*"])
        return users

    def user(self, name):
        return self.users().get(name) if name else None

    @property
    def users_error(self):
        """Why the users file can't be used right now, or "" (only the STREAMHUB_ADMIN_PASSWORD admin works)."""
        self._users.get()
        return self._users.error

    def errors(self):
        """{"apps" | "users" | "news": problem} for every catalog file that is currently invalid."""
        files = {"apps": self._apps, "users": self._users, "news": self._news}
        for file in files.values():
            file.get()
        return {name: file.error for name, file in files.items() if file.error}

    # -- news --
    def news(self):
        return self._news.get()


def _parse_users(data):
    """Local users need a password. Entries with `"source": "oidc"` or `"ldap"` set the role and boards of
    that SSO account instead of group mapping, and can never be used to log in with a password."""
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    users = {}
    for name, u in data.items():
        if not isinstance(u, dict):
            continue
        source = u.get("source", "local")
        if source == "local" and "password" not in u:
            continue
        if source not in ("local", "oidc", "ldap"):
            raise ValueError(f"user '{name}': source must be local, oidc or ldap")
        if u.get("role", "user") not in ROLES:
            raise ValueError(f"user '{name}': role must be one of {', '.join(ROLES)}")
        if not isinstance(u.get("boards", []), list):
            raise ValueError(f"user '{name}': boards must be a list")
        users[name] = User(name=name, password=str(u.get("password", "")) if source == "local" else "",
                           role=u.get("role", "user"), boards=list(u.get("boards", [])), source=source)
    return users


def _parse_news(data):
    if not isinstance(data, list):
        raise ValueError("expected a JSON array")
    return [NewsItem(title=n["title"], date=n.get("date", ""), message=n.get("message", ""),
                     type=n.get("type", "normal"))
            for n in data if isinstance(n, dict) and "title" in n]
