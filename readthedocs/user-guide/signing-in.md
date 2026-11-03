# Signing in

Public boards need no account. Protected boards, and their apps, need you to sign in.

## Log in

Click **Log in** at the top right, or open a protected board, and enter your user name and password. When the hub uses single sign-on with an OpenID Connect provider, the page also has a button such as **Sign in with Okta**: click it and sign in with your company account. With LDAP, sign in with your directory user name and password in the normal form.

```{figure} /_static/screenshots/login.png
:alt: The login page
:class: screenshot
:width: 80%

The login page.
```

After you sign in, the boards you were given appear in the menu, and the home page greets you.

- A login lasts 7 days by default (`session-days`). Single sign-on logins may be shorter (`sso-session-minutes`).
- After 10 failed attempts in 5 minutes from your address, the hub refuses logins for a while (HTTP 429). Wait 5 minutes.
- **The login page says the hub has no admin yet:** the hub is new. Its administrator must finish the [setup](../getting-started/quickstart.md#2-create-your-own-hub).

## Your account menu

Click your avatar to open the account menu. It lists what your role allows:

```{figure} /_static/screenshots/account-menu.png
:alt: The account menu of an admin
:class: screenshot

The account menu of an admin.
```

| Role | Menu entries |
|---|---|
| `user`, `guest` | Clear memory, Log out |
| `manager` | Also **Dashboard** and **Network** of the admin panel |
| `admin` | Also Apps and boards, Users, News, Settings, Docker, Static files, Sessions, JSON files, and the hub actions: Reload configuration, Restart hub, Stop hub |

**Log out** ends your session on every instance of the hub.

## What apps know about you

The hub tells each app who you are, with the headers `X-Streamhub-User` and `X-Streamhub-Role`, so an app can greet you or show your own data. Apps never see your password or the hub's cookies. App developers can read more in [Writing apps](../deployment/writing-apps.md#knowing-who-is-signed-in).

## Access denied (403)

A 403 page on an app means none of your boards lists it. Ask an admin to give you the app's board.
