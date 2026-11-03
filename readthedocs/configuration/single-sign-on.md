# Single sign-on

Users can sign in with an **OpenID Connect** provider (a button on the login page), with an **LDAP** directory (the normal login form, tried after the users file), or both. Directory groups are mapped to roles and boards. The Settings tab has forms for all of it, under **Sign-in**.

```json
"oidc": { "issuer": "https://login.example.com/realms/main", "client-id": "streamhub",
          "label": "Sign in with Okta", "scopes": ["openid", "profile", "email"],
          "username-claim": "preferred_username", "groups-claim": "groups" },
"ldap": { "url": "ldaps://ldap.example.com", "bind-dn": "cn=streamhub,ou=svc,dc=example,dc=com",
          "search-base": "ou=people,dc=example,dc=com", "search-filter": "(uid={username})",
          "group-attribute": "memberOf" },
"group-mapping": [
  { "group": "data-team", "role": "user", "boards": ["sales.brd"] },
  { "group": "cn=ops,ou=groups,dc=example,dc=com", "role": "manager", "boards": ["*"] }
],
"sso-default-role": null,
"sso-session-minutes": 480
```

## OpenID Connect

Works with Microsoft Entra ID (Azure AD), Okta, Keycloak, Google, Auth0 and other providers, using the authorization code flow with PKCE.

1. Install the `oidc` extra: `pip install "py-streamhub[oidc]"`. The Docker image has it.
2. Register a **confidential client** with the provider. Use the redirect URI `https://<hub host>/login/oidc/callback` and the authorization code flow, and add a groups claim.
3. Set `oidc` and pass the client secret as `STREAMHUB_OIDC_CLIENT_SECRET`.
4. Serve the hub over HTTPS, directly or behind a proxy with `behind-proxy`.

| Key | Default | Description |
|---|---|---|
| `issuer`, `client-id` | required | `https://` only. `<issuer>/.well-known/openid-configuration` must exist and name the same issuer, and every endpoint it lists must be `https://`. |
| `scopes` | `openid profile email` | Requested scopes |
| `username-claim` | `preferred_username` | Claim used as the user name; falls back to `email`, then `sub`. Pick a claim users can't change themselves. |
| `groups-claim` | `groups` | Claim, in the ID token or the userinfo, that lists the user's groups |
| `algorithms` | `RS256` … `ES512` | Accepted ID-token signature algorithms (RS, PS and ES at 256/384/512). Tokens are checked against the provider's `jwks_uri`. |
| `token-auth` | `basic` | `basic` (`client_secret_basic`) or `post` (`client_secret_post`) |
| `redirect-uri` | `<scheme>://<host>/login/oidc/callback` | Set it explicitly behind a proxy that changes the host |
| `label` | `Single sign-on` | Button text |
| `insecure-http` | `false` | Development only: allow an `http://` issuer. Signatures are still checked. |

## LDAP

1. Install the `ldap` extra: `pip install "py-streamhub[ldap]"`.
2. Set `ldap`, and `STREAMHUB_LDAP_BIND_PASSWORD` for a search bind.
3. Use `ldaps://`, or `starttls: true`, because passwords cross that connection.

| Key | Description |
|---|---|
| `url` | Required. `ldap://` or `ldaps://` |
| `user-dn` | Bind directly as this DN, with `{username}`, for example `uid={username},ou=people,dc=example,dc=com` |
| `bind-dn`, `search-base`, `search-filter` | Instead of `user-dn`: bind as a service account, find the user with the filter (default `(uid={username})`), then bind as that user. For Active Directory, try `(sAMAccountName={username})`. |
| `group-attribute` | Attribute that lists the groups (default `memberOf`) |
| `starttls` | `true` to upgrade an `ldap://` connection. If the upgrade fails, nothing is sent. |
| `ca-file` | PEM file of the CA of the directory's certificate (default: the system CAs). Certificates and host names are always verified. |
| `allow-plaintext` | Development only: allow `ldap://` without `starttls` |

The hub refuses to start with an `http://` issuer or a plain `ldap://` URL unless the development options allow it.

## Group mapping

- Rules match group names case-insensitively, and `"group": "*"` matches everyone.
- The highest matching role wins, and the boards of every matching rule are combined.
- A user that matches no rule gets `sso-default-role` with no boards. When it is `null`, that user is refused (403).
- Role and boards are fixed at login and kept in the session, so group changes apply at the next login. `sso-session-minutes` bounds how long that can take, and an admin can revoke sessions on the Sessions tab.
- To give one SSO account its own role and boards, add it to the users file with its `source` ([Users file](users.md#single-sign-on-accounts)).

## First admin with SSO

The setup page isn't offered when OIDC or LDAP is configured: admins then come from `group-mapping`. Map an admin group, or keep a local admin in the users file.

## Troubleshooting

Failed and refused SSO logins are written to the `streamhub.audit` log with the reason: a state mismatch (cookies blocked, or more than 10 minutes on the provider's page), an issuer or audience mismatch, an invalid signature or unknown key, or no matching rule. See [Troubleshooting](../reference/troubleshooting.md).
