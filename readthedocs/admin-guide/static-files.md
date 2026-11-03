# Static files

The **Static files** tab (admins) manages the static folder, the `cdf` setting, which the hub serves at `/cdf/`. It holds app icons, logos and any file apps link to, such as a stylesheet.

```{figure} /_static/screenshots/admin-static-icons.png
:alt: The Static files tab inside the icons folder
:class: screenshot

The `icons` folder, with thumbnails and per-file actions.
```

- Click a folder to open it; the path at the top leads back.
- **Upload** files with the button, or drop them on the page (16 MB per upload). Replacing an existing file asks first.
- **New folder** creates a folder.
- Per entry: 🔗 copies the file's URL (`/cdf/icons/monitor.png`), ✎ renames or moves it, 🗑 deletes a file or an empty folder.
- Every path must stay inside the static folder.

The icon and logo pickers of the app editor and the Settings tab use the same folder, and their **Upload** buttons add files to `icons/`.

```{important}
By default the static folder is the one bundled with Streamhub, inside the installed package. An upgrade, or a new container, replaces it, and your uploads are lost. Set **Static folder (/cdf/)** in Settings → Schedule and files to a folder of your config, for example `cdf`, and copy the bundled files there first. The dashboard's checklist reminds you.
```

```{figure} /_static/screenshots/admin-static.png
:alt: The root of the static folder, with a note that it is the bundled folder
:class: screenshot

The tab warns while the bundled folder is in use.
```

## The temp folder

`/temp/<path>` serves a second public folder, `temp` (default `<config>/temp`). It is **emptied on every memory clean**, so apps can use it for large downloads they produce: write the file there, with a unique name, and link to `/temp/<name>`. The dashboard shows its size and can purge it. Its path is in `/api/` as `cdf_temp`.

```{warning}
Files in the static and temp folders are public, and they are served from the hub's own address, including HTML and SVG. Upload only files you trust.
```
