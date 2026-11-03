"""Getting started: `streamhub init` (a starter config folder), `streamhub demo` (the bundled demo) and the
first admin account written by the setup page."""
import json
import os
import shutil
from pathlib import Path

from streamhub import auth, platform_utils
from streamhub.config import CONFIG_FILE_NAME, PACKAGE_DIR

STARTER_DIR = PACKAGE_DIR / "starter"
DEMO_DIR = PACKAGE_DIR / "demo"
USERS_FILE_NAME = "streamhub-users.json"
# Left behind by a run of the demo: never copied, never overwritten.
_RUNTIME = shutil.ignore_patterns("logs", "temp", "backups", ".streamhub-*", "streamhub-users.json", "__pycache__")


def write_atomically(path, text):
    """Readers see the old or the new content, never half a file."""
    path = Path(path)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def read_json(path, default):
    """The JSON content of `path`, or `default` when it does not exist."""
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def write_json(path, data):
    write_atomically(path, json.dumps(data, indent="\t") + "\n")


def add_admin(users_file, name, password):
    """Add (or replace) a local admin with access to every board; the other users stay."""
    users = read_json(users_file, {})
    if not isinstance(users, dict):
        raise ValueError(f"{users_file}: expected a JSON object of users")
    users[name] = {"password": auth.hash_password(password), "role": "admin", "boards": ["*"]}
    write_json(users_file, users)


def update_config(config_file, **values):
    """Set keys of streamhub.json (creating it when missing); a None value is skipped."""
    data = read_json(config_file, {})
    data.update({key: value for key, value in values.items() if value is not None})
    write_json(config_file, data)


def init_folder(folder, site_title="Streamhub", port=8500, admin_user="admin", admin_password=None, force=False):
    """Write the starter config into `folder` (and a users file when a password is given). Returns the files.

    Raises FileExistsError, naming the files, when any already exists and `force` is False.
    """
    folder = Path(folder)
    names = [p.name for p in sorted(STARTER_DIR.glob("*.json"))]
    if admin_password:
        names.append(USERS_FILE_NAME)
    existing = [name for name in names if (folder / name).exists()]
    if existing and not force:
        raise FileExistsError(", ".join(existing))
    folder.mkdir(parents=True, exist_ok=True)
    for name in names:
        if name != USERS_FILE_NAME:
            shutil.copyfile(STARTER_DIR / name, folder / name)
    update_config(folder / CONFIG_FILE_NAME, **{"site-title": site_title, "port": port})
    if admin_password:
        add_admin(folder / USERS_FILE_NAME, admin_user, admin_password)
    return [folder / name for name in names]


def prepare_demo(target=None):
    """Copy the bundled demo to a writable folder (the package folder may be read-only). Returns its config folder.

    The example apps are refreshed on every call; the demo's JSON files are copied only when missing, so edits
    made on the admin page stay, and so do its logs and sessions.
    """
    target = Path(target) if target else platform_utils.user_data_dir() / "demo"
    for source in DEMO_DIR.iterdir():
        if source.is_dir() and source.name != "config":
            shutil.copytree(source, target / source.name, dirs_exist_ok=True, ignore=_RUNTIME)
    config = target / "config"
    config.mkdir(parents=True, exist_ok=True)
    for source in (DEMO_DIR / "config").glob("*.json"):
        if not (config / source.name).exists():
            shutil.copyfile(source, config / source.name)
    return config
