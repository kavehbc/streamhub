# Opening apps

## What happens when you open an app

1. If the app is running, it opens at once.
2. If it isn't, the hub starts it and shows a **loading page**. The page waits for the app to answer, then opens it by itself. A Streamlit app usually takes a few seconds; the hub allows up to two minutes by default (`startup-timeout`).
3. The app runs at `http://<hub>/<app_id>/`. Bookmark that address: it works whether or not the app is running.

```{figure} /_static/screenshots/loading.png
:alt: The loading page while an app starts
:class: screenshot
:width: 80%

The loading page. **App output** shows what the app prints while it starts.
```

```{figure} /_static/screenshots/streamlit-app.png
:alt: A Streamlit app served by the hub under /streamlit-demo/
:class: screenshot

A Streamlit app, served under the hub's address. It knows who is signed in.
```

Apps stop by themselves when nobody has used them for a while, or during the nightly memory clean. Your browser tab then shows the app as disconnected. Refresh the page, and the app starts again.

## When an app can't start

If the app stops, or doesn't answer in time, you see an error page. It gives the reason, the exit code, and the end of the app's log, which usually names the problem (here, a missing Python package):

```{figure} /_static/screenshots/app-error.png
:alt: The error page of an app that stopped with a ModuleNotFoundError
:class: screenshot

The error page shows the end of the app's log.
```

- **Try again** starts the app again.
- **Report an issue** tells its developers (see below).
- The full log is at `/out/<app_id>/`, for users who can open the app.

```{figure} /_static/screenshots/app-output.png
:alt: The output log page of an app
:class: screenshot

`/out/<app_id>/` shows the last 256 KB of the app's log.
```

## Report an issue

Every card has **Report an issue** (the flag icon). The report page lists the app's developers, with mail links, and has a form. When you send the form, the hub delivers it to the hub's report channels (Slack, Teams or email) and, if a mail server is set up, emails the developers with your address as *Reply-To*. The page then tells you whether the report was sent, partly sent, or couldn't be delivered. A client can send 5 reports per 10 minutes.

```{figure} /_static/screenshots/report.png
:alt: The report form with the developers of the app
:class: screenshot
:width: 85%

The report form.
```

## Clear memory

**Clear memory** in the account menu stops the apps that are allowed to stop (`auto_shutdown`) and empties the hub's temporary folder. Use it when the server is short of memory. Admins can also stop every app. The page asks for confirmation first.

```{figure} /_static/screenshots/clear.png
:alt: The Clear memory confirmation page
:class: screenshot
:width: 80%

Clear memory asks before it stops anything.
```

## The Help page

The built-in **Help** app (`/help.cmd/`) shows the Streamhub user guide inside the hub. It is a Streamlit app, so it takes a moment to start the first time.

```{figure} /_static/screenshots/help.png
:alt: The built-in Help page
:class: screenshot

The built-in Help page.
```
