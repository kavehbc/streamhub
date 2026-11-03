# Codebase review and recommendations

Review date: 2026-10-29. Streamhub is a single-process Tornado gateway with on-demand process, Docker and Kubernetes runtimes. This review covered routing, authentication, proxying, lifecycle, configuration, notifications, deployment and tests. It is not a penetration test or a dependency vulnerability scan; deployment-specific trust boundaries and live LDAP/OIDC servers were not tested.

This file lists only the recommendations that are **not implemented yet**. Implemented ones are removed and described in the changelog of the root [README.md](../README.md#changelog).

## Priorities

Issue details, impact and source links live in [known-issues.md](known-issues.md); the work is tracked in [roadmap.md](roadmap.md). Severity there assumes a shared, network-reachable deployment. Priorities below also consider operational urgency.

| Priority | Finding | Verification |
|---|---|---|
| P0 | [SEC-3](known-issues.md#sec-3) | Confirm revocation and review remote history and downstream copies. |
| P0 | [SEC-15](known-issues.md#sec-15) | Test that an app cannot read the config folder, the hub's process or its start-up environment under the intended threat model. |
| P1 | [SEC-12](known-issues.md#sec-12) | Test that an app's internal port can't be reached except from the hub, whatever address the app binds. |
| P1 | [SEC-20](known-issues.md#sec-20) | Test that a user who can read Pods but not Secrets can't read app variables. |
| P1 | [QUAL-6](known-issues.md#qual-6), [QUAL-9](known-issues.md#qual-9) | Before the public release: check that no published commit holds employer data, and that every bundled image has a known licence. |
| P2 | [COMPAT-5](known-issues.md#compat-5) | Verify Streamlit's own login end to end behind the hub. |

## Engineering improvements

- **Test against real services.** LDAP is tested only with a simulated `ldap3`. Run the LDAP login (direct bind, search bind, STARTTLS and LDAPS, untrusted certificates) against a test directory in CI, and cover Docker and Kubernetes lifecycle behavior (launch, failure, leftover cleanup) in environments that provide those services. Keep the tests deterministic and isolated.
- **Pin tested deployment versions.** CI tests the minimum versions and audits dependencies, but deployments still resolve the newest releases. Maintain a constraints file of the versions CI tested, for deployments to install with.
- **Share the login limit between instances.** The login throttle is per instance, so N instances allow N times the limit. Use a shared atomic limiter when the limit must hold for the whole deployment.
- **Alerting.** `/metrics` exposes readiness, start failures, notification failures, login failures and invalid config files. Provide example Prometheus alert rules for them, and test that each alert can fire without exposing private data.

## Proposed features

This is a proposal, not an existing guarantee:

- **App isolation profiles:** optional separate origins and least-privilege runtime identities, with network and resource policies. Acceptance: an app cannot invoke another app or hub administration with a user's browser credentials solely through same-origin access, and cannot read hub secrets through its execution environment, its file access or the hub's process. This addresses [SEC-12](known-issues.md#sec-12) and [SEC-15](known-issues.md#sec-15); the current boundaries are described in [architecture.md](architecture.md#trust-model).

## Limits

- No production systems, real identity providers, Docker/Kubernetes clusters or live notification services were exercised. Recommendations involving those systems require integration testing before deployment.
