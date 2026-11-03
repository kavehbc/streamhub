"""Sphinx configuration of the Streamhub documentation site (Read the Docs)."""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))  # sphinx-click imports streamhub.cli from the checkout

# The version is set in one place: streamhub/__init__.py.
release = re.search(r'__version__ = "([^"]+)"', (ROOT / "streamhub" / "__init__.py").read_text(encoding="utf-8"))[1]
version = ".".join(release.split(".")[:2])

project = "Streamhub"
author = "Kaveh Bakhtiyari"
copyright = "2020-2026, Kaveh Bakhtiyari"

extensions = [
    "myst_parser",
    "sphinx_copybutton",
    "sphinx_design",
    "sphinx_click",
    "sphinxcontrib.mermaid",
]

source_suffix = {".md": "markdown"}
root_doc = "index"
exclude_patterns = ["_build", "_tools", "README.md", ".venv"]

myst_enable_extensions = ["colon_fence", "deflist", "attrs_inline", "attrs_block", "fieldlist", "substitution"]
myst_heading_anchors = 3
myst_substitutions = {"version": release}
# The changelog is included from the root README, whose version headings start at level 3.
suppress_warnings = ["myst.header"]

html_theme = "furo"
html_title = f"Streamhub {release}"
html_logo = "../streamhub/static/brand/logo-mark.svg"
html_favicon = "../streamhub/static/brand/favicon-32.png"
html_static_path = ["_static"]
html_css_files = ["custom.css"]
html_theme_options = {
    "source_repository": "https://github.com/kavehbc/streamhub/",
    "source_branch": "main",
    "source_directory": "readthedocs/",
    "light_css_variables": {"color-brand-primary": "#4f46e5", "color-brand-content": "#4f46e5"},
    "dark_css_variables": {"color-brand-primary": "#a5b4fc", "color-brand-content": "#a5b4fc"},
}
pygments_style = "friendly"
pygments_dark_style = "monokai"

copybutton_prompt_text = r"\$ |PS> "
copybutton_prompt_is_regexp = True
mermaid_version = "11.4.1"

# `make -C readthedocs linkcheck`: the examples point at a local hub.
linkcheck_ignore = [r"https?://localhost(:\d+)?/?.*", r"https?://127\.0\.0\.1.*"]
linkcheck_timeout = 15
