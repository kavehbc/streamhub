# Command line

Installing Streamhub adds the `streamhub` command. `python -m streamhub …` and, in a clone, `python main.py …` do the same.

| Command | Does |
|---|---|
| `streamhub demo` | Runs the bundled demo apps (login `admin` / `admin`) |
| `streamhub init [FOLDER]` | Writes a starter config folder with its admin account |
| `streamhub run [CONFIG]` | Runs the hub on a config folder, or on its `streamhub.json` |
| `streamhub check [CONFIG]` | Validates a config folder without starting anything; exits with 1 on errors |
| `streamhub passwd [PASSWORD]` | Prints a password hash for the users file |
| `streamhub hash-passwords [CONFIG]` | Replaces the raw passwords left in the users file with hashes, in place |
| `streamhub version` | Prints the version (also `streamhub --version`) |

Shortcuts kept for older scripts: `streamhub [options] CONFIG` without `run` (the 2.0 form), and the `streamhub-passwd` command.

## Examples

```bash
streamhub run                                  # $STREAMHUB_CONFIG, else the current folder
streamhub run /etc/streamhub --port 80         # another port, kept across reloads
streamhub run --supervised /etc/streamhub      # under systemd, NSSM or Docker
streamhub run --debug my-hub                   # debug logs and tracebacks; notifications off
streamhub init my-hub --yes --admin-password "$ADMIN_PASSWORD"
streamhub check my-hub && echo valid
streamhub passwd                               # prompts twice, prints pbkdf2_sha256$600000$…
streamhub demo --port 8600 --folder ./demo
```

## Exit codes of `run`

| Code | Meaning |
|---|---|
| 0 | Stopped (**Stop hub**, Ctrl+C, SIGTERM) |
| 3 | **Restart hub** in `--supervised` mode: the service manager should start the hub again |
| 1 | A configuration error, printed with the key that caused it |

## Full reference

```{click} streamhub.cli:main
:prog: streamhub
:nested: full
```
