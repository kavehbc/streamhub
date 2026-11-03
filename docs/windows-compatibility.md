# Windows Compatibility

Since 2.0, one codebase runs on **Windows and Linux**. Every OS-specific branch lives in [platform_utils.py](../streamhub/platform_utils.py), and CI runs the test suite on both systems ([.github/workflows/ci.yml](../.github/workflows/ci.yml)). The suite was verified on Windows 11 (Python 3.13) and in the Linux container (Python 3.12). It covers launching Streamlit, Flask and FastAPI apps, WebSocket proxying, memory clean with no orphan processes left behind, port reuse, exit and restart.

## How the 1.x blockers were resolved

| ID | 1.x blocker | 2.0 solution |
|---|---|---|
| WIN-1 | `signal.SIGQUIT` crashed startup | `install_signal_handlers` registers whichever of SIGINT, SIGTERM, SIGQUIT and SIGBREAK exist, and forwards them with `loop.call_soon_threadsafe` |
| WIN-2 | Tornado 5 | Tornado ≥ 6.3 on asyncio's default Proactor loop, which also runs subprocesses |
| WIN-3 | `tornado.process.Subprocess` | `asyncio.create_subprocess_exec`, with exits detected by `await proc.wait()` |
| WIN-4 | `preexec_fn=os.setsid` | `new_group_kwargs()`: `CREATE_NEW_PROCESS_GROUP` on Windows, `start_new_session=True` on POSIX |
| WIN-5 | `shell=True` with `source activate` | Argument lists. `env_python()` resolves the env's interpreter directly (`<prefix>\python.exe` or `<prefix>/bin/python`); `activate: true` uses `conda run` |
| WIN-6 | `bash <file>` | `script_argv()` chooses by extension: bash, `cmd /c` or PowerShell. Alternatively use the `command` key. |
| WIN-7 | `os.killpg` | `process_tree()` and `signal_tree()` (psutil); asyncio reaps the root process |
| WIN-8, WIN-9 | `os.system("… &")`, bash relaunch | Auto-start and relaunch run in the hub process. Restart is exit code 3 under a service manager, or a `Popen` of the hub otherwise. |
| WIN-10 | `ss`, `kill`, `killall`, `cpu_num` in `status.cmd` | Since 2.1 the `/admin/` page uses `platform_utils` helpers: `listening_ports` (`psutil.net_connections`), `tree_stats`, `server_stats` (load is `n/a` where `getloadavg` is missing), and `cpu_affinity`, which returns `None` where the OS has no affinity API |
| WIN-11 | `/api/` JSON broke on `\` | Built from a dict |
| WIN-12 | Slow connect probes | A bind test, which is instant. Containers and pods, whose ports the hub doesn't own, use `port_accepts` (TCP connect) or their health path. |
| WIN-13 | Deleting temp files that are still in use | `clean_folder()` skips and logs files it can't delete |
| WIN-14 | `CONDA_DEFAULT_ENV` required | Not used. An empty env means the hub's interpreter. |
| WIN-15 | `export TZ` | `timezone` config key (`zoneinfo` + `tzdata`) |
| WIN-16 | Apps bound to `0.0.0.0` | Streamlit and the demo apps bind to `127.0.0.1` (see [SEC-12](known-issues.md#sec-12)) |
| WIN-17 | Line endings in shell scripts | [.gitattributes](../.gitattributes) keeps `*.sh` and `*.bash` as LF, and `*.bat`, `*.cmd` and `*.ps1` as CRLF |
| WIN-18 | "OS Independent" classifier | The classifiers now list POSIX/Linux and Windows |

Some details differ from the original plan:

- **Stopping:** it doesn't use `CTRL_BREAK_EVENT`. Aimed at a stale process-group ID, Windows delivers that event to every process on the console, including the hub, so Windows stops apps with `TerminateProcess`.
- **Port probe:** it sets `SO_EXCLUSIVEADDRUSE` on Windows and `SO_REUSEADDR` on POSIX. Without `SO_REUSEADDR`, Linux connections in TIME_WAIT make a free port look busy.

## Behavior differences

| Topic | Linux | Windows |
|---|---|---|
| Stopping an app | SIGTERM to the process tree, then SIGKILL after `stop-timeout` | `TerminateProcess` on the tree at once, with no graceful shutdown |
| Stopping the hub | SIGTERM / SIGINT | Ctrl+C / Ctrl+Break (what service managers send) |
| Deleting files that are in use | Allowed | Skipped until the next clean |
| Paths in JSON | `/srv/apps/x` | `C:/apps/x` or `C:\\apps\\x` |
| Launcher scripts | `.sh` / `.bash` | `.bat` / `.cmd` / `.ps1`. The `command` key works on both and is recommended. |
| Apps after a hub crash | Keep running until the hub starts again, which kills them (`kill_leftover`: the process tree, plus the rest of its process group, after checking the start time) | Killed with the hub: it runs in a Job Object with `KILL_ON_JOB_CLOSE` (`kill_children_with_hub`, through `ctypes`), which every child joins. Before relaunching itself, the hub clears that limit (`release_children`) so the new copy survives. The startup sweep also runs, for a hub that could not create the job. |
| App environment (`child_env`) | `PATH`, `HOME`, `USER`, `LOGNAME`, `SHELL`, `TERM`, `LD_LIBRARY_PATH`, `XDG_*`, locale, temp, proxies, CA bundles, `CONDA_*` | `PATH`, `SYSTEMROOT`, `WINDIR`, `COMSPEC`, `PATHEXT`, `USERPROFILE`, `APPDATA`, `LOCALAPPDATA`, `PROGRAMFILES*`, `TEMP`, … (names compare case-insensitively) |
| `bind-check` (`exposed_listeners`) | psutil reads the app's sockets (own user) | Same, through the TCP tables |
| `docker` runtime | `docker` CLI on PATH (`STREAMHUB_DOCKER` otherwise); default daemon `unix:///var/run/docker.sock` | Same with Docker Desktop (`docker.exe`); default daemon `npipe:////./pipe/docker_engine`, so a `docker-socket` there must be an `npipe://` URL (a bare path becomes `unix://`). Images must match the daemon's OS (Linux containers by default). |
| Per-user data folder (`user_data_dir`, where `streamhub demo` copies the demo) | `$XDG_DATA_HOME/streamhub`, default `~/.local/share/streamhub` | `%LOCALAPPDATA%\streamhub` |
| Container ID for the setup page's `docker logs` hint (`container_name`) | The host name, when `/.dockerenv` or `/run/.containerenv` exists | `""` (the page points at the console instead) |
| Environment suggestions on the admin page (`conda_envs`) | `conda env list --json` when conda is on PATH (or `CONDA_EXE`) | Same |
| `kubernetes` runtime | Hub runs in the cluster; `kubectl` on PATH | Not practical: the hub must run inside the cluster to reach Service names |
| [Executable](operations.md#build) | `streamhub`, built on Linux; default app interpreter `python3`, then `python` | `streamhub.exe`, built on Windows; default app interpreter `python`, then `python3` (`python3` is often the Microsoft Store stub). Conda builds need the env's `Library\bin` on PATH, which the spec adds. |

## Deploying on Windows

1. **Install** Python 3.11+ (or Miniconda), then from the repo run `pip install -e ".[tools]"`.
2. **Configure:** set `"virtual-environment"` to an env name or folder, or give each app a `python_executable`. A service usually runs without conda on PATH, so environment **folders** are the safest choice.
3. **Run it as a service.** With [NSSM](https://nssm.cc/):
   ```powershell
   nssm install Streamhub "C:\Python312\Scripts\streamhub.exe" "run --supervised C:\streamhub-config"
   nssm set Streamhub AppExit 3 Restart          # /restart/ → restart
   nssm set Streamhub AppExit 0 Exit             # /exit/ → stay stopped
   nssm set Streamhub AppStdout C:\streamhub-config\logs\streamhub.log
   nssm set Streamhub AppStderr C:\streamhub-config\logs\streamhub.log
   nssm start Streamhub
   ```
   For a manual run instead, use `make.bat start` ([make.bat](../make.bat); set `CONFIG` to the config folder).
4. **Firewall:** open only the hub's port. Apps listen on `127.0.0.1`, so Windows shows no firewall prompts for them.
5. **TLS:** put IIS (ARR), Caddy or nginx in front of the hub, and set `"behind-proxy": true`.
6. **Account:** run the service as a dedicated low-privilege user with read access to the app folders and environments.
