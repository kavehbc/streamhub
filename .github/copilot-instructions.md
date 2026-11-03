# GitHub Copilot instructions

Streamhub is a Tornado reverse proxy that launches Streamlit and Python web apps on demand and serves them under one port, on Linux and Windows. Start with [docs/README.md](../docs/README.md). Architecture, configuration, operations, Windows support, known issues and the roadmap are all under `docs/`.

## Working on the code

- Tasks are in the `Makefile` and `make.bat` (same target names; `make help`).
- Install: `make install` (`pip install -e ".[tools,examples,dev]"`).
- Run the demo: `make demo` (`python -m streamhub demo --debug`, login `admin` / `admin`). Or use Docker: `make docker-up`, (the first start logs a setup link, unless `.env` sets `STREAMHUB_ADMIN_PASSWORD`).
- `config/` is the (git-ignored) deployment config; the demo is `streamhub/demo/`, the `streamhub init` starter `streamhub/starter/`.
- **Test before finishing:** `make test` (`python -m pytest -q`). The integration tests start a real hub and the example apps, and `tests/test_docs.py` checks every relative link and anchor in the docs.
- Keep the code cross-platform. Put every OS-specific call (processes, signals, sockets, interpreters, shells) in `streamhub/platform_utils.py`. Never use `shell=True`, and always pass an `encoding` when opening text files.
- Never commit secrets (Slack hooks, passwords, keys, cookie secrets). Secrets come from environment variables. See SEC-3 in [docs/known-issues.md](../docs/known-issues.md).

## Keeping documentation in sync

**Every code change must update the matching docs in the same change.** Before finishing a task, go through the table below and edit each doc that matches.

| If you change... | Update |
|---|---|
| Routes in `streamhub/app.py`, or add/remove/rename a handler | `docs/architecture.md` (Request routing, Module reference), `docs/operations.md` (Endpoints and access) |
| `streamhub/auth.py`, roles, login, cookies, `can_access_app` | `docs/architecture.md` (Access control), `docs/operations.md` (Endpoints and access), `docs/configuration.md` (Users file roles) |
| `streamhub/config.py`, `streamhub/catalog.py`, any JSON key or default, environment variables | `docs/configuration.md` |
| `streamhub/launcher.py`, `runtimes.py`, `proxy.py`, `ports.py`, `scheduler.py`, health checks, memory clean, shutdown | `docs/architecture.md` (App lifecycle, Proxy, Hub lifecycle), `docs/operations.md` |
| `streamhub/platform_utils.py`, or any platform-specific behavior | `docs/windows-compatibility.md` |
| `streamhub/tools/` (help.cmd), `handlers/admin_page.py` (`/admin/`), `handlers/setup.py` (`/setup/`) | `docs/operations.md` (Endpoints and access) |
| `pyproject.toml`, `streamhub/cli.py`, `Dockerfile`, `docker-compose.yml`, `Makefile`, `make.bat`, `config/` layout, `deploy/` (including the PyInstaller spec), CI | `docs/operations.md` (Install, Run, Docker, Services) |
| App contract (flags, env vars, headers passed to apps), `streamhub/demo/` | `docs/operations.md` (Deploying an app), root `README.md` (Writing apps) |
| Templates or UI | `docs/architecture.md` (templates row) when the structure changes |
| User-visible behavior or a release | Root `README.md` (user guide and **Changelog**), `version` in `pyproject.toml` and `streamhub/__init__.py` |
| Anything users or admins see: settings, app keys, CLI, endpoints, screens, install or deployment steps | The matching pages of the documentation site in `readthedocs/` ([development/documentation.md](../readthedocs/development/documentation.md)). After a UI change, retake the screenshots it affects: `python readthedocs/_tools/screenshots.py <names>` |

### Issues and roadmap

Issue IDs (`SEC-n`, `BUG-n`, `COMPAT-n`, `QUAL-n`, `WIN-n`) are **permanent**.

- **Never renumber or reuse an ID**, because other docs link to them by anchor. `known-issues.md` lists only open issues, so it records the highest ID used so far in each category: update that line when you add an issue.
- **When you fix an issue:**
  - delete its section and its ID from the severity table in `known-issues.md` (the file holds open issues only);
  - describe the fix in the **Changelog** of the root `README.md`;
  - remove the matching items from `docs/roadmap.md` and `docs/recommendations.md` (which holds only recommendations not implemented yet);
  - remove links and references to its ID from the other docs and from code comments, and update any troubleshooting row in `operations.md` that mentions it.
- **When you fix it only partly,** edit the issue text to describe what is still broken.
- **When you find a new defect,** even if you don't fix it, add it under `## Open` with the next free ID in its category, add it to the severity table, and link to the code.
- **When you implement a roadmap feature or a recommendation,** remove it from `roadmap.md` and `recommendations.md`, and document it where it belongs (configuration, operations, architecture).

### Writing rules

- **Say each fact once.** Each fact belongs in exactly one doc; elsewhere, link to it (for example, from a doc, `[SEC-12](known-issues.md#sec-12)`). Don't copy issue descriptions into the roadmap or the guides.
- Keep the docs short: tables and bullets, no filler.
- Link to code with relative paths, and add line anchors only where they help, such as `[proxy.py:32](../streamhub/proxy.py#L32)` from a doc. **When you edit a file, grep `docs/` for its name and fix any line anchors you shifted.**
- Document what the code does, not what it is meant to do. If the two differ, document the code and file an issue.
- The root `README.md` is the end-user guide (`help.cmd` renders it). `docs/` is for maintainers. Don't duplicate between them beyond a link.

### Check before finishing

```bash
make test            # includes tests/test_docs.py: every relative link and #anchor in the docs must resolve
make docs            # the readthedocs/ site builds with warnings as errors
# line anchors pointing into files you touched still need a manual look
grep -n '<changed-file-name>' docs/*.md
```
