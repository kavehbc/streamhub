# Home page and boards

This page is for the people who use a hub: how to find an app and open it.

## The top menu

Every page has the same menu. It holds **Home**, **News** (when there are announcements) and one entry per **board**. A lock marks a board that needs a login. At the right are the **theme switch** (◐) and either **Log in** or your **account menu**. On a phone, the menu folds into the ☰ button.

```{figure} /_static/screenshots/home-anonymous.png
:alt: The home page before signing in, with locked Sales and Operations boards
:class: screenshot

The home page before signing in. Boards that need a login show a lock.
```

## Home

The home page shows:

- the site title and a short introduction, with a button for each of your first boards;
- counters: the boards you can open, their apps, and how many are running;
- **Your favorites**: the apps you starred, with a live status dot;
- **Apps**: the apps listed on the home page itself (the board `""`), when the hub has any;
- **Boards**: every board, with its number of apps, or *Sign in to open*;
- **Latest news**: the three most recent announcements. **All news** opens the full list.

```{figure} /_static/screenshots/home.png
:alt: The home page of a signed-in admin with favorites, boards and news
:class: screenshot

The home page after signing in.
```

## Boards and app cards

A board lists its apps as cards. Each card shows the app's icon, name and description, its kind (Streamlit, Python, Link, Docker…) and its **status**:

| Dot | Status | Meaning |
|---|---|---|
| Green | Running | Ready: it opens at once |
| Amber | Starting | Launching: opening it shows the loading page |
| Red | Unhealthy | It failed its health checks; the hub restarts it if it is set up to |
| Gray | Idle | Not running: opening it starts it |

The status refreshes by itself. **Open** opens the app in its own browser tab, and starts it if needed. An app can have **child apps**, which are listed inside its card with their own status, star and report link. A card marked *Disabled* is listed but can't be opened.

```{figure} /_static/screenshots/board.png
:alt: The Demo board with four app cards, one of them starred
:class: screenshot

A board. The Flask demo has a child app, the FastAPI demo.
```

```{figure} /_static/screenshots/board-ops.png
:alt: The Operations board with two idle apps and a disabled link
:class: screenshot

A protected board. *Legacy reports* is disabled: it is listed, but it has no Open button.
```

### Search and filters

- **Search apps** filters the cards by name, ID or description, including child apps.
- **All**, **Running** and **Favorites** narrow the cards to the running apps or to your favorites.

```{figure} /_static/screenshots/board-filter.png
:alt: A board filtered to running apps matching "demo"
:class: screenshot

The Running filter combined with a search.
```

### Favorites

Click the ☆ on a card to make it a favorite. Favorites come first on their board and appear on the home page. They are stored in your browser, so they follow the browser, not your account.

## News

**News** lists every announcement, newest first, and can filter them by type: normal, info (blue) or warning (orange).

```{figure} /_static/screenshots/news.png
:alt: The News page with four announcements
:class: screenshot

The News page.
```

## Dark mode

The hub follows your system's light or dark setting. The ◐ button switches it, and the choice is remembered in your browser.

```{figure} /_static/screenshots/home-dark.png
:alt: The home page in the dark theme
:class: screenshot

The dark theme.
```

## On a phone

The layout adapts to small screens. The menu folds into ☰, cards stack, and the admin tables turn into cards.

::::{grid} 1 2 2 2

:::{grid-item}
```{image} /_static/screenshots/phone-board.png
:alt: A board on a phone
:class: screenshot phone
```
:::

:::{grid-item}
```{image} /_static/screenshots/phone-menu.png
:alt: The open menu on a phone
:class: screenshot phone
```
:::
::::
