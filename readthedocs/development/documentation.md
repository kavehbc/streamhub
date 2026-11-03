# This documentation

This site is built with [Sphinx](https://www.sphinx-doc.org/), [MyST Markdown](https://myst-parser.readthedocs.io/) and the [Furo](https://pradyunsg.me/furo/) theme, and hosted on [Read the Docs](https://readthedocs.org/). Everything it needs is in the `readthedocs/` folder of the repository.

```text
readthedocs/
├── .readthedocs.yaml        Read the Docs build configuration
├── conf.py                  Sphinx configuration (the version comes from streamhub/__init__.py)
├── requirements.txt         Sphinx and its extensions
├── Makefile, make.bat       Local builds
├── index.md                 Home page and table of contents
├── getting-started/  user-guide/  admin-guide/  configuration/  deployment/  reference/  development/
├── changelog.md             Included from the root README's Changelog
├── _static/
│   ├── custom.css
│   └── screenshots/         One PNG per screen, retaken by _tools/screenshots.py
└── _tools/screenshots.py    Builds a sample hub and takes every screenshot
```

## Build locally

```bash
pip install -r readthedocs/requirements.txt
make docs                       # or: make -C readthedocs html; Windows: make.bat docs
```

Open `readthedocs/_build/html/index.html`. The build treats warnings as errors, as Read the Docs does, so broken cross-references fail it. `make -C readthedocs linkcheck` checks the external links.

The CLI reference is generated from `streamhub.cli` with [sphinx-click](https://sphinx-click.readthedocs.io/), so it needs Streamhub's dependencies (Tornado, Click, psutil) in the build environment. A development install (`make install`) has them.

## Publish on Read the Docs

1. Sign in to [readthedocs.org](https://readthedocs.org/) with GitHub and **Import a project**: `kavehbc/streamhub`.
2. The configuration file is not at the repository root. In the project's **Settings → Advanced settings**, set **Build configuration file** to `readthedocs/.readthedocs.yaml`, and save.
3. **Build version**. Every push to the default branch rebuilds `latest`. To publish a version per release, activate tags under **Versions** (for example `v2.3.0`), and set the default version to `stable`.

The configuration builds on Ubuntu 24.04 with Python 3.12, installs `readthedocs/requirements.txt` and the package itself, fails on warnings, and also produces PDF and EPUB downloads.

## Retake the screenshots

After a UI change, retake the screenshots so they match:

```bash
pip install -e ".[tools,examples]" playwright
python -m playwright install chromium        # or use an installed browser with --channel chrome
python readthedocs/_tools/screenshots.py
python readthedocs/_tools/screenshots.py admin-dashboard home   # only some of them
```

The script builds a sample hub in a temporary folder: three boards, sample apps (one of them broken on purpose, for the error page), three users and four news items. It starts the hub on port 8600, plus an empty hub on 8610 for the setup page, drives a browser through every screen, and writes `readthedocs/_static/screenshots/*.png`. Before each screenshot it replaces local paths (the temporary folder, your home folder, the package folder) with neutral ones. The Docker and Network tabs are filtered to the hub's own containers and ports. Check the images before committing them anyway.

`--hub-python` runs the hubs with another interpreter, for example the one of your development environment when Playwright is installed elsewhere.

## Keep it in sync

The site documents what the code does. When a change affects users (a setting, a CLI option, an endpoint, a screen), update the matching page in the same change, and retake the screenshots the change affects. The maintainer docs in `docs/` remain the detailed reference of the architecture and the open issues.
