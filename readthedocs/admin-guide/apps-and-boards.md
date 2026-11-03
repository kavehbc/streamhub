# Apps and boards

The **Apps** tab edits `streamhub-apps.json`: the boards first, then the apps. Changes apply on the next request, without a restart.

```{figure} /_static/screenshots/admin-apps.png
:alt: The Apps tab with the Boards table and the Apps table
:class: screenshot

The Apps tab.
```

## Boards

A board groups apps and gives the top menu an entry. **Add board** asks for:

| Field | Meaning |
|---|---|
| Name | The board's ID, ending in `.brd` (for example `sales.brd`). Its page is `/sales.brd/`. |
| Label | The text of the menu and the board card |
| Login required | Only users given this board (or `*`, all boards) can see it **and open its apps** |

Deleting a board takes it off its apps. The home page itself counts as a board, `""`: apps listed there appear on the home page and are public.

## Order

Drag the ☰ grip of a row to reorder boards, top-level apps (with their children), or the children of one app. You can also focus the grip and press **Up** or **Down**. The order is the order of the menu, the home page and the cards. Reordering is off while the list is filtered.

## The app editor

**Add app**, ✎ (edit), and **Add child** open the app editor. It starts with the app's **Type**, then shows that type's fields.

| Type | What it is | Main fields |
|---|---|---|
| Streamlit app | A Streamlit script, run on this server in the Python environment you pick | Folder, Entry script, Python environment |
| Python web app | Any Python web server (Flask, Dash, FastAPI…), run on this server | Folder, Entry script, Python environment, Health path |
| Docker image | A container started from an image, pulled when missing | Image, The image runs (web or Streamlit), Container port, Environment variables, Volumes, Other `docker run` options |
| Kubernetes pod | A pod in the cluster the hub runs in | Image, Container port, Kubernetes options |
| Link to a URL | The card opens another website | URL |
| Proxy to a URL | The hub serves another website under `/<app ID>/`, behind its own login | URL |
| Hub page | A card that opens a page of the hub, `/<app ID>/` | – |

```{figure} /_static/screenshots/admin-app-editor-docker.png
:alt: The app editor with the Docker image type selected
:class: screenshot

Switching the type to *Docker image* swaps the Launch fields for the Container ones.
```

### General fields

| Field | Meaning |
|---|---|
| App ID | Short and unique: the app's address is `/<app ID>/`. The editor says as you type whether the ID is free. The hub's own paths (`admin`, `api`, `login`…) are refused. |
| Name, Description, Icon | What the card shows. **Choose** picks an image of the static folder; **Upload** adds one to `icons/`. |
| Display | *Show*; *Disabled* (listed, can't be opened); *Hidden* (not listed, still opens by URL, subject to its boards) |
| Listed under | *Top level*, or another app: a child app shows inside its parent's card |
| Boards | Where the app is listed. Its boards also decide who can open it; admins can open every app. |
| Developers | One per line, `Name <email>`. *Report an issue* writes to them. |

### Launch fields (Streamlit and Python apps)

| Field | Meaning |
|---|---|
| Folder | Where the app's code is; also its working directory. Relative paths start at the config folder. Checked on the server as you type. |
| Entry script | Relative to the folder |
| Python environment | A conda env name or an environment folder. Start typing to see the server's conda environments. Empty: the default environment of the Settings, else the hub's own Python. |
| Python executable | An explicit interpreter path; overrides the environment |
| Launcher script | A `.sh`, `.bat`, `.cmd` or `.ps1` script that starts the app. It receives the port flags and must forward them. |
| Run through conda run | For environments that need activation (some Windows DLLs) |
| Command | A JSON list that replaces the entry script, with `{python}`, `{port}`, `{app_id}` and `{base_path}` placeholders |
| Extra arguments | One per line, appended to the command |
| Environment variables | One `NAME=value` per line |
| Hub variables passed through | Names or globs (such as `AWS_*`) of the hub's environment variables this app receives. Apps get no other hub variables. |

### Lifecycle fields

| Field | Meaning |
|---|---|
| Stop on memory clean and when idle | `auto_shutdown`. On by default. |
| Start with the hub and after scheduled cleans | `auto_start` |
| Idle timeout (min) | Stop the app after this long without use; `0` turns it off |
| Restart | *Never*, *When it fails* (`on-failure`), or *Whenever it stops* (`always`), with backoff |
| Health checks / Health path | A path under `/<app ID>/` that answers 2xx or 3xx when the app works. Streamlit apps use `_stcore/health` by default. The hub uses it to know when the app is ready, and to restart a hung app. |
| Streamlit user headers | Fill `st.user` with the signed-in user ([Writing apps](../deployment/writing-apps.md#knowing-who-is-signed-in)) |

New apps are saved with a `type`, so their IDs need no suffix. The [Apps file reference](../configuration/apps.md) lists the JSON key behind each field.

## Child apps

A child app has its own ID, address, boards and lifecycle, and is shown inside its parent's card. Use **Add child** on a parent row, or set **Listed under** in the editor. Children nest one level deep.

## Deleting an app

🗑 removes the entry. A running app keeps running until it stops; stop it on the dashboard first.
