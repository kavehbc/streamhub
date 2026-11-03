# Troubleshooting

Start with the app's log: `/out/<app_id>/`, or **Log** on the dashboard. The hub log (stderr) and `streamhub check <config>` explain most of the rest.

## Apps

| Symptom | Cause and fix |
|---|---|
| Error page *The app stopped (exit code N)* | Read the log tail on the page, or the full log at `/out/<app_id>/`. Typical causes: a missing package in the app's environment, a wrong `folder` or `file`, a syntax error. Refresh to start the app again. |
| *The app did not answer on … within N s* | The app doesn't answer on its health path or port. Check the log for an import error, a missing framework, the app listening on another port, or a wrong `health_path`. A slow app needs a larger `startup-timeout`. |
| *… listens on 0.0.0.0:N, which bypasses the hub's access control* | The app binds every interface. Make it listen on `STREAMHUB_HOST` (`127.0.0.1`). |
| An app keeps restarting, with *failed N health checks* in the log | Its `health_path` returns errors or takes more than 10 s. Fix the endpoint, or raise `health-failures`. |
| An app fails with a missing variable or credential | Apps don't inherit the hub's environment: add the variable to its `env_passthrough`. |
| *Could not start …: Conda environment not found* | Check `virtual_environment`. Services and containers often have no conda on PATH: use an environment folder, or `python_executable`. |
| Links or redirects of a Python app lose the `/<app_id>/` prefix | Handle the prefix: Flask `ProxyFix(x_prefix=1)`, FastAPI `root_path=os.environ["STREAMHUB_BASE_PATH"]`. See [Writing apps](../deployment/writing-apps.md#python-web-apps). |
| An upload fails, or the connection resets | The body is larger than `max-upload-mb`, or than the reverse proxy's limit (`client_max_body_size` in nginx). |
| A Streamlit app shows *connection error* behind a proxy | The reverse proxy doesn't forward WebSockets. See [HTTPS and reverse proxies](../deployment/https-and-proxies.md). |
| *docker was not found* / *kubectl was not found* | Install the CLI for the hub's user, or set `STREAMHUB_DOCKER` / `STREAMHUB_KUBECTL`. |
| A Kubernetes app is stuck on the loading page | `/out/<app_id>/` shows the pod's waiting reason, for example `ImagePullBackOff`. |
| Broken icons on the cards | The `icon` URL doesn't exist in the static folder. Check it on the Static files tab. |

## Access and sign-in

| Symptom | Cause and fix |
|---|---|
| 403 on an app | The user has none of the app's boards. Give the user the board, or put the app on a public board. |
| A new hub has no admin: the login page says so | Open the hub's address and enter the setup token the hub logged at startup (`Setup token: …`; in Docker, `docker logs <container>`). It is logged again, at most once a minute, when someone opens the login page. Or run `streamhub init <config>`, or set `STREAMHUB_ADMIN_PASSWORD`. |
| `/setup/` answers 404 | The hub already has an admin, uses OIDC or LDAP (their admins come from `group-mapping`), or its users file is invalid. |
| Everyone is logged out; `/admin/` says the users file is not in use | The users file is invalid, unreadable or was deleted. Fix it on disk; `streamhub check` names the problem. Meanwhile only the `STREAMHUB_ADMIN_PASSWORD` admin can log in. |
| A user can't log in after an upgrade | Their password is stored raw, and raw passwords are refused (the log names the user). Run `streamhub hash-passwords <config>`. |
| Logins rejected with 429 | Too many failed logins from that address: wait 5 minutes. Behind a reverse proxy, set `behind-proxy: true`, so clients are told apart. A 503 *Too many logins in progress* means more than 8 password checks queued for 10 s. |
| SSO login returns to the login page | The audit log names the reason: a state mismatch (cookies blocked, or more than 10 minutes on the provider's page), an issuer or audience mismatch, an invalid signature or unknown signing key, or no `group-mapping` rule (403). |
| The hub refuses to start: *oidc: the issuer must be https://* or *ldap: use ldaps://* | SSO requires TLS. Fix the URL; `insecure-http` and `allow-plaintext` are for development only. *PyJWT with cryptography* means the `oidc` extra is missing. |

## The hub

| Symptom | Cause and fix |
|---|---|
| *No such folder* on `streamhub run` | The config folder doesn't exist: create it with `streamhub init <folder>`, or try `streamhub demo`. |
| The hub refuses to start and names a key | That setting has a bad value: fix it, and run `streamhub check`. |
| An edit of `streamhub.json` on disk has no effect | Use **Reload configuration**, and restart for the keys it lists. |
| A banner on `/admin/` names a catalog file | That file is invalid; the hub keeps using the last good version of the apps and news files. |
| **Restart hub** stops the hub instead | Under a service manager, run with `--supervised` and restart on exit code 3. |
| With several instances, apps restart or sessions drop | The load balancer isn't sticky, or the instances have different cookie secrets. See [Multiple instances](../deployment/multiple-instances.md). |
| Uploaded icons disappeared after an upgrade | The static folder was the bundled one. Set `cdf` to a folder of your config ([Static files](../admin-guide/static-files.md)). |
| The report form says the report could not be delivered | No channel accepted it: check the notification settings, and the warnings in the hub log. |
