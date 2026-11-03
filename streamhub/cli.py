"""The `streamhub` command: `run`, `demo`, `init`, `passwd`, `check` and `version`, like `streamlit run`.

`streamhub <config>` (no subcommand) still means `streamhub run <config>`, and `streamhub-passwd` still works.
"""
import getpass
import logging
import os
import sys
from pathlib import Path

import click

from streamhub import __version__
from streamhub.auth import hash_password
from streamhub.config import ConfigError

CONTEXT = {"help_option_names": ["-h", "--help"]}
MIN_PASSWORD = 8


class _RunByDefault(click.Group):
    """A group whose unknown first argument (a path or a `run` option) is handed to `run`."""

    def parse_args(self, ctx, args):
        if args and args[0] not in self.commands and args[0] not in ("-h", "--help", "--version"):
            args = ["run", *args]
        return super().parse_args(ctx, args)


@click.group(cls=_RunByDefault, context_settings=CONTEXT)
@click.version_option(__version__, prog_name="Streamhub")
def main():
    """Streamhub: launch Streamlit and Python web apps on demand behind one port.

    \b
    streamhub demo                            try the bundled demo apps (login admin / admin)
    streamhub init <config folder>            create a starter config folder, with its admin account
    streamhub run <config folder>             run the hub
    streamhub passwd                          hash a password for the users file
    streamhub hash-passwords <config folder>  hash the raw passwords left in the users file
    streamhub check <config folder>           validate a config folder without starting it
    streamhub version                         print the version
    """


@main.command(context_settings=CONTEXT)
@click.option("--port", type=int, default=0, help="HTTP port (overrides 'port').")
@click.option("--ssl-port", "--ssl_port", "ssl_port", type=int, default=0, help="HTTPS port (overrides 'ssl_port').")
@click.option("--debug", is_flag=True, help="Verbose logs and tracebacks; notifications are disabled.")
@click.option("--supervised", is_flag=True, envvar="STREAMHUB_SUPERVISED",
              help="A service manager restarts the hub: /restart/ exits with code 3 instead of relaunching.")
@click.option("--log-level", default="INFO", show_default=True,
              type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False))
@click.argument("config", default=".", envvar="STREAMHUB_CONFIG")
def run(port, ssl_port, debug, supervised, log_level, config):
    """Run the hub. CONFIG is a folder holding streamhub.json (default: $STREAMHUB_CONFIG, else the current
    folder), or the file itself. A folder without streamhub.json runs on the defaults."""
    if not Path(config).exists():
        raise click.ClickException(f"No such folder: {config}\nCreate a config with `streamhub init {config}`, "
                                   "or try the demo with `streamhub demo`.")
    _serve(config, port, ssl_port, debug, supervised, log_level)


def _serve(config, port, ssl_port, debug, supervised, log_level):
    logging.basicConfig(level="DEBUG" if debug else log_level.upper(),
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    from streamhub.app import run as run_hub  # imported here so `passwd` and `version` start fast

    try:
        sys.exit(run_hub(config, port=port, ssl_port=ssl_port, debug=debug, supervised=supervised))
    except ConfigError as exc:
        raise click.ClickException(str(exc)) from exc


@main.command(context_settings=CONTEXT)
@click.option("--port", type=int, default=0, help="HTTP port (default: 8500).")
@click.option("--debug", is_flag=True, help="Verbose logs and tracebacks; notifications are disabled.")
@click.option("--folder", type=click.Path(file_okay=False), default=None,
              help="Where to keep the demo copy (default: a per-user data folder).")
def demo(port, debug, folder):
    """Run the bundled demo: a Streamlit, a Flask and a FastAPI app on a public board.

    The demo is copied to a writable folder first. Its admin login is admin / admin unless
    STREAMHUB_ADMIN_PASSWORD is set. The apps need: pip install "py-streamhub[examples]".
    """
    from streamhub import auth
    from streamhub.bootstrap import prepare_demo

    config = prepare_demo(folder)
    os.environ.setdefault("STREAMHUB_ADMIN_PASSWORD", auth.DEMO_ADMIN_PASSWORD)
    login = ("admin / admin" if auth.demo_password_in_use()
             else f"{os.environ.get('STREAMHUB_ADMIN_USER', 'admin')} and $STREAMHUB_ADMIN_PASSWORD")
    click.echo(f"Demo config: {config}\nOpen http://localhost:{port or 8500}/ and sign in as {login}.")
    _serve(str(config), port, 0, debug, False, "INFO")


@main.command(context_settings=CONTEXT)
@click.argument("folder", default=".", type=click.Path(file_okay=False))
@click.option("--site-title", default="Streamhub", show_default=True, help="Name shown on the landing page.")
@click.option("--port", type=int, default=8500, show_default=True, help="HTTP port of the hub.")
@click.option("--admin-user", default="admin", show_default=True, help="Name of the first admin account.")
@click.option("--admin-password", default=None,
              help="Password of the first admin. Asked when omitted; with --yes and no password, no account is "
                   "created and the hub prints a setup link instead.")
@click.option("--yes", "-y", is_flag=True, help="Don't ask: use the defaults and the options given.")
@click.option("--force", is_flag=True, help="Overwrite the starter files if they exist (other users are kept).")
def init(folder, site_title, port, admin_user, admin_password, yes, force):
    """Create a starter config folder: settings, one board, a news item and an admin account.

    FOLDER defaults to the current folder. Everything can be changed later on the admin page.
    """
    from streamhub.bootstrap import init_folder

    if not yes:
        site_title = click.prompt("Site title", default=site_title)
        port = click.prompt("HTTP port", default=port, type=int)
        admin_user = click.prompt("Admin user name", default=admin_user)
        if admin_password is None:
            admin_password = click.prompt(f"Admin password ({MIN_PASSWORD} characters or more)", hide_input=True,
                                          confirmation_prompt=True)
    if admin_password is not None and len(admin_password) < MIN_PASSWORD:
        raise click.ClickException(f"The admin password needs {MIN_PASSWORD} characters or more")
    try:
        written = init_folder(folder, site_title=site_title, port=port, admin_user=admin_user,
                              admin_password=admin_password, force=force)
    except FileExistsError as exc:
        raise click.ClickException(f"{folder} already has {exc}: use --force to overwrite") from exc
    for path in written:
        click.echo(f"wrote {path}")
    click.echo(f"\nNext: streamhub run {folder}\nThen open http://localhost:{port}/"
               + ("" if admin_password else " and follow the setup link the hub prints."))


@main.command(context_settings=CONTEXT)
@click.argument("password", required=False)
def passwd(password):
    """Print a password hash for streamhub-users.json (prompts when PASSWORD is omitted)."""
    if password is None:
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Repeat: "):
            raise click.ClickException("Passwords do not match")
    click.echo(hash_password(password))


@main.command("hash-passwords", context_settings=CONTEXT)
@click.argument("target", default=".", type=click.Path(exists=True))
def hash_passwords(target):
    """Replace raw passwords in the users file with hashes, in place.

    TARGET is a config folder (its users file is used) or the users file itself. Prints user names only.
    """
    import json
    import os
    from pathlib import Path

    from streamhub.auth import hash_users
    from streamhub.config import load_settings

    path = Path(target)
    if path.is_dir() or path.name == "streamhub.json":
        try:
            path = load_settings(path).users_file
        except ConfigError as exc:
            raise click.ClickException(str(exc)) from exc
    if not path.is_file():
        raise click.ClickException(f"No users file at {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise click.ClickException(f"{path}: invalid JSON ({exc})") from exc
    if not isinstance(data, dict):
        raise click.ClickException(f"{path}: expected a JSON object of users")
    changed = hash_users(data)
    if not changed:
        click.echo(f"{path}: every password is already hashed.")
        return
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)  # atomic: the file is never half written
    click.echo(f"{path}: hashed the passwords of {len(changed)} user(s): {', '.join(changed)}")


@main.command(context_settings=CONTEXT)
@click.argument("target", default=".", type=click.Path(exists=True))
def check(target):
    """Validate a config folder without starting anything. Exits with 1 on errors.

    TARGET is a config folder or its streamhub.json. Checks the settings, the apps, users and news files,
    file and tool references, and security-sensitive settings. Secret values are never printed.
    """
    from streamhub.validate import check as run_check

    logging.basicConfig(level="ERROR", format="%(levelname)s %(message)s")
    errors, warnings = run_check(target)
    for warning in warnings:
        click.echo(f"warning: {warning}")
    for error in errors:
        click.echo(f"error: {error}", err=True)
    click.echo(f"{target}: {len(errors)} error(s), {len(warnings)} warning(s)")
    sys.exit(1 if errors else 0)


@main.command()
def version():
    """Print the Streamhub version."""
    click.echo(f"Streamhub, version {__version__}")


@main.command("follow-pod", hidden=True)
@click.argument("kubectl")
@click.argument("namespace")
@click.argument("pod")
@click.argument("startup_timeout", type=int)
def follow_pod(kubectl, namespace, pod, startup_timeout):
    """Internal: the local process that stands for a Kubernetes app (see runtimes.follow_pod)."""
    from streamhub.runtimes import follow_pod as follow

    sys.exit(follow(kubectl, namespace, pod, startup_timeout))
