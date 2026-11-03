"""Configuration checks shared by `streamhub check` and the admin page's JSON editor.

Nothing here starts an app, opens a port, writes a file or prints a secret value.
"""
import importlib.util
import json
from pathlib import Path

from streamhub import auth, platform_utils
from streamhub.catalog import Catalog, _parse_news, _parse_users
from streamhub.config import ConfigError, build_settings, load_settings, parse_config_text

SECRET_KEYS = ("cookie-secret", "slack-hook")
SECRET_ENV = ("STREAMHUB_*PASSWORD*", "STREAMHUB_*SECRET*", "STREAMHUB_*TOKEN*", "STREAMHUB_*HOOK*")


def check_text(key, text, settings):
    """Validate the new content of one of the hub's files. Returns (errors, warnings), as strings.

    `key` is config, apps, users or news; `settings` are the running hub's.
    """
    try:
        data = json.loads(text)
    except ValueError as exc:
        return [f"invalid JSON ({exc})"], []
    try:
        if key == "config":
            path = settings.config_file or settings.config_dir / "streamhub.json"
            fresh = build_settings(settings.config_dir, path, parse_config_text(text, path), persist_secret=False)
            return [], config_warnings(fresh, data)
        if key == "apps":
            _, apps = Catalog(settings)._parse_apps(data)
            return [], apps_warnings(data, apps, settings)
        if key == "users":
            _parse_users(data)
            return [], []
        _parse_news(data)
        return [], []
    except (ConfigError, ValueError, TypeError, KeyError, AttributeError) as exc:
        return [str(exc)], []


def config_warnings(settings, data):
    """Security-sensitive or risky settings that are still valid."""
    warnings = [f"'{key}' is in the file; prefer its environment variable so the secret stays out of git"
                for key in SECRET_KEYS if data.get(key)]
    if settings.bind_check == "off":
        warnings.append("'bind-check' is off: apps listening on every interface go unnoticed (SEC-12)")
    exposed = [p for p in settings.env_passthrough if any(platform_utils.child_env([p], base=False, environ={
        name: "" for name in ("STREAMHUB_ADMIN_PASSWORD", "STREAMHUB_COOKIE_SECRET", "STREAMHUB_SMTP_PASSWORD",
                              "STREAMHUB_OIDC_CLIENT_SECRET", "STREAMHUB_LDAP_BIND_PASSWORD",
                              "STREAMHUB_METRICS_TOKEN", "STREAMHUB_SLACK_HOOK")}))]
    if exposed:
        warnings.append(f"'env-passthrough' {exposed} passes hub secrets to every app")
    if settings.oidc.get("insecure-http"):
        warnings.append("oidc: 'insecure-http' is for development only")
    if settings.ldap.get("allow-plaintext"):
        warnings.append("ldap: 'allow-plaintext' sends passwords unencrypted")
    if settings.ldap and importlib.util.find_spec("ldap3") is None:
        warnings.append("ldap is configured but ldap3 is not installed: pip install 'py-streamhub[ldap]'")
    for name in ("ssl_cert", "ssl_key"):
        path = getattr(settings, name)
        if settings.ssl_port and path and not Path(path).is_file():
            warnings.append(f"{name.replace('_', '-')} not found: {path}")
    return warnings


def apps_warnings(data, apps, settings):
    """References that look wrong but do not stop the hub: unknown boards, missing files and tools."""
    boards = {b.get("name") for b in data[0].get("boards", [])}
    warnings = []
    for app in [a for parent in apps for a in (parent, *parent.children)]:
        for board in app.boards:
            if board and board not in boards:
                warnings.append(f"{app.app_id}: board '{board}' is not defined")
        if not app.launchable:
            continue
        if app.runtime == "process" and app.kind != "cmd":
            if app.file and not app.command and not app.bash_file:
                main = Path(app.file)
                if not main.is_absolute():  # relative to the working directory: the folder, else the config folder
                    main = Path(app.folder or settings.config_dir) / main
                if not main.is_file():
                    warnings.append(f"{app.app_id}: file not found: {main}")
            if app.bash_file and not Path(app.bash_file).is_file():
                warnings.append(f"{app.app_id}: bash_file not found: {app.bash_file}")
            if app.python_executable and not Path(app.python_executable).is_file():
                warnings.append(f"{app.app_id}: python_executable not found: {app.python_executable}")
        if app.runtime != "process" and app.is_streamlit and not (app.file or app.command):
            warnings.append(f"{app.app_id}: a Streamlit image needs 'file' or 'command'")
        if app.volumes and app.runtime != "docker":
            warnings.append(f"{app.app_id}: 'volumes' applies to docker apps only")
        if app.runtime == "docker" and not platform_utils.docker_exe():
            warnings.append(f"{app.app_id}: docker is not on PATH (or set STREAMHUB_DOCKER)")
        if app.runtime == "kubernetes" and not platform_utils.kubectl_exe():
            warnings.append(f"{app.app_id}: kubectl is not on PATH (or set STREAMHUB_KUBECTL)")
    return warnings


def check(target):
    """(errors, warnings) for a whole config folder: settings, catalog files and their references."""
    try:
        settings = load_settings(target, persist_secret=False)
    except ConfigError as exc:
        return [str(exc)], []
    errors, warnings = [], []
    if settings.config_file:
        data = json.loads(settings.config_file.read_text(encoding="utf-8"))
        warnings += config_warnings(settings, data)
    for key, path in (("apps", settings.apps_file), ("users", settings.users_file), ("news", settings.news_file)):
        if not Path(path).is_file():
            if key == "apps":
                warnings.append(f"no apps file at {path}")
            continue
        file_errors, file_warnings = check_text(key, Path(path).read_text(encoding="utf-8"), settings)
        errors += [f"{Path(path).name}: {e}" for e in file_errors]
        warnings += [f"{Path(path).name}: {w}" for w in file_warnings]
        if key == "users" and not file_errors:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            raw = [name for name, entry in data.items() if isinstance(entry, dict) and "password" in entry
                   and entry.get("source", "local") == "local" and not auth.is_hashed(entry["password"])]
            if raw:
                errors.append(f"{Path(path).name}: raw passwords for {', '.join(raw)}; "
                              "run `streamhub hash-passwords`")
    return errors, warnings
