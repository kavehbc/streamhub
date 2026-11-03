"""Hub configuration: `streamhub.json` mapped onto one typed object.

Every key is optional. `null` or a missing key means "use the default". Relative paths are
resolved against the folder that holds the config file. Secrets may come from the environment.
"""
import json
import logging
import os
import re
import secrets
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

PACKAGE_DIR = Path(__file__).resolve().parent
CONFIG_FILE_NAME = "streamhub.json"
SECRET_FILE_NAME = ".streamhub-secret"
# Asymmetric ID-token signatures accepted from an OpenID provider; never "none" or HMAC.
OIDC_ALGORITHMS = ("RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512")
BIND_CHECKS = ("warn", "refuse", "off")
NOTIFIER_TYPES = ("slack", "teams", "email")


class ConfigError(Exception):
    """Invalid configuration: startup stops with this message."""


@dataclass
class Settings:
    """Every hub setting. Defaults here; JSON keys and env overrides in _KEYS and _ENV below."""
    config_dir: Path
    config_file: Path | None = None
    server_url: str = "http://localhost"
    apps_file: Path = None
    users_file: Path = None
    news_file: Path = None
    cdf_path: Path = PACKAGE_DIR / "cdf"
    temp_path: Path = None
    log_path: Path = None
    schedule: str | None = "02:00"
    timezone: str | None = None
    template_folder: Path = PACKAGE_DIR / "templates"
    template_file: str = "main.html"
    slack_name: str = ""
    slack_hook: str = ""
    virtual_environment: str = ""
    port: int = 8500
    ssl_port: int = 0
    ssl_cert: Path | None = None
    ssl_key: Path | None = None
    behind_proxy: bool = False
    port_exceptions: list = field(default_factory=lambda: [8501])
    port_range: tuple = None
    cookie_secret: str = ""
    session_days: int = 7
    idle_timeout: int = 0
    startup_timeout: int = 120
    proxy_timeout: int = 300
    stop_timeout: int = 10
    max_ws_message_mb: int = 200
    health_interval: int = 30
    health_failures: int = 3
    kubernetes_namespace: str = ""
    docker_socket: str = ""        # "" uses Docker's default (DOCKER_HOST, else /var/run/docker.sock)
    docker_network: str = ""       # "" publishes app containers on 127.0.0.1
    instance_id: str = ""
    env_passthrough: list = field(default_factory=list)
    bind_check: str = "warn"
    max_upload_mb: int = 1024
    usage_retention_days: int = 90
    streamlit_user_headers: bool = False
    drain_timeout: int = 10
    sessions_file: Path = None
    sso_session_minutes: int = 0
    notifiers: list = field(default_factory=list)
    smtp: dict = field(default_factory=dict)
    smtp_password: str = ""        # secrets: environment only, never read from the file
    oidc: dict = field(default_factory=dict)
    oidc_client_secret: str = ""
    ldap: dict = field(default_factory=dict)
    ldap_bind_password: str = ""
    metrics_token: str = ""
    group_mapping: list = field(default_factory=list)
    sso_default_role: str | None = None
    site_title: str = "Streamhub"
    team_name: str = ""
    logo: str = ""
    footer: str = ""

    def __post_init__(self):
        self.apps_file = self.apps_file or self.config_dir / "streamhub-apps.json"
        self.users_file = self.users_file or self.config_dir / "streamhub-users.json"
        self.news_file = self.news_file or self.config_dir / "streamhub-news.json"
        self.sessions_file = self.sessions_file or self.config_dir / ".streamhub-sessions.sqlite3"
        # Instances that share a config folder keep their own temp files and logs.
        per_instance = Path(self.instance_id) if self.instance_id else Path()
        self.temp_path = self.temp_path or self.config_dir / "temp" / per_instance
        self.log_path = self.log_path or self.config_dir / "logs" / per_instance

    @property
    def internal_port_range(self):
        """Ports handed to apps: `port-range`, or the 1000 ports after the hub's port."""
        return self.port_range or (self.port + 1, self.port + 1000)


# JSON key -> (attribute, converter). Converters receive the config dir and the raw value.
def _str(_, v):
    if not isinstance(v, str):
        raise TypeError("expected a string")
    return v


def _int(_, v):
    if isinstance(v, bool):
        raise TypeError("expected an integer")
    return int(v)


def _bool(_, v):
    if not isinstance(v, bool):
        raise TypeError("expected true or false")
    return v


def _path(base, v):
    path = Path(_str(base, v)).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def _int_list(_, v):
    if not isinstance(v, list):
        raise TypeError("expected a list of integers")
    return [int(x) for x in v]


def _str_list(_, v):
    if not (isinstance(v, list) and all(isinstance(x, str) for x in v)):
        raise TypeError("expected a list of strings")
    return v


def _choice(*allowed):
    def convert(_, v):
        if v not in allowed:
            raise ValueError(f"expected one of {', '.join(allowed)}")
        return v
    return convert


def _dict(_, v):
    if not isinstance(v, dict):
        raise TypeError("expected a JSON object")
    return v


def _object_list(_, v):
    if not (isinstance(v, list) and all(isinstance(x, dict) for x in v)):
        raise TypeError("expected a list of JSON objects")
    return v


# Layouts renamed since: the old name keeps working.
RENAMED_LAYOUTS = {"main_2.html": "main_side.html"}


def _template_file(_, v):
    if _str(_, v) in RENAMED_LAYOUTS:
        log.warning("'template-file': %s is now called %s; update streamhub.json", v, RENAMED_LAYOUTS[v])
        return RENAMED_LAYOUTS[v]
    return v


def _timezone(_, v):
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    try:
        ZoneInfo(_str(_, v))
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(f"unknown time zone {v!r}: use an IANA name such as Europe/Paris") from None
    return v


def _role(_, v):
    from streamhub.auth import ROLES

    if v not in ROLES:
        raise ValueError(f"expected one of {', '.join(ROLES)}")
    return v


def _instance(_, v):
    if not re.fullmatch(r"[a-z0-9]([a-z0-9-]{0,30}[a-z0-9])?", _str(_, v)):
        raise ValueError("use 1-32 lowercase letters, digits and '-'")
    return v


def _docker_name(_, v):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", _str(_, v)):
        raise ValueError("use letters, digits, '_', '.' and '-'")
    return v


def _docker_socket(_, v):
    if _str(_, v).startswith("-") or any(ord(c) < 32 for c in v):
        raise ValueError("expected a socket path or a Docker host URL")
    return v


def _range(_, v):
    if not (isinstance(v, list) and len(v) == 2):
        raise TypeError("expected [first, last]")
    first, last = int(v[0]), int(v[1])
    if first > last:
        raise ValueError("first port is greater than last port")
    return first, last


_KEYS = {
    "server-url": ("server_url", _str),
    "apps": ("apps_file", _path),
    "users": ("users_file", _path),
    "news": ("news_file", _path),
    "cdf": ("cdf_path", _path),
    "temp": ("temp_path", _path),
    "log-folder": ("log_path", _path),
    "timezone": ("timezone", _timezone),
    "template-folder": ("template_folder", _path),
    "template-file": ("template_file", _template_file),
    "slack-name": ("slack_name", _str),
    "slack-hook": ("slack_hook", _str),
    "virtual-environment": ("virtual_environment", _str),
    "port": ("port", _int),
    "ssl_port": ("ssl_port", _int),
    "ssl-cert": ("ssl_cert", _path),
    "ssl-key": ("ssl_key", _path),
    "behind-proxy": ("behind_proxy", _bool),
    "port-exception": ("port_exceptions", _int_list),
    "port-range": ("port_range", _range),
    "cookie-secret": ("cookie_secret", _str),
    "session-days": ("session_days", _int),
    "idle-timeout": ("idle_timeout", _int),
    "startup-timeout": ("startup_timeout", _int),
    "proxy-timeout": ("proxy_timeout", _int),
    "stop-timeout": ("stop_timeout", _int),
    "max-ws-message-mb": ("max_ws_message_mb", _int),
    "health-interval": ("health_interval", _int),
    "health-failures": ("health_failures", _int),
    "kubernetes-namespace": ("kubernetes_namespace", _str),
    "docker-socket": ("docker_socket", _docker_socket),
    "docker-network": ("docker_network", _docker_name),
    "instance-id": ("instance_id", _instance),
    "env-passthrough": ("env_passthrough", _str_list),
    "bind-check": ("bind_check", _choice(*BIND_CHECKS)),
    "max-upload-mb": ("max_upload_mb", _int),
    "usage-retention-days": ("usage_retention_days", _int),
    "streamlit-user-headers": ("streamlit_user_headers", _bool),
    "drain-timeout": ("drain_timeout", _int),
    "sessions-db": ("sessions_file", _path),
    "sso-session-minutes": ("sso_session_minutes", _int),
    "notifiers": ("notifiers", _object_list),
    "smtp": ("smtp", _dict),
    "oidc": ("oidc", _dict),
    "ldap": ("ldap", _dict),
    "group-mapping": ("group_mapping", _object_list),
    "sso-default-role": ("sso_default_role", _role),
    "site-title": ("site_title", _str),
    "team-name": ("team_name", _str),
    "logo": ("logo", _str),
    "footer": ("footer", _str),
}
_IGNORED = {"master-password", "slack-hook_comment"}

# Settings that only take effect on the next start (attribute names).
RESTART_ONLY = ("port", "ssl_port", "ssl_cert", "ssl_key", "behind_proxy", "cdf_path", "temp_path",
                "log_path", "template_folder", "cookie_secret", "port_range", "max_ws_message_mb",
                "health_interval", "instance_id", "sessions_file", "usage_retention_days")

# The Settings form of the admin page: (section, [(key, kind, label, placeholder, help)]). Every key of
# _KEYS, plus "schedule", appears exactly once. The placeholder shows the default. Kinds:
#   text, secret, int, bool, ints, strings (comma separated), path (checked on the server), image (a picker of
#   /cdf/ images), layout (the templates found), timezone, environment (the conda envs found), schedule,
#   choice:<list> (a list of the admin page's choices), object:<form> and list:<form> (a SUBFORMS entry).
# An empty field removes the key, so its default applies.
SETTINGS_FORM = (
    ("Branding", (
        ("site-title", "text", "Site title", "Streamhub", "Heads the landing page and names the browser tab"),
        ("team-name", "text", "Team name", "", "Shown under the top menu"),
        ("logo", "image", "Logo", "the Streamhub logo", "Image for the top menu: pick or upload one"),
        ("footer", "text", "Footer", "the site title", "Text at the bottom of every page"),
        ("template-file", "layout", "Layout", "main.html", "How the landing, news and board pages are laid out"),
        ("template-folder", "path", "Template folder", "bundled",
         "A folder of your own templates, which override the bundled ones"),
    )),
    ("Server", (
        ("server-url", "text", "Server URL", "http://localhost",
         "The address people use to reach the hub, for links in notifications"),
        ("port", "int", "HTTP port", "8500", "The one port the hub and all its apps are served on"),
        ("ssl_port", "int", "HTTPS port", "0 (off)", "Needs the certificate and key below"),
        ("ssl-cert", "path", "TLS certificate", "", "PEM file, for the HTTPS port"),
        ("ssl-key", "path", "TLS key", "", "PEM file, for the HTTPS port"),
        ("behind-proxy", "bool", "Behind a reverse proxy", "",
         "Turn on when nginx, a load balancer or similar forwards requests to the hub"),
        ("instance-id", "text", "Instance ID", "", "Only for several hubs behind one address: 1-32 lowercase "
         "letters, digits and '-'"),
        ("port-range", "ints", "App port range", "port+1, port+1000", "First and last port handed to apps"),
        ("port-exception", "ints", "Reserved ports", "8501", "Ports never handed to apps, comma separated"),
        ("max-upload-mb", "int", "Largest upload (MB)", "1024", "Per request to an app"),
        ("max-ws-message-mb", "int", "Largest WebSocket message (MB)", "200", "Streamlit file uploads use these"),
        ("proxy-timeout", "int", "Proxy timeout (s)", "300", "Per proxied request or WebSocket connect"),
    )),
    ("Apps", (
        ("virtual-environment", "environment", "Default Python environment", "the hub's own Python",
         "Conda env name or environment folder, for apps that name none"),
        ("idle-timeout", "int", "Idle timeout (min)", "0 (off)", "Stop apps nobody used for this long "
         "(apps with 'Stop on memory clean and when idle')"),
        ("startup-timeout", "int", "Startup timeout (s)", "120", "How long an app may take to start"),
        ("stop-timeout", "int", "Stop timeout (s)", "10", "Grace period before an app is killed"),
        ("drain-timeout", "int", "Drain timeout (s)", "10", "Wait for open requests on stop or restart"),
        ("health-interval", "int", "Health check interval (s)", "30", "0 turns the checks off"),
        ("health-failures", "int", "Health failures", "3", "Failed checks in a row before an app is stopped"),
        ("bind-check", "choice:bind-check", "Bind check", "warn",
         "What to do with an app that listens beyond this machine (127.0.0.1), around the hub's login"),
        ("env-passthrough", "strings", "Environment passthrough", "",
         "Hub variables (globs such as AWS_*) every app receives, comma separated"),
        ("streamlit-user-headers", "bool", "Streamlit user headers", "", "Tell Streamlit apps who the user is "
         "(st.user)"),
        ("kubernetes-namespace", "text", "Kubernetes namespace", "the hub pod's, else default",
         "Where Kubernetes apps run"),
    )),
    ("Docker", (
        ("docker-socket", "text", "Docker socket", "/var/run/docker.sock",
         "Socket path or Docker host URL (unix://, npipe://, tcp://) of the daemon that runs docker apps"),
        ("docker-network", "text", "Docker network", "none: publish on 127.0.0.1",
         "When the hub runs in a container: app containers join this network and the hub reaches them by name"),
    )),
    ("Schedule and files", (
        ("schedule", "schedule", "Daily memory clean", "02:00", "Stops idle-able apps and empties the temp "
         "folder every day at this time"),
        ("timezone", "timezone", "Time zone", "server local", "Of the daily clean; start typing to pick one"),
        ("apps", "path", "Apps file", "streamhub-apps.json", ""),
        ("users", "path", "Users file", "streamhub-users.json", ""),
        ("news", "path", "News file", "streamhub-news.json", ""),
        ("cdf", "path", "Static folder (/cdf/)", "bundled", "Icons and logos. Use a folder of your own so "
         "uploads survive upgrades"),
        ("temp", "path", "Temp folder (/temp/)", "<config>/temp", "Emptied on every memory clean"),
        ("log-folder", "path", "Log folder", "<config>/logs", ""),
        ("sessions-db", "path", "Sessions database", "<config>/.streamhub-sessions.sqlite3", ""),
        ("usage-retention-days", "int", "Usage retention (days)", "90", "0 keeps everything"),
    )),
    ("Sign-in", (
        ("session-days", "int", "Session lifetime (days)", "7", "How long a login lasts"),
        ("sso-session-minutes", "int", "SSO session limit (min)", "0 (session lifetime)",
         "Sign single sign-on users in again after this long, so group changes apply"),
        ("cookie-secret", "secret", "Cookie secret", "generated",
         "Leave empty: one is generated. Or prefer STREAMHUB_COOKIE_SECRET, so it stays out of git"),
        ("sso-default-role", "choice:roles", "SSO default role", "none: no access",
         "For single sign-on users no group mapping rule matches"),
        ("oidc", "object:oidc", "OpenID Connect", "off", "Sign in with Azure AD (Entra ID), Okta, Keycloak, Google…"),
        ("ldap", "object:ldap", "LDAP", "off", "Sign in with a directory password (Active Directory, OpenLDAP)"),
        ("group-mapping", "list:group-mapping", "Group mapping", "none",
         "Give single sign-on users a role and boards from their directory groups"),
    )),
    ("Notifications", (
        ("slack-hook", "secret", "Slack webhook", "",
         "Prefer STREAMHUB_SLACK_HOOK, so the secret stays out of git"),
        ("slack-name", "text", "Slack channel name", "", "Used in logs only"),
        ("notifiers", "list:notifiers", "Channels", "none", "Where the hub reports starts, cleans, failing "
         "apps and issue reports"),
        ("smtp", "object:smtp", "Mail server", "off", "For email channels, and to email issue reports to developers"),
    )),
)

SECTION_HELP = {
    "Branding": "How the hub looks to its users.",
    "Server": "Where the hub listens. Most of these apply after a restart.",
    "Apps": "Defaults for every app; an app's own settings win.",
    "Docker": "Only for apps of the Docker image type.",
    "Schedule and files": "The daily clean, and where the hub keeps its files (relative paths start at the "
                          "config folder).",
    "Sign-in": "Local accounts are on the Users tab. Here: sessions and single sign-on.",
    "Notifications": "Messages to Slack, Microsoft Teams or email.",
}

# Option lists of the admin page's selects: (value, label), referred to as choice:<name> and checks:<name>.
CHOICES = {
    "bind-check": (("warn", "Warn in the log"), ("refuse", "Stop the app and show why"), ("off", "Don't check")),
    "token-auth": (("basic", "HTTP Basic (client_secret_basic)"), ("post", "In the form (client_secret_post)")),
    "notifier-types": (("slack", "Slack webhook"), ("teams", "Microsoft Teams webhook"), ("email", "Email")),
    "oidc-algorithms": tuple((a, a) for a in OIDC_ALGORITHMS),
    "pull-policies": (("IfNotPresent", "If not present"), ("Always", "Always"), ("Never", "Never")),
}

# Forms for the JSON objects of the settings (and the app's `kubernetes`): {form: [(sub-key, kind, label,
# placeholder, help, shown when)]}. Kinds: text, int, bool, tristate, strings, json, boards, choice:<list>,
# checks:<list>. "shown when" is "" or "<sub-key>:<value>,<value>". Sub-keys a form doesn't know are kept.
SUBFORMS = {
    "oidc": (
        ("issuer", "text", "Issuer URL", "https://login.example.com/realms/main",
         "Your identity provider's address (https)", ""),
        ("client-id", "text", "Client ID", "", "Its secret, if any, comes from STREAMHUB_OIDC_CLIENT_SECRET", ""),
        ("label", "text", "Button label", "Single sign-on", "Shown on the login page", ""),
        ("scopes", "strings", "Scopes", "openid, profile, email", "Comma separated", ""),
        ("username-claim", "text", "User name claim", "preferred_username", "", ""),
        ("groups-claim", "text", "Groups claim", "groups", "Its groups feed the group mapping", ""),
        ("token-auth", "choice:token-auth", "Client authentication", "basic",
         "How the client secret reaches the token endpoint", ""),
        ("redirect-uri", "text", "Redirect URI", "<this site>/login/oidc/callback",
         "Register this at the provider; set it when a proxy changes the host name", ""),
        ("algorithms", "checks:oidc-algorithms", "Signature algorithms", "",
         "None checked: all of them", ""),
        ("insecure-http", "bool", "Allow an http:// issuer (development only)", "", "", ""),
    ),
    "ldap": (
        ("url", "text", "Server URL", "ldaps://ldap.example.com", "ldaps://, or ldap:// with STARTTLS", ""),
        ("user-dn", "text", "User DN template", "uid={username},ou=people,dc=example,dc=com",
         "Sign in as the user directly. Leave empty to search with a service account instead", ""),
        ("bind-dn", "text", "Service account DN", "cn=streamhub,dc=example,dc=com",
         "For the search; its password comes from STREAMHUB_LDAP_BIND_PASSWORD", ""),
        ("search-base", "text", "Search base", "ou=people,dc=example,dc=com", "", ""),
        ("search-filter", "text", "Search filter", "(uid={username})", "Active Directory: (sAMAccountName={username})",
         ""),
        ("group-attribute", "text", "Group attribute", "memberOf", "", ""),
        ("starttls", "bool", "Use STARTTLS (with ldap://)", "", "", ""),
        ("ca-file", "text", "CA certificate file", "the system's", "PEM file that signs the server's certificate",
         ""),
        ("allow-plaintext", "bool", "Allow unencrypted connections (development only)", "", "", ""),
    ),
    "smtp": (
        ("host", "text", "Host", "smtp.example.com", "Email is off without it", ""),
        ("port", "int", "Port", "465 with SSL, 587 with STARTTLS, else 25", "", ""),
        ("ssl", "bool", "SSL from the start (port 465)", "", "", ""),
        ("starttls", "tristate", "STARTTLS", "on unless SSL", "", ""),
        ("username", "text", "User name", "", "Its password comes from STREAMHUB_SMTP_PASSWORD", ""),
        ("from", "text", "From address", "the user name", "", ""),
    ),
    "notifiers": (
        ("type", "choice:notifier-types", "Channel", "", "", ""),
        ("url", "text", "Webhook URL", "https://hooks.slack.com/services/…", "", "type:slack,teams"),
        ("to", "strings", "Recipients", "ops@example.com", "Comma separated; needs the mail server", "type:email"),
        ("events", "checks:events", "Events", "", "None checked: every event", ""),
    ),
    "group-mapping": (
        ("group", "text", "Directory group", "data-team", "* matches everyone", ""),
        ("role", "choice:roles", "Role", "user", "", ""),
        ("boards", "boards", "Boards", "", "", ""),
    ),
    "kubernetes": (
        ("namespace", "text", "Namespace", "the hub's setting", "", ""),
        ("service_account", "text", "Service account", "default", "", ""),
        ("image_pull_policy", "choice:pull-policies", "Image pull policy", "Kubernetes' default", "", ""),
        ("image_pull_secrets", "strings", "Image pull secrets", "", "Secret names, comma separated", ""),
        ("resources", "json", "Resources", '{"limits": {"memory": "2Gi", "cpu": "1"}}',
         "JSON object of requests and limits", ""),
        ("node_selector", "json", "Node selector", '{"disktype": "ssd"}', "JSON object", ""),
        ("env_from", "json", "Environment from", '[{"secretRef": {"name": "app-env"}}]', "JSON list", ""),
    ),
}


def settings_form():
    """SETTINGS_FORM as JSON-ready sections. `restart` marks keys that apply only after a restart, `env` names
    the environment variable that overrides a key, and `envSet` says whether it is set (never its value)."""
    env_of = {attr: name for name, attr in _ENV.items()}
    sections = []
    for title, fields in SETTINGS_FORM:
        rows = []
        for key, kind, label, placeholder, help_text in fields:
            attr = _KEYS[key][0] if key in _KEYS else key
            env = env_of.get(attr, "")
            rows.append({"key": key, "kind": kind, "label": label, "placeholder": placeholder, "help": help_text,
                         "restart": attr in RESTART_ONLY, "env": env, "envSet": bool(env and os.environ.get(env))})
        sections.append({"title": title, "help": SECTION_HELP.get(title, ""), "fields": rows})
    return sections


def subforms():
    """SUBFORMS as JSON-ready field lists."""
    return {name: [{"key": key, "kind": kind, "label": label, "placeholder": placeholder, "help": help_text,
                    "when": when} for key, kind, label, placeholder, help_text, when in fields]
            for name, fields in SUBFORMS.items()}


def config_keys(attributes):
    """The JSON keys of Settings attribute names, for messages."""
    names = {attr: key for key, (attr, _) in _KEYS.items()}
    return [names.get(attr, attr) for attr in attributes]


_ENV = {
    "STREAMHUB_SLACK_HOOK": "slack_hook",
    "STREAMHUB_COOKIE_SECRET": "cookie_secret",
    "STREAMHUB_INSTANCE_ID": "instance_id",
    "STREAMHUB_DOCKER_SOCKET": "docker_socket",
    "STREAMHUB_DOCKER_NETWORK": "docker_network",
    "STREAMHUB_SMTP_PASSWORD": "smtp_password",
    "STREAMHUB_OIDC_CLIENT_SECRET": "oidc_client_secret",
    "STREAMHUB_LDAP_BIND_PASSWORD": "ldap_bind_password",
    "STREAMHUB_METRICS_TOKEN": "metrics_token",
}


def resolve_config_path(target):
    """`target` is a folder holding streamhub.json, or the config file itself."""
    target = Path(target).expanduser().resolve()
    if target.is_file():
        return target.parent, target
    if target.is_dir():
        candidate = target / CONFIG_FILE_NAME
        return target, (candidate if candidate.is_file() else None)
    raise ConfigError(f"Config path does not exist: {target}")


def config_target(settings):
    """The config file the admin page writes: the one in use, else streamhub.json in the config folder."""
    return settings.config_file or Path(settings.config_dir) / CONFIG_FILE_NAME


def load_settings(target, persist_secret=True):
    """Settings from the file, then environment overrides, then cross-key validation.

    `persist_secret` False never writes `.streamhub-secret` (validation only).
    """
    config_dir, config_file = resolve_config_path(target)
    data = None
    if config_file is None:
        log.warning("No %s in %s; using defaults (saving the Settings on the admin page creates it)",
                    CONFIG_FILE_NAME, config_dir)
    else:
        data = parse_config_text(config_file.read_text(encoding="utf-8"), config_file)
    return build_settings(config_dir, config_file, data, persist_secret)


def parse_config_text(text, config_file):
    """The JSON object of a config file, or ConfigError."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{config_file}: invalid JSON ({exc})") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{config_file}: expected a JSON object")
    return data


def build_settings(config_dir, config_file, data, persist_secret=True):
    """Settings from a parsed config object (None: defaults), environment overrides and validation."""
    values = _parse(config_dir, config_file, data) if data is not None else {}
    for env_name, attr in _ENV.items():
        if os.environ.get(env_name):
            values[attr] = os.environ[env_name]
    for attr, key, check in (("instance_id", "instance-id", _instance), ("docker_socket", "docker-socket", _docker_socket),
                             ("docker_network", "docker-network", _docker_name)):
        if attr in values:  # environment values are checked like the file's
            try:
                check(None, values[attr])
            except ValueError as exc:
                raise ConfigError(f"{key}: {exc}") from exc

    settings = Settings(config_dir=config_dir, config_file=config_file, **values)
    if not settings.cookie_secret:
        settings.cookie_secret = _stored_secret(config_dir) if persist_secret else secrets.token_urlsafe(48)
    if settings.ssl_port and not (settings.ssl_cert and settings.ssl_key):
        raise ConfigError("ssl_port is set but ssl-cert and ssl-key are not")
    for channel in settings.notifiers:
        if channel.get("type") not in NOTIFIER_TYPES:
            raise ConfigError("notifiers: each entry needs a 'type' of slack, teams or email")
    if settings.oidc:
        _check_oidc(settings.oidc)
    if settings.ldap:
        _check_ldap(settings.ldap)
    return settings


def _check_oidc(oidc):
    """HTTPS everywhere unless `insecure-http` (development only); signatures need PyJWT."""
    if not (oidc.get("issuer") and oidc.get("client-id")):
        raise ConfigError("oidc: 'issuer' and 'client-id' are required")
    if oidc.get("insecure-http"):
        log.warning("oidc: 'insecure-http' is set; use it for development only")
    elif not oidc["issuer"].startswith("https://"):
        raise ConfigError("oidc: the issuer must be https:// (or set 'insecure-http': true for development)")
    algorithms = oidc.get("algorithms")
    if algorithms is not None and not (isinstance(algorithms, list) and algorithms
                                       and set(algorithms) <= set(OIDC_ALGORITHMS)):
        raise ConfigError(f"oidc: 'algorithms' must be a non-empty subset of {', '.join(OIDC_ALGORITHMS)}")
    try:
        from jwt.algorithms import has_crypto
    except ImportError:
        has_crypto = False
    if not has_crypto:
        raise ConfigError("oidc: ID token signatures need PyJWT with cryptography: pip install 'py-streamhub[oidc]'")


def _check_ldap(ldap):
    """TLS (ldaps:// or STARTTLS) unless `allow-plaintext` (development only)."""
    url = str(ldap.get("url") or "")
    if not url:
        raise ConfigError("ldap: 'url' is required")
    if not url.lower().startswith(("ldap://", "ldaps://")):
        raise ConfigError("ldap: 'url' must start with ldap:// or ldaps://")
    secure = url.lower().startswith("ldaps://") or ldap.get("starttls")
    if ldap.get("allow-plaintext"):
        log.warning("ldap: 'allow-plaintext' is set; passwords may cross the network unencrypted")
    elif not secure:
        raise ConfigError("ldap: use ldaps:// or 'starttls': true (or 'allow-plaintext': true for development)")


def _parse(config_dir, config_file, data):
    """Map JSON keys to Settings attributes; null or "" keeps the default, unknown keys only warn."""
    values = {}
    for key, raw in data.items():
        if key in _IGNORED:
            if key == "master-password" and raw:
                log.warning("'master-password' is no longer used and is ignored; remove it from %s",
                            config_file)
            continue
        if key == "schedule":
            # null, "" or "off" disables the daily memory clean.
            values["schedule"] = None if raw in (None, "", "off") else _check_time(raw)
            continue
        if key not in _KEYS:
            log.warning("Unknown config key '%s' in %s", key, config_file)
            continue
        if raw is None or raw == "":
            continue
        attr, convert = _KEYS[key]
        try:
            values[attr] = convert(config_dir, raw)
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"{config_file}: '{key}': {exc}") from exc
    return values


def _check_time(raw):
    try:
        hour, minute = (int(x) for x in str(raw).split(":"))
        if not (0 <= hour < 24 and 0 <= minute < 60):
            raise ValueError
    except ValueError:
        raise ConfigError(f"'schedule' must be HH:MM, got {raw!r}") from None
    return f"{hour:02d}:{minute:02d}"


def _stored_secret(config_dir):
    """A random cookie secret kept next to the config, so sessions survive restarts."""
    path = config_dir / SECRET_FILE_NAME
    try:
        if path.is_file():
            value = path.read_text(encoding="utf-8").strip()
            if value:
                return value
        value = secrets.token_urlsafe(48)
        path.write_text(value, encoding="utf-8")
        return value
    except OSError as exc:
        log.warning("Cannot persist cookie secret in %s (%s); sessions end on restart", path, exc)
        return secrets.token_urlsafe(48)
