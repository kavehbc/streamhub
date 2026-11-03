"""help.cmd: renders the Streamhub user guide (the repository README)."""
from importlib import metadata
from pathlib import Path

import streamlit as st


def guide():
    """The README: next to the code (checkout or executable bundle), else from the installed package."""
    beside = Path(__file__).resolve().parents[2] / "README.md"
    if beside.is_file():
        return beside.read_text(encoding="utf-8")
    try:
        return metadata.metadata("streamhub")["Description"]  # pyproject's readme
    except (metadata.PackageNotFoundError, KeyError):
        here = Path.cwd() / "README.md"
        return here.read_text(encoding="utf-8") if here.is_file() else None


def main():
    st.set_page_config(page_title="Streamhub Help", layout="wide")
    text = guide()
    if not text:
        st.error("The Streamhub user guide (README.md) was not found.")
        st.stop()
    st.markdown(text, unsafe_allow_html=True)


main()
