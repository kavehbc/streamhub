# Installation

Streamhub needs **Python 3.11 or later** on Linux or Windows, unless you use the [Docker image](#docker) or the [single-file executable](#single-file-executable). Installing it adds the `streamhub` command.

## Choose a method

::::{tab-set}

:::{tab-item} pip (from PyPI)
The package is [py-streamhub](https://pypi.org/project/py-streamhub/) on PyPI; the command it installs is `streamhub`.

```bash
pip install "py-streamhub[tools,examples]"
streamhub version
```

The latest commit from GitHub: `pip install "py-streamhub[tools,examples] @ git+https://github.com/kavehbc/streamhub"`.
:::

:::{tab-item} pipx (isolated tool)
Download the wheel from a [GitHub release](https://github.com/kavehbc/streamhub/releases), or build one ([Building](../development/building.md#wheel-and-sdist)), then:

```bash
pipx install "dist/py_streamhub-<version>-py3-none-any.whl[tools]"   # or: pip install "<wheel>[tools]"
```
:::

:::{tab-item} From a clone
```bash
git clone https://github.com/kavehbc/streamhub
cd streamhub
pip install -e ".[tools,examples]"
```

For development, `make install` (Windows: `make.bat install`) also installs the test tools.
:::

:::{tab-item} conda
```bash
git clone https://github.com/kavehbc/streamhub
cd streamhub
conda env create -f environment.yml
```
:::

:::{tab-item} Docker
```bash
docker run -p 8500:8500 -v streamhub-config:/config kavehbc/streamhub
```
See [Docker](#docker) below and the [Docker deployment guide](../deployment/docker.md).
:::
::::

## Optional extras

The package is small: its own dependencies are only Tornado, Click and psutil (plus `tzdata` on Windows). Extras add the rest:

| Extra | Adds | Needed for |
|---|---|---|
| `tools` | Streamlit | The built-in **Help** page (`help.cmd`), which runs with the hub's own Python |
| `examples` | Streamlit, Flask, FastAPI, uvicorn | The demo apps of `streamhub demo` |
| `oidc` | PyJWT with cryptography | OpenID Connect sign-in. The hub refuses to start with `oidc` configured but PyJWT missing. |
| `ldap` | ldap3 | LDAP sign-in |
| `build` | build, PyInstaller | Building the wheel and the executable |
| `dev` | pytest, requests, PyJWT | Running the test suite |

Combine them as needed: `pip install "py-streamhub[tools,oidc,ldap]"`.

```{note}
The hub and its apps don't have to share a Python environment. Each app runs in the environment it names (a conda env name or an environment folder). An app's environment needs its own framework, for example `streamlit` for a Streamlit app. See [Apps file](../configuration/apps.md#launching-a-process-app).
```

## Docker

The image [`kavehbc/streamhub`](https://hub.docker.com/r/kavehbc/streamhub) on Docker Hub (`make docker-build` builds it; each release also publishes it as `ghcr.io/kavehbc/streamhub:<version>`) has the `tools`, `examples` and `oidc` extras and the `docker` client. It runs as a non-root user (uid 1000) in supervised mode and keeps its configuration in the `/config` volume.

```bash
docker run -p 8500:8500 -v streamhub-config:/config kavehbc/streamhub   # your hub: open it and follow the setup page
docker run -p 8500:8500 kavehbc/streamhub streamhub demo                # the demo, login admin / admin
```

With Docker Compose, from a clone:

```bash
cp .env.example .env          # optional: STREAMHUB_ADMIN_PASSWORD, STREAMHUB_COOKIE_SECRET, DOCKER_GID…
docker compose up -d --build  # or: make docker-up
docker compose logs streamhub # the first start prints the setup token
```

The [Docker deployment guide](../deployment/docker.md) covers the volume, permissions, the Docker socket and Docker apps.

## Single-file executable

`make exe` builds `dist/streamhub` (`streamhub.exe` on Windows) with PyInstaller. It is a single file of about 10 MB that needs no Python install to run the hub. Build it on each operating system you deploy to; see [Building](../development/building.md#single-file-executable). Apps still need a Python: set `virtual-environment`, or the executable runs apps with `python` from PATH.

## Check the installation

```console
$ streamhub version
Streamhub, version 2.3.0
$ streamhub --help
```

Next: [Quick start](quickstart.md).
