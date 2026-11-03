# Roadmap

Remaining work, in priority order. Defects are referred to by their ID in [known-issues.md](known-issues.md), and other improvements by their section in [recommendations.md](recommendations.md); neither is described again here. What has been delivered is in the changelog of the root [README.md](../README.md#changelog).

## Next

| Action | Addresses |
|---|---|
| Rotate the Slack webhook and purge the old secrets from git history (repository owner) | [SEC-3](known-issues.md#sec-3) |
| Decide whether to rewrite the git history, or publish from a fresh one, before the public release (data owner) | [QUAL-6](known-issues.md#qual-6) |
| Record the origin and licence of the bundled icons, or replace them | [QUAL-9](known-issues.md#qual-9) |
| App isolation profiles: run less-trusted apps under their own OS user or in a container, without access to the config folder; optionally a separate origin per app | [SEC-15](known-issues.md#sec-15), [proposal](recommendations.md#proposed-features) |
| Bind apps inside a network namespace or container, or firewall the internal port range, so only the hub can reach them | [SEC-12](known-issues.md#sec-12) |
| Keep Kubernetes app variables in a per-app Secret | [SEC-20](known-issues.md#sec-20) |
| Support Streamlit's own `st.login` behind the hub | [COMPAT-5](known-issues.md#compat-5) |
| Test LDAP, Docker and Kubernetes against real services in CI | [Engineering](recommendations.md#engineering-improvements) |
| Pin the dependency versions CI tested, for deployments | [Engineering](recommendations.md#engineering-improvements) |
| A login limiter shared by all instances | [Engineering](recommendations.md#engineering-improvements) |
| Example Prometheus alert rules for `/metrics` | [Engineering](recommendations.md#engineering-improvements) |
