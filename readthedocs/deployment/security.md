# Security

## What the hub protects

- **Access control on the apps themselves.** A protected board hides its apps, and it refuses their launch, proxy, status and log requests to users without the board.
- **Passwords** are PBKDF2 hashes (600,000 iterations); raw passwords are refused. At most 8 password checks run at once, and a client gets HTTP 429 after 10 failed logins in 5 minutes.
- **Sessions** are signed, HttpOnly, SameSite=Lax cookies (Secure over HTTPS), with a server-side record that admins can revoke on every instance.
- **XSRF tokens** protect every form and admin API call.
- **Secrets** come from environment variables, and apps don't inherit the hub's environment.
- **Single sign-on** requires TLS: OIDC verifies the issuer and the ID-token signature; LDAP verifies certificates and never sends credentials after a failed STARTTLS.
- **Setup** of a new hub needs a one-time token from the hub's console.

## What it doesn't isolate

- **Browser origin.** Every app is served from the hub's origin, under its own path. A path prefix is not a security boundary: a page of one app can send requests to another app, or to hub pages, with the user's cookies. The hub's cookies are HttpOnly and stripped before proxying, and hub POSTs need the XSRF token, but a malicious app can still act as its visitors toward other apps. **Put untrusted apps on their own hub.**
- **OS identity.** Process apps run as the hub's OS user, so they can read the config folder (users file, cookie secret, session database). Containers and pods don't share the hub's files. Run apps you don't fully trust as `docker` or `kubernetes` apps.
- **Network.** The hub's access control applies only to requests that go through it. Firewall the internal port range, and keep `bind-check` on (or set it to `refuse`).
- **Identity headers.** `X-Streamhub-User` and `X-Streamhub-Role` are trustworthy only for requests that came through the hub. Apps that can be reached otherwise should verify `X-Streamhub-Identity` with their `STREAMHUB_APP_KEY`.
- **The Docker daemon.** Admins who reach the Docker tab or define Docker apps control the daemon, and so its host.
- **Static files.** Files uploaded to `cdf` or written to `temp` are served from the hub's origin, including HTML and SVG.

The repository's [known issues](https://github.com/kavehbc/streamhub/blob/main/docs/known-issues.md) list the open security findings.

## Hardening checklist

- [ ] HTTPS everywhere; `behind-proxy` behind a reverse proxy.
- [ ] `STREAMHUB_COOKIE_SECRET` set, and the same on every instance.
- [ ] No secrets in the JSON files: `streamhub check` warns about secrets in `streamhub.json`.
- [ ] No demo password: the dashboard and `streamhub check` warn while `admin` / `admin` works.
- [ ] Few admins. Give operators the `manager` role: they can start, stop and monitor apps without editing anything.
- [ ] `sso-session-minutes` set with single sign-on, so removed group memberships take effect.
- [ ] `env-passthrough` limited to what apps need; never pass the hub's own secrets.
- [ ] The users file and backups readable only by the hub's user, and kept out of git.
- [ ] The Docker socket mount removed if you don't use Docker apps.
- [ ] Untrusted apps on a separate hub, or in containers.
