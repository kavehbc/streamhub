# Streamhub documentation site

The source of the Read the Docs site: Sphinx with MyST Markdown and the Furo theme.

```bash
pip install -r readthedocs/requirements.txt
make docs                 # from the repository root; or: make -C readthedocs html (Windows: make.bat docs)
```

The output is in `readthedocs/_build/html/`. Publishing on Read the Docs, the folder layout and retaking the screenshots (`_tools/screenshots.py`) are described on the site itself, in [development/documentation.md](development/documentation.md).
