"""The `streamhub` command line: subcommands, the old no-subcommand form, and frozen-executable helpers."""
import sys

import pytest
from click.testing import CliRunner

from streamhub import __version__, cli, platform_utils


@pytest.fixture
def ran(monkeypatch):
    """Replace the hub with a recorder: `streamhub run` must reach app.run with the parsed options."""
    calls = []

    def fake_run(config, **options):
        calls.append((config, options))
        return 0

    monkeypatch.setattr("streamhub.app.run", fake_run)
    return calls


def test_run_subcommand(ran, tmp_path):
    result = CliRunner().invoke(cli.main, ["run", "--port", "9000", "--debug", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert ran == [(str(tmp_path), {"port": 9000, "ssl_port": 0, "debug": True, "supervised": False})]


@pytest.mark.parametrize("args", [["{dir}"], ["--port", "9000", "{dir}"], ["--supervised", "{dir}"]])
def test_no_subcommand_means_run(ran, tmp_path, args):
    """`streamhub <config>` from 2.0 (Docker CMD, systemd units) keeps working."""
    result = CliRunner().invoke(cli.main, [a.format(dir=tmp_path) for a in args])
    assert result.exit_code == 0, result.output
    assert ran[0][0] == str(tmp_path)


def test_debug_is_a_flag_not_a_value(ran, tmp_path):
    """`streamhub --debug <config>` must not read the config path as the value of --debug."""
    result = CliRunner().invoke(cli.main, ["--debug", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert ran == [(str(tmp_path), {"port": 0, "ssl_port": 0, "debug": True, "supervised": False})]


def test_run_defaults_to_current_folder(ran, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert CliRunner().invoke(cli.main, ["run"]).exit_code == 0
    assert ran[0][0] == "."


def test_run_rejects_a_missing_folder():
    result = CliRunner().invoke(cli.main, ["run", "no/such/folder"])
    assert result.exit_code == 1 and "No such folder" in result.output and "streamhub init" in result.output


def test_run_reads_the_config_from_the_environment(ran, tmp_path, monkeypatch):
    monkeypatch.setenv("STREAMHUB_CONFIG", str(tmp_path))
    assert CliRunner().invoke(cli.main, ["run"]).exit_code == 0
    assert ran[0][0] == str(tmp_path)


def test_init_writes_a_valid_starter(tmp_path):
    import json

    from streamhub import auth

    folder = tmp_path / "hub"
    result = CliRunner().invoke(cli.main, ["init", str(folder), "--yes", "--admin-password", "first-pw-1",
                                           "--site-title", "Team hub", "--port", "8600"])
    assert result.exit_code == 0, result.output
    assert json.loads((folder / "streamhub.json").read_text(encoding="utf-8")) == {"site-title": "Team hub",
                                                                                  "port": 8600}
    users = json.loads((folder / "streamhub-users.json").read_text(encoding="utf-8"))
    assert users["admin"]["role"] == "admin" and auth.verify_password(users["admin"]["password"], "first-pw-1")
    check = CliRunner().invoke(cli.main, ["check", str(folder)])
    assert check.exit_code == 0 and "0 error(s), 0 warning(s)" in check.output
    again = CliRunner().invoke(cli.main, ["init", str(folder), "--yes"])
    assert again.exit_code == 1 and "--force" in again.output  # never overwrites by accident
    short = CliRunner().invoke(cli.main, ["init", str(tmp_path / "other"), "--yes", "--admin-password", "short"])
    assert short.exit_code == 1 and not (tmp_path / "other").exists()


def test_init_prompts_for_what_it_needs(tmp_path):
    result = CliRunner().invoke(cli.main, ["init", str(tmp_path)], input="My hub\n8700\nboss\npass-word-1\npass-word-1\n")
    assert result.exit_code == 0, result.output
    assert "boss" in (tmp_path / "streamhub-users.json").read_text(encoding="utf-8")


def test_init_without_password_leaves_the_admin_to_the_setup_page(tmp_path):
    result = CliRunner().invoke(cli.main, ["init", str(tmp_path), "--yes"])
    assert result.exit_code == 0 and "setup link" in result.output
    assert not (tmp_path / "streamhub-users.json").exists()


def test_demo_copies_the_bundled_demo(ran, tmp_path, monkeypatch):
    monkeypatch.setenv("STREAMHUB_ADMIN_PASSWORD", "")  # so the value `demo` sets is undone afterwards
    monkeypatch.delenv("STREAMHUB_ADMIN_PASSWORD")
    result = CliRunner().invoke(cli.main, ["demo", "--folder", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "admin / admin" in result.output and ran[0][0] == str(tmp_path / "config")
    assert (tmp_path / "streamlit" / "main.py").is_file() and (tmp_path / "config" / "streamhub-apps.json").is_file()
    check = CliRunner().invoke(cli.main, ["check", str(tmp_path / "config")])
    assert check.exit_code == 0, check.output
    # The demo's JSON files survive a second run (admin-page edits stay); the apps are refreshed.
    (tmp_path / "config" / "streamhub-news.json").write_text("[]", encoding="utf-8")
    (tmp_path / "flask" / "main.py").write_text("", encoding="utf-8")
    assert CliRunner().invoke(cli.main, ["demo", "--folder", str(tmp_path)]).exit_code == 0
    assert (tmp_path / "config" / "streamhub-news.json").read_text(encoding="utf-8") == "[]"
    assert (tmp_path / "flask" / "main.py").read_text(encoding="utf-8") != ""


def test_config_error_is_a_clean_message(tmp_path):
    (tmp_path / "streamhub.json").write_text('{"port": "abc"}', encoding="utf-8")
    result = CliRunner().invoke(cli.main, ["run", str(tmp_path)])
    assert result.exit_code == 1 and "'port'" in result.output and "Traceback" not in result.output


def test_version_and_help():
    runner = CliRunner()
    assert runner.invoke(cli.main, ["version"]).output.strip() == f"Streamhub, version {__version__}"
    assert __version__ in runner.invoke(cli.main, ["--version"]).output
    listing = runner.invoke(cli.main, ["--help"]).output
    assert "run" in listing and "passwd" in listing and "follow-pod" not in listing  # internal command stays hidden


def test_passwd_subcommand_and_legacy_command():
    for command, args in ((cli.main, ["passwd", "s3cret"]), (cli.passwd, ["s3cret"])):
        result = CliRunner().invoke(command, args)
        assert result.exit_code == 0 and result.output.startswith("pbkdf2_sha256$")


def test_hash_passwords_command(tmp_path):
    import json

    from streamhub import auth

    users = tmp_path / "streamhub-users.json"
    users.write_text(json.dumps({"ann": {"password": "ann-pw", "role": "admin", "boards": ["*"]},
                                 "bob": {"password": auth.hash_password("bob-pw", 1000), "role": "user"}}),
                     encoding="utf-8")
    result = CliRunner().invoke(cli.main, ["hash-passwords", str(tmp_path)])  # a config folder
    assert result.exit_code == 0 and "1 user(s): ann" in result.output and "ann-pw" not in result.output
    data = json.loads(users.read_text(encoding="utf-8"))
    assert auth.verify_password(data["ann"]["password"], "ann-pw") and data["ann"]["role"] == "admin"
    assert "ann-pw" not in users.read_text(encoding="utf-8")
    again = CliRunner().invoke(cli.main, ["hash-passwords", str(users)])  # or the file itself
    assert again.exit_code == 0 and "already hashed" in again.output
    users.write_text("[1, 2]", encoding="utf-8")
    assert CliRunner().invoke(cli.main, ["hash-passwords", str(users)]).exit_code == 1


def test_version_has_a_single_source():
    import tomllib
    from pathlib import Path

    project = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8"))
    assert "version" not in project["project"] and "version" in project["project"]["dynamic"]
    assert project["tool"]["setuptools"]["dynamic"]["version"] == {"attr": "streamhub.__version__"}


def test_self_command_and_hub_python(monkeypatch):
    assert platform_utils.self_command() == [sys.executable, "-m", "streamhub"]
    assert platform_utils.hub_python() == sys.executable
    assert platform_utils.relaunch_env({}) == {}
    monkeypatch.setattr(platform_utils, "IS_FROZEN", True)
    assert platform_utils.self_command() == [sys.executable]
    assert platform_utils.relaunch_env({})["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
    monkeypatch.setattr(platform_utils.shutil, "which", lambda name: "/usr/bin/python3" if name == "python3" else None)
    assert platform_utils.hub_python() == "/usr/bin/python3"
    monkeypatch.setattr(platform_utils.shutil, "which", lambda name: f"/bin/{name}")
    assert platform_utils.hub_python() == ("/bin/python" if platform_utils.IS_WINDOWS else "/bin/python3")
    monkeypatch.setattr(platform_utils.shutil, "which", lambda name: None)
    with pytest.raises(LookupError):
        platform_utils.hub_python()
