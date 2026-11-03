"""Documentation links: every relative link points to an existing file, and every #anchor to a heading."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = sorted([ROOT / "README.md", ROOT / ".claude" / "CLAUDE.md", ROOT / ".github" / "copilot-instructions.md",
               *(ROOT / "docs").glob("*.md")])
LINK = re.compile(r"\]\(([^)\s]+)\)")


def slug(heading):
    """GitHub's anchor for a heading."""
    return re.sub(r"[^a-z0-9 _-]", "", heading.strip().lower()).replace(" ", "-")


def anchors(path):
    text = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.S)
    return {slug(line.lstrip("#")) for line in text.splitlines() if line.startswith("#")}


def links():
    for doc in DOCS:
        text = re.sub(r"```.*?```", "", doc.read_text(encoding="utf-8"), flags=re.S)
        text = re.sub(r"`[^`\n]*`", "", text)  # examples in inline code are not links
        for target in LINK.findall(text):
            if not re.match(r"[a-z]+:", target):
                yield pytest.param(doc, target, id=f"{doc.name}->{target}")


@pytest.mark.parametrize("doc,target", list(links()))
def test_link_resolves(doc, target):
    path, _, anchor = target.partition("#")
    file = (doc.parent / path).resolve() if path else doc
    assert file.exists(), f"{doc.name}: missing file {path}"
    if anchor and file.suffix == ".md":
        assert anchor in anchors(file), f"{doc.name}: no heading for #{anchor} in {file.name}"
    if anchor.startswith("L") and anchor[1:].isdigit():
        assert int(anchor[1:]) <= len(file.read_text(encoding="utf-8").splitlines()), f"{doc.name}: {target} is past the end"
