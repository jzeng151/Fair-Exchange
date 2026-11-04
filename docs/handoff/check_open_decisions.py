#!/usr/bin/env python3
"""Handoff open-decisions check (#39).

Every spec in docs/specs/ that has a "Not decided" section must be accounted for in the open-decisions
list of docs/handoff/06-known-limitations.md, so that no open decision is dropped from the handoff.

Two guards:
  1. Each spec with a "Not decided" section is referenced by file name in the open-decisions list.
  2. The handoff declares, per spec, how many "Not decided" bullet items that spec currently has, in a
     manifest comment. If a spec gains or loses an item, the count no longer matches and the build
     fails until someone updates both the list and the count. This catches a new decision added to a
     spec that is already linked (which a filename-only check would miss).

The manifest lives in 06-known-limitations.md as a single HTML comment, one line per spec:
    <!-- open-decisions-manifest
    13-conversation-steps.md: 2
    memory.md: 3
    ...
    -->

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
NOT_DECIDED = re.compile(r"^(#{2,4})\s+Not decided\b", re.MULTILINE)
OPEN_DECISIONS = re.compile(r"^##\s+Open decisions\b", re.MULTILINE)
MANIFEST = re.compile(r"<!--\s*open-decisions-manifest\s*(.*?)-->", re.DOTALL)
BULLET = re.compile(r"^\s*-\s+\S")

# This spec gathers the list itself; it has a "Not decided"-style note but needs no self-entry.
SELF = {"39-handoff.md"}


def _section_after(text: str, heading_match: re.Match[str]) -> str:
    """The lines of the section the heading opens, up to the next heading of the same or higher level."""
    level = len(heading_match.group(1))
    start = heading_match.end()
    rest = text[start:]
    end = re.search(rf"^#{{1,{level}}}\s", rest, re.MULTILINE)
    return rest[: end.start()] if end else rest


def open_decision_counts() -> dict[str, int]:
    """For each spec with a 'Not decided' section, the number of top-level bullet items in it."""
    counts: dict[str, int] = {}
    for md in sorted(SPECS.glob("*.md")):
        if md.name in {"README.md"} | SELF:
            continue
        text = md.read_text(encoding="utf-8")
        m = NOT_DECIDED.search(text)
        if not m:
            continue
        section = _section_after(text, m)
        counts[md.name] = sum(1 for line in section.splitlines() if BULLET.match(line))
    return counts


def handoff_text() -> str:
    return HANDOFF.read_text(encoding="utf-8")


def declared_manifest(text: str) -> dict[str, int]:
    m = MANIFEST.search(text)
    if not m:
        raise SystemExit(f"{HANDOFF.relative_to(ROOT)} has no open-decisions-manifest comment")
    declared: dict[str, int] = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line:
            continue
        name, _, count = line.partition(":")
        declared[name.strip()] = int(count.strip())
    return declared


def main() -> int:
    text = handoff_text()
    if not OPEN_DECISIONS.search(text):
        print(f"{HANDOFF.relative_to(ROOT)} has no '## Open decisions' section")
        return 1
    body = text[OPEN_DECISIONS.search(text).end():]
    actual = open_decision_counts()
    declared = declared_manifest(text)

    problems: list[str] = []
    for name, count in actual.items():
        if name not in body:
            problems.append(f"{name}: has {count} open decision(s) but is not referenced in the list")
        if declared.get(name) != count:
            problems.append(f"{name}: spec has {count} open decision(s), manifest declares {declared.get(name)}")
    for name in declared:
        if name not in actual:
            problems.append(f"{name}: in the manifest but has no 'Not decided' section anymore")

    if problems:
        print("Open-decisions check failed:")
        for p in problems:
            print(f"  {p}")
        print(f"Update {HANDOFF.relative_to(ROOT)}: the list and the open-decisions-manifest comment.")
        return 1
    print("Every spec's open decisions are referenced, and the counts match the manifest.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
