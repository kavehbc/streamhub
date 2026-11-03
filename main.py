"""Backward-compatible entry point: `python main.py <args>` equals `streamhub <args>` (for example `run <config>`)."""
from streamhub.cli import main

if __name__ == "__main__":
    main()
