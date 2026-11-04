#!/usr/bin/env python3
"""Handoff open-decisions check (#39).

Every spec in docs/specs/ that has a "Not decided" section must be referenced in the open-decisions
list of docs/handoff/06-known-limitations.md, so that no open decision is dropped from the handoff.
The check matches on the spec's file name (e.g. "13-conversation-steps.md" or "memory.md"), which is
how the handoff links to specs.

Run from the repository root: python docs/handoff/check_open_decisions.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPECS = ROOT / "docs" / "specs"
HANDOFF = ROOT / "docs" / "handoff" / "06-known-limitations.md"
# A "Not decided" section heading, e.g. "### Not decided (do not build or assume)".
NOT_DECIDED = re.compile(r"^#{2,4}\s+Not decided\b", re.MULTILINE)
# The open-decisions section of the handoff doc; everything after that heading.
OPEN_DECISIONS = re.compile(r"^##\s+Open decisions\b", re.MULTILINE)

# This spec owns the gathered list itself; it has a "Not decided"-style note but needs no self-link.
SELF = {"39-handoff.md"}


def specs_with_open_decisions() -> list[str]:
    found = []
    for md in sorted(SPECS.glob("*.md")):
        if md.name == "README.md":
            continue
        if NOT_DECIDED.search(md.read_text(encoding="utf-8")):
            found.append(md.name)
    return found


def open_decisions_text() -> str:
    text = HANDOFF.read_text(encoding="utf-8")
    m = OPEN_DECISIONS.search(text)
    if not m:
        raise SystemExit(f"{HANDOFF.relative_to(ROOT)} has no '## Open decisions' section")
    return text[m.end():]


def main() -> int:
    body = open_decisions_text()
    missing = [name for name in specs_with_open_decisions() if name not in SELF and name not in body]
    if missing:
        print("Specs with a 'Not decided' section not referenced in the open-decisions list:")
        for name in missing:
            print(f"  {name}")
        print(f"Add each to {HANDOFF.relative_to(ROOT)} under '## Open decisions'.")
        return 1
    print("Every spec's open decisions are referenced in the handoff.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
