# Building from source

## Set up

```bash
git clone https://github.com/kavehbc/streamhub
cd streamhub
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
make install                                     # Windows: make.bat install
```

`make install` runs `pip install -e ".[tools,examples,dev]"`: the hub in editable mode, the demo apps' frameworks and the test tools. `make install-ldap` adds LDAP and `make install-build` the build tools.

## Tasks

The `Makefile` (Linux, macOS, Git Bash) and `make.bat` (Windows cmd or PowerShell) have the same targets. `make help` lists them.

| Target | Runs |
|---|---|
| `install`, `install-ldap`, `install-build` | `pip install -e ".[tools,examples,dev]"`, plus `ldap` or the `build` tools |
| `test` | `pytest -q`: unit, handler, integration and documentation-link tests |
| `demo` | `streamhub demo --debug` |
| `start` | The hub on `CONFIG` (default `config`), with its output appended to `logs/streamhub.log` |
| `check` | `streamhub check` on `CONFIG` |
| `passwd` | `streamhub passwd` |
| `dist`, `exe` | The wheel and sdist, or the single-file executable |
| `docker-build`, `docker-up`, `docker-down`, `docker-logs` | The Docker image (tagged `kavehbc/streamhub:<version>` and `:latest`) and the Compose stack |
| `k8s-image` | `streamhub-kubectl:<version>`: the hub image with `kubectl` |
| `docs` | This documentation site, in `readthedocs/_build/html` |
| `clean` | Caches and build output |

Override variables on the command line, for example `make start CONFIG=/etc/streamhub ARGS=--supervised PYTHON=python3.12`. With `make.bat`, set `PYTHON`, `CONFIG`, `IMAGE_NAME`, `IMAGE` and `LATEST` as environment variables, and pass extra options after the target.

## Tests

```bash
make test          # python -m pytest -q
```

The integration tests start a real hub and the demo apps; they are skipped when Streamlit isn't installed. `tests/test_docs.py` checks every relative link and anchor of the Markdown docs. CI runs the suite on Linux and Windows with Python 3.11, 3.12 and 3.13, plus a run against the minimum dependency versions (`deploy/constraints-minimum.txt`), `pip-audit`, a wheel build, and a Docker build with a health check. It runs on pushes and pull requests to `main` or `master`; see [Releases](#releases) for what a push publishes.

## Wheel and sdist

```bash
make install-build
make dist           # python -m build → dist/py_streamhub-<version>-py3-none-any.whl and .tar.gz
pipx install "dist/py_streamhub-<version>-py3-none-any.whl[tools]"
```

The wheel bundles the templates, static files, the starter config and the demo apps.

## Single-file executable

```bash
make install-build
make exe            # PyInstaller → dist/streamhub (streamhub.exe on Windows), about 10 MB
./dist/streamhub run my-hub
```

The executable is built from `deploy/pyinstaller/streamhub.spec`, and bundles the templates, static files, the starter config, the demo apps, the Help page and the README.

- **Build once per OS.** PyInstaller doesn't cross-compile: build on Linux for Linux (preferably on the oldest glibc you deploy to), and on Windows for Windows.
- **Conda Pythons work.** The spec adds the environment's `Library\bin` to PATH so DLLs such as libffi are found.
- **It has no Python for the apps.** Apps without `virtual_environment` or `python_executable` run with `python` from PATH (`python3` first on Linux), so set `virtual-environment`. The Help page needs Streamlit in that Python.
- **Restart hub** relaunches the executable itself.

## Docker images

```bash
make docker-build                 # kavehbc/streamhub:<version> and :latest
make k8s-image                    # streamhub-kubectl:<version>, for Kubernetes apps
```

## The version

The version is set in one place, `streamhub/__init__.py` (`__version__`). The package metadata, `streamhub --version`, the admin page and this documentation read it from there.

## Releases

A push to `main` or `master` whose CI passes publishes release `v<version>`, unless it exists already, so bump `__version__` to release:

- the image `ghcr.io/kavehbc/streamhub:<version>` and `:latest`;
- a GitHub release (and tag) with the wheel, the sdist, and `streamhub-<version>-docker-image.tar.gz` for `docker load -i`. The release notes are the README changelog section of that version.

The first push of the image creates a private package on GitHub: make it public under the package's settings.

## Code layout

```text
streamhub/            The package
  app.py              Hub: routes, startup, memory clean, reload, shutdown
  config.py           Typed settings from streamhub.json and the environment
  catalog.py          Apps, boards, users, news (cached JSON)
  launcher.py         Start, watch, health-check and stop apps
  runtimes.py         Process, Docker and Kubernetes runtimes
  proxy.py            HTTP and WebSocket reverse proxy
  platform_utils.py   Everything that differs between Linux and Windows
  auth.py, sessions.py, usage.py, validate.py, ports.py, scheduler.py, notify.py, cli.py, bootstrap.py
  handlers/           Tornado request handlers (pages, login, SSO, setup, apps, admin API, admin page)
  templates/          HTML templates
  static/             Stylesheet, admin editors, logo, bundled Bootstrap and Font Awesome
  cdf/                Bundled static files served at /cdf/
  demo/  starter/     The demo of `streamhub demo`; the starter config of `streamhub init`
tests/                pytest suite
deploy/               systemd unit, Kubernetes and load-balancer examples, PyInstaller spec
docs/                 Maintainer documentation (architecture, known issues, roadmap)
readthedocs/          This documentation site
```

## Contributing

- Keep the code cross-platform: every OS-specific call (processes, signals, sockets, interpreters, shells) goes in `streamhub/platform_utils.py`. Never use `shell=True`, and always pass an `encoding` when opening text files.
- Never commit secrets; they come from environment variables.
- Update the documentation in the same change: the maintainer docs in `docs/`, and the matching pages of this site ([Documentation](documentation.md)).
- Run `make test` before you open a pull request.
