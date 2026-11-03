# Users file: `streamhub-users.json`

A JSON object of users. Create it with `streamhub init`, the setup page, or the admin page's **Users** tab, which writes the password hashes for you. **Keep it out of git.**

```json
{
  "alice": { "password": "pbkdf2_sha256$600000$…", "role": "admin",   "boards": ["*"] },
  "bob":   { "password": "pbkdf2_sha256$600000$…", "role": "user",    "boards": ["sales.brd"] },
  "carol@example.com": { "source": "oidc", "role": "manager", "boards": ["*"] }
}
```

| Key | Description |
|---|---|
| `password` | A PBKDF2 hash, for local users. Raw passwords are refused. |
| `role` | `admin`, `manager`, `user` or `guest` |
| `boards` | The protected boards the user can open; `["*"]` means all |
| `source` | `local` (the default), `oidc` or `ldap` |

## Roles

| Role | Grants |
|---|---|
| `admin` | Every app; `/api/`, `/update/`, `/restart/`, `/exit/`, and *stop all apps* on `/clear/`; on `/admin/`, the apps, users, news and settings editors, Docker, static files, sessions, the JSON editor and git |
| `manager` | On `/admin/`: server load, start, stop, restart, logs, usage and CPU affinity of apps; the `/api/apps/<id>/start`, `/stop` and `/restart` endpoints; `/metrics` |
| `user`, `guest` | The boards listed in `boards`; `/clear/` (apps with `auto_shutdown` only); `/out/` for the apps they can open |

An app is open to a user when **one of its boards** is the home page (`""`), a public board, or a protected board the user has. Admins can open every app; the built-in `help.cmd` is public.

## Passwords

Passwords are stored as hashes only: `pbkdf2_sha256$<iterations>$<salt>$<digest>`, with 600,000 iterations.

- Create a hash with `streamhub passwd` (or `make passwd`) and paste it into the file.
- To convert a file that still holds raw passwords, run `streamhub hash-passwords <config folder or users file>`. It rewrites the file in place, checks each new hash first, and prints only user names.
- A raw password cannot log in: the hub logs an error that names the user and the command that fixes it.
- The admin page never shows passwords. The JSON editor shows `********` instead: keeping `********` leaves a password unchanged, and typing a new value stores its hash.

```console
$ streamhub passwd
Password:
Repeat:
pbkdf2_sha256$600000$2f4c…$9b1e…
```

## Single sign-on accounts

An entry with `"source": "oidc"` or `"ldap"` has no password. It gives that SSO account its own role and boards, instead of the [group mapping](single-sign-on.md#group-mapping). It can't be used to log in with the password form, and an SSO login never takes over a local account of the same name.

## Changes apply at once

The file is re-read when it changes. A local user's role and boards come from the file on every request, so edits and removals apply immediately: a removed user is logged out.

## When the users file is invalid

**An unusable users file grants nothing.** If the file becomes invalid (bad JSON, an unknown `role` or `source`), unreadable, or is deleted after the hub loaded it:

- its local users are logged out;
- single sign-on logins and sessions are refused, since an override in the file can't be read;
- `/admin/` shows the error;
- only the `STREAMHUB_ADMIN_PASSWORD` admin can still log in.

Fix it on disk; `streamhub check` names the problem. To remove every user, write `{}`. A users file that never existed simply has no users.

## An admin without a users file

`STREAMHUB_ADMIN_PASSWORD` (and `STREAMHUB_ADMIN_USER`, default `admin`) adds or replaces an admin user from the environment. A raw value is hashed in memory; a hash from `streamhub passwd` is used as is. See [Environment variables](environment.md).
