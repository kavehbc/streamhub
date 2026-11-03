# Windows

The same code runs on Windows and Linux; CI tests both. This page covers what differs on Windows and how to run the hub as a service.

## Install

1. Install Python 3.11+ or Miniconda.
2. `pip install "streamhub[tools] @ git+https://github.com/kavehbc/streamhub"`, or from a clone, `pip install -e ".[tools]"` (or `make.bat install`).
3. Create a config: `streamhub init C:\streamhub-config`.
4. Set `"virtual-environment"` to an env name or, better for a service, an environment **folder** such as `C:/conda/envs/apps`. Or give each app a `python_executable`.

Paths in JSON can be written `C:/apps/x` or `C:\\apps\\x`.

## Run as a service with NSSM

[NSSM](https://nssm.cc/) runs any program as a Windows service:

```powershell
nssm install Streamhub "C:\Python312\Scripts\streamhub.exe" "run --supervised C:\streamhub-config"
nssm set Streamhub AppExit 3 Restart          # Restart hub → restart the service
nssm set Streamhub AppExit 0 Exit             # Stop hub → stay stopped
nssm set Streamhub AppStdout C:\streamhub-config\logs\streamhub.log
nssm set Streamhub AppStderr C:\streamhub-config\logs\streamhub.log
nssm set Streamhub AppEnvironmentExtra STREAMHUB_COOKIE_SECRET=a-long-random-string
nssm start Streamhub
```

Run the service as a dedicated low-privilege user with read access to the app folders and environments. For a manual run, `make.bat start` runs the `config` folder (set `CONFIG` to another one) and appends the output to `logs\streamhub.log`.

## TLS and firewall

- Put IIS (with ARR), Caddy or nginx in front of the hub for HTTPS, and set `"behind-proxy": true`. See [HTTPS and reverse proxies](https-and-proxies.md).
- Open only the hub's port. Apps listen on `127.0.0.1`, so Windows shows no firewall prompts for them.

## Differences from Linux

| Topic | Linux | Windows |
|---|---|---|
| Stopping an app | SIGTERM to the process tree, then SIGKILL after `stop-timeout` | `TerminateProcess` on the tree at once, with no graceful shutdown |
| Stopping the hub | SIGTERM, SIGINT | Ctrl+C, Ctrl+Break (what service managers send) |
| Files in use | Deleted by a memory clean | Skipped until the next clean |
| Launcher scripts | `.sh`, `.bash` | `.bat`, `.cmd`, `.ps1`. The `command` key works on both and is recommended. |
| Apps after a hub crash | Keep running until the hub starts again, which stops them | Stop with the hub: it runs in a Job Object that kills its children |
| Load average on the dashboard | Shown | `n/a` |
| Demo copy | `~/.local/share/streamhub/demo` | `%LOCALAPPDATA%\streamhub\demo` |
| Docker apps | Default daemon `unix:///var/run/docker.sock` | Docker Desktop, default daemon `npipe:////./pipe/docker_engine`; a `docker-socket` must be an `npipe://` URL |
| Kubernetes apps | Supported, with the hub in the cluster | Not practical: the hub must run inside the cluster |
| Executable | `streamhub`; apps default to `python3`, then `python` | `streamhub.exe`; apps default to `python`, then `python3` (often the Microsoft Store stub) |

## Tasks with make.bat

`make.bat` has the same targets as the Makefile: `make.bat install`, `make.bat test`, `make.bat demo`, `make.bat start`, `make.bat docs`… Set variables as environment variables, and pass extra options after the target:

```bat
set CONFIG=C:\streamhub-config
make.bat start --supervised
```
