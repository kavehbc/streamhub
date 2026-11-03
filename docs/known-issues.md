# Known Issues

Defects that are still present. Each issue has a permanent ID that [roadmap.md](roadmap.md) and [recommendations.md](recommendations.md) refer to. Severity reflects the impact on a shared, network-reachable deployment. A fixed issue is removed from this file and its fix is listed in the changelog of the root [README.md](../README.md#changelog).

IDs are never reused. The highest ID used so far in each category, including fixed issues: **SEC-22, BUG-23, COMPAT-5, QUAL-9, WIN-18**.

| Severity | Open IDs |
|---|---|
| High | SEC-3 |
| Medium | SEC-12, SEC-15, SEC-21 |
| Low | SEC-20, SEC-22, COMPAT-5, QUAL-6, QUAL-9 |

---

## Open

### SEC-3
**Leaked secrets are still in git history.** 2.0 removed the Slack webhook, the master password and the TLS private keys from the working tree, and the cookie secret is no longer a constant. The old commits still contain all of them.

**Recommended fix:** Revoke or rotate every exposed credential and regenerate certificates made from exposed keys. Coordinate with repository owners before rewriting history with `git filter-repo`; remove the affected history from remotes and coordinate cleanup of forks and clones. Rotation is necessary even after history is rewritten.

### SEC-12
**Internal app ports can be reached directly when an app binds every interface.** Streamlit apps are started with `--server.address=127.0.0.1`, and the demo apps bind to `127.0.0.1`. The hub can't enforce this for `.py` apps or `bash_file` scripts. Since 2.2, `bind-check` ([launcher.py](../streamhub/launcher.py), `_bind_ok`) reports a `process` app that listens on a non-loopback address once it is ready, or stops it with `"refuse"`. The check runs once, at readiness: a port opened later, or a listener in another process, is not seen, and an app on loopback is still reachable by other local users and processes.

**Recommended fix:** Run apps in isolated network namespaces or containers and permit upstream access only from the hub, including for Kubernetes services. Enforce network policy or host firewall rules independently of the app's bind address.

### SEC-15
**Process apps run as the hub's OS user.** Since 2.2, apps no longer inherit the hub's environment ([platform_utils.py](../streamhub/platform_utils.py), `child_env`), so hub secrets reach an app only through `env-passthrough` or its `env`. An app still runs as the same OS user as the hub, so it can read the hub's files (the cookie secret file, the users file, the session database), its process memory, and on Linux `/proc/<hub pid>/environ`, which keeps the environment the hub started with.

**Recommended fix:** Run less-trusted apps under separate OS identities (or in containers) with no access to the config folder, as proposed by the app isolation profiles in [roadmap.md](roadmap.md).

### SEC-20
**Kubernetes app variables are stored in the Pod spec.** [kubernetes_manifest](../streamhub/runtimes.py) writes the app's variables as plain `env` values, including `STREAMHUB_APP_KEY` (which verifies `X-Streamhub-Identity`, [operations.md](operations.md#deploying-an-app)) and any `env-passthrough` values. Anyone who can read Pods in the namespace can read them.

**Recommended fix:** Put the values in a per-app Kubernetes Secret owned by the hub and reference it with `valueFrom.secretKeyRef`, and delete it with the Pod.

### SEC-21
**Hub admins control the host's Docker daemon.** The Compose file mounts `/var/run/docker.sock` ([docker-compose.yml](../docker-compose.yml)), and the Docker tab ([docker_admin.py](../streamhub/handlers/docker_admin.py)) and docker apps ([runtimes.py](../streamhub/runtimes.py), `DockerRuntime`) use it. Access to the daemon gives root on its host: an admin, or anyone who takes over an admin session, can start a privileged container or mount the host's files with `runtime_args`.

**Recommended fix:** Give the hub a restricted daemon: a socket proxy that allows only the calls the hub makes (containers with the `streamhub.*` labels, images, logs), or rootless Docker. Reject `runtime_args` such as `--privileged`, `-v /:/…` and `--pid=host` unless an allow-list in the config permits them.

### SEC-22
**Static files are served from the hub's origin.** The Static files tab ([cdf_admin.py](../streamhub/handlers/cdf_admin.py)) uploads any file type, and `/cdf/` serves it as is. An HTML or SVG file can run scripts with the hub's origin, so a page uploaded by an admin can act as any user who opens it: read other hub pages and send requests with their session.

**Recommended fix:** Serve `/cdf/` with `Content-Security-Policy: sandbox` and `X-Content-Type-Options: nosniff`, or from a separate origin; or refuse active content types on upload.

### COMPAT-5
**Streamlit's own `st.login` doesn't work behind the hub.** Streamlit reads its auth cookie only when XSRF protection is on and the WebSocket carries an `Origin` header. The hub starts Streamlit with `--server.enableXsrfProtection=false` ([runtimes.py](../streamhub/runtimes.py), `streamlit_flags`) and drops `Origin` from proxied WebSockets ([proxy.py](../streamhub/proxy.py), `WS_HANDSHAKE`). Since 2.2, `streamlit-user-headers` fills `st.user` with the hub's user instead (`name`, `role`), through Streamlit's experimental `server.trustedUserHeaders`. It is off by default, because Streamlit releases without that option refuse to start with it (verified with Streamlit 1.66).

**Recommended fix:** If Streamlit's own login must be supported, address XSRF and WebSocket origin handling without weakening protection, and verify the flow end to end.

### QUAL-6
**Employer data remains in the git history.** Since 2.3 the repository tracks no deployment config: `config/` is git-ignored, the company logos and product photos are gone from [cdf/](../streamhub/cdf/), and the demo and the [starter config](../streamhub/starter/) are neutral. Earlier commits still hold the old `config/` files (internal hostnames, a public IP, an AWS console alias, employee names and emails) and the removed images.

**Recommended fix:** Before publishing, decide with the data owner whether to rewrite the history (together with [SEC-3](#sec-3)) or publish from a fresh history.

### QUAL-9
**The bundled icons have no recorded origin or licence.** The images in [cdf/icons/](../streamhub/cdf/icons/) ship in the package and are offered by the admin page's icon picker, but nothing records where they come from or under which licence (two file names look like Noun Project downloads).

**Recommended fix:** Record the source and licence of each icon, or replace the set with icons under a known licence (or drawn for Streamhub, like [static/brand/](../streamhub/static/brand/)).
