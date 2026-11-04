"""Repo guard, run by CI on every PR and on main. Catches problems the per-package tests can't see.

    python scripts/ci/check_repo.py          # exits 1 and lists every problem

Checks the files tracked by git:
  1. Every JSON file parses with no duplicate keys. npm and most tools silently keep the last of two
     identical keys (e.g. a dependency listed twice after a merge), so nothing else would notice.
  2. Every package with tests is run by CI: a Python package (pyproject.toml + tests/) or an npm package
     (package.json with a "test" script) must appear as a `working-directory` in .github/workflows/ci.yml.
     Otherwise its tests can fail without anyone seeing it.
  3. No iCloud-style duplicate files ("models 2.py", "notes 3.md") are committed.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

CI_WORKFLOW = Path(".github/workflows/ci.yml")
# "name 2.ext" with a single extension; real names like "FPS for import 7.8.26.xlsm" (a date) don't match
ICLOUD_DUPLICATE = re.compile(r" [2-9](\.[A-Za-z0-9]+)?$")


def tracked_files(root: Path) -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=root, check=True, capture_output=True).stdout
    return [p for p in out.decode("utf-8").split("\0") if p]


def _no_duplicates(pairs: list[tuple[str, object]]) -> dict:
    seen: dict = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"duplicate key {key!r}")
        seen[key] = value
    return seen


def json_problems(root: Path, files: list[str]) -> list[str]:
    problems = []
    for name in files:
        if not name.endswith(".json"):
            continue
        try:
            json.loads((root / name).read_text(encoding="utf-8"), object_pairs_hook=_no_duplicates)
        except ValueError as exc:
            problems.append(f"{name}: {exc}")
    return problems


def ci_directories(root: Path) -> set[str]:
    path = root / CI_WORKFLOW
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    return {d.strip().strip("'\"").rstrip("/") for d in re.findall(r"working-directory:\s*(\S+)", text)}


def coverage_problems(root: Path, files: list[str]) -> list[str]:
    tracked = set(files)
    run_by_ci = ci_directories(root)
    problems = []
    for name in sorted(tracked):
        parts = name.split("/")
        if len(parts) != 2:
            continue  # top-level packages only
        package, leaf = parts
        if leaf == "pyproject.toml" and any(f.startswith(f"{package}/tests/") for f in tracked):
            kind = "Python package with tests"
        elif leaf == "package.json":
            scripts = json.loads((root / name).read_text(encoding="utf-8")).get("scripts", {})
            if "test" not in scripts:
                continue
            kind = "npm package with a test script"
        else:
            continue
        if package not in run_by_ci:
            problems.append(f"{package}/: {kind} not run by CI (add a step with "
                            f"`working-directory: {package}` to {CI_WORKFLOW})")
    return problems


def duplicate_file_problems(files: list[str]) -> list[str]:
    return [f"{name}: looks like an iCloud duplicate; remove it (check `git hash-object` against the original)"
            for name in files if ICLOUD_DUPLICATE.search(Path(name).name)]


def problems(root: Path) -> list[str]:
    files = tracked_files(root)
    return json_problems(root, files) + coverage_problems(root, files) + duplicate_file_problems(files)


def main() -> int:
    found = problems(Path.cwd())
    for p in found:
        print(f"::error::{p}")
    print(f"repo guard: {len(found)} problem(s)")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
