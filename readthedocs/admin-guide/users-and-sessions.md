# Users and sessions

## Users

The **Users** tab edits `streamhub-users.json`. Passwords are never shown: a new password is hashed when you save. The admin defined by `STREAMHUB_ADMIN_PASSWORD` isn't in this file, so it isn't listed.

```{figure} /_static/screenshots/admin-users.png
:alt: The Users tab with three users
:class: screenshot

The Users tab.
```

**Add user** and ✎ open the editor:

| Field | Meaning |
|---|---|
| User name | Letters, digits and `. _ @ -` |
| Sign-in | *Password* (a local user), or an *OpenID Connect* or *LDAP* account. A single sign-on entry has no password: it sets that account's role and boards instead of the group mapping. |
| Password | For local users. **Generate** creates a strong password and shows it once: copy it for the user. Leave the field unchanged to keep the current password. |
| Role | See below |
| Boards | The login boards this user can see. Admins see every board. |

```{figure} /_static/screenshots/admin-user-editor.png
:alt: The user editor for bob
:class: screenshot

The user editor.
```

### Roles

| Role | Can do |
|---|---|
| `admin` | Everything: every app, every admin section, and the hub actions (reload, restart, stop, stop all apps) |
| `manager` | Also starts, stops and monitors apps on the admin page (Dashboard, Network), and reads `/metrics` |
| `user` | Opens the boards it is given |
| `guest` | Opens the boards it is given |

Every role can use **Clear memory**, which stops only apps with `auto_shutdown`, and can read the logs of the apps it can open. Changes to a local user apply on that user's next request: a removed user is logged out at once.

```{tip}
Many users? Connect single sign-on instead, and map directory groups to roles and boards: [Single sign-on](../configuration/single-sign-on.md).
```

## Sessions

The **Sessions** tab lists the active sessions: user, sign-in source, role, when they signed in, when they were last seen, and their address. Your own session is marked *this session*. **Revoke** ends one session; **All of user** ends every session of that user, including sessions from before version 2.2. A revocation applies on every instance of the hub within 5 seconds. **Log out** revokes the user's own session.

```{figure} /_static/screenshots/admin-sessions.png
:alt: The Sessions tab
:class: screenshot

The Sessions tab.
```

Sessions are kept in `.streamhub-sessions.sqlite3` in the config folder (`sessions-db`). Logins of single sign-on users keep the role and boards they had at login until the session ends; `sso-session-minutes` bounds how long that can be.
