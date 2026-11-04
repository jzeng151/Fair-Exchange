#!/usr/bin/env python3
"""Handoff link check (#39).

Fails if a relative Markdown link in the handoff package points to a file that does not exist, so the
handoff never links to something that isn't there. External links (http/https/mailto) and in-page
anchors (#...) are ignored; a link with an anchor is checked for the file part only.

Scope: docs/handoff/. The spec also names docs/specs/; each spec owns its own cross-links (and a spec
may link to a sibling spec that is still in an open PR), so spec-to-spec links are each spec PR's
responsibility, not this package's. This check covers every link the handoff itself makes, including
the handoff's links into docs/specs/.

Run from the repository root: python docs/handoff/check_links.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIRS = [ROOT / "docs" / "handoff"]
LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def is_external(target: str) -> bool:
    return target.startswith(("http://", "https://", "mailto:", "#"))


def check_file(md: Path) -> list[str]:
    problems: list[str] = []
    for match in LINK.finditer(md.read_text(encoding="utf-8")):
        target = match.group(1).strip()
        if is_external(target):
            continue
        path_part = target.split("#", 1)[0]
        if not path_part:  # a pure in-page anchor like (#open-decisions)
            continue
        resolved = (md.parent / path_part).resolve()
        if not resolved.exists():
            problems.append(f"{md.relative_to(ROOT)} -> {target} (missing {path_part})")
    return problems


def main() -> int:
    problems: list[str] = []
    for d in DIRS:
        for md in sorted(d.rglob("*.md")):
            problems.extend(check_file(md))
    if problems:
        print("Broken relative links:")
        for p in problems:
            print(f"  {p}")
        return 1
    print("All relative links in docs/handoff/ resolve.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
