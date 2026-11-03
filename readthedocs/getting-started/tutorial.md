# Tutorial: a hub for two teams

This tutorial builds the hub shown in the screenshots of this documentation: an **Analytics Hub** with a public **Demo** board and two protected boards, **Sales** and **Operations**. Each step is done on the admin page, and the JSON that the step writes is shown too, because everything the admin page edits is a plain file in the config folder.

You need a hub with an admin account ([Quick start](quickstart.md), steps 2 and 3), and an app to serve. The demo apps work for this: `streamhub demo --folder ./tutorial` copies them to `./tutorial/streamlit`, `./tutorial/flask` and `./tutorial/fastapi`.

## Step 1: name the site

Open **Settings** from the account menu. In **Branding**, set the **Site title** to `Analytics Hub` and the **Team name** to `Data Platform Team`. In **Schedule and files**, check the **Daily memory clean** time and pick your **Time zone**. Click **Save and apply**.

```{figure} /_static/screenshots/admin-settings.png
:alt: The Settings tab with the Branding section
:class: screenshot

Every setting has a hint, and its default is shown as a placeholder. Settings marked *restart* apply after a restart.
```

This writes `streamhub.json`:

```json
{
  "site-title": "Analytics Hub",
  "team-name": "Data Platform Team",
  "schedule": "02:00",
  "timezone": "America/Toronto"
}
```

## Step 2: add boards

Open **Apps and boards**. Under **Boards**, click **Add board** twice:

| Name | Label | Login required |
|---|---|---|
| `sales.brd` | Sales | yes |
| `ops.brd` | Operations | yes |

A board that requires a login is visible only to users who were given it. It also protects its apps: a user without the board can't open them, even by URL.

## Step 3: add apps

Click **Add app**. Choose the **Type** first: the editor then shows only that type's fields.

```{figure} /_static/screenshots/admin-app-editor.png
:alt: The app editor with Type, App ID, Name, Icon, Boards and Developers
:class: screenshot

The app editor. The **App ID** check says whether the ID is free; folder and file fields are checked on the server.
```

For a Streamlit app:

- **Type:** Streamlit app
- **App ID:** `sales-forecast` (the app's address: `/sales-forecast/`)
- **Name** and **Description:** what the card shows
- **Icon:** pick one with **Choose**, or **Upload** your own
- **Boards:** Sales
- **Developers:** one per line, `Jane Doe <jane.doe@example.com>`. **Report an issue** writes to them.
- **Folder:** the app's folder, for example `../streamlit` (relative paths start at the config folder)
- **Entry script:** `main.py`
- **Python environment:** a conda env name or an environment folder. Leave it empty to use the hub's own Python.
- **Restart:** *When it fails*, so a crashed app comes back

Save, and the app appears on its board. Add a Python web app the same way (Type *Python web app*, a Flask `main.py`, **Health path** `health/`). The [Apps and boards](../admin-guide/apps-and-boards.md) page describes every field.

```{figure} /_static/screenshots/admin-apps.png
:alt: The Apps tab listing boards and apps, with drag handles to reorder them
:class: screenshot

The Apps tab. Drag the ☰ grip to reorder boards and apps: that is the order of the menu, the home page and the cards.
```

The apps file now holds:

```json
[
  {"boards": [
    {"name": "demo.brd", "label": "Demo", "auth": false},
    {"name": "sales.brd", "label": "Sales", "auth": true},
    {"name": "ops.brd", "label": "Operations", "auth": true}
  ]},
  {
    "board": ["sales.brd"],
    "app_id": "sales-forecast",
    "type": "streamlit",
    "app_name": "Sales forecast",
    "description": "Weekly forecast by region",
    "folder": "../streamlit",
    "file": "main.py",
    "restart": "on-failure",
    "icon": "/cdf/icons/running.png",
    "developer": [{"name": "Jane Doe", "email": "jane.doe@example.com"}]
  }
]
```

## Step 4: add users

Open **Users** and click **Add user**. Give each user a role and boards:

| User | Role | Boards | Can do |
|---|---|---|---|
| `alice` | manager | all | Open every board, and start, stop and monitor apps on the admin page |
| `bob` | user | Sales | Open the public boards and Sales |

**Generate** creates a strong password and shows it once. Passwords are stored as hashes; the page never shows them again.

```{figure} /_static/screenshots/admin-user-editor.png
:alt: The user editor with sign-in source, role, boards and password
:class: screenshot

The user editor.
```

## Step 5: announce it

Open **News**, click **Add news**, and write a title, a date, a message and a type (*Normal*, *Info* in blue, or *Warning* in orange). The home page shows the latest three; **News** in the top menu lists them all.

## Step 6: check what users see

Log out, and sign in as `bob`. Bob sees the public Demo board and Sales. Operations shows a lock, and its apps answer 403.

```{figure} /_static/screenshots/home-user.png
:alt: The home page as a user with only the Sales board
:class: screenshot

The home page of a user who has the Sales board only.
```

## Step 7: keep the configuration

The config folder now holds everything about this hub:

```text
my-hub/
├── streamhub.json           settings
├── streamhub-apps.json      boards and apps
├── streamhub-users.json     users (password hashes): keep it out of git
├── streamhub-news.json      announcements
├── .streamhub-secret        generated cookie secret (when STREAMHUB_COOKIE_SECRET is not set)
├── .streamhub-sessions.sqlite3
├── logs/                    one <app_id>.log per app, usage.sqlite3
└── temp/                    the public /temp/ folder, emptied by every memory clean
```

Back it up with the **Backup** tab, or put the config, apps and news files in git; the **JSON files** tab can commit and push them ([JSON files and backup](../admin-guide/json-files-and-backup.md)). Check the folder at any time with `streamhub check my-hub`.
