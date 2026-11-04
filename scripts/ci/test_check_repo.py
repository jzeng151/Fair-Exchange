"""Tests for scripts/ci/check_repo.py, the repo guard CI runs on every PR."""
import json
import subprocess
from pathlib import Path

import check_repo as guard

CI = """
jobs:
  checks:
    steps:
      - name: Agent tests
        working-directory: agent
        run: uv run --no-sync pytest
      - name: API
        working-directory: api
        run: npm ci && npm test
"""


def repo(tmp_path: Path, files: dict[str, str]) -> Path:
    for name, text in {".github/workflows/ci.yml": CI, **files}.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    return tmp_path


def test_a_clean_repo_passes(tmp_path):
    root = repo(tmp_path, {"agent/pyproject.toml": "", "agent/tests/test_x.py": "",
                           "api/package.json": json.dumps({"scripts": {"test": "vitest run"}})})
    assert guard.problems(root) == []


def test_duplicate_json_keys_are_caught(tmp_path):
    root = repo(tmp_path, {"api/package.json": '{"scripts": {"test": "x"}, "dependencies": {"ajv": "8", "ajv": "8"}}'})
    assert any("duplicate key 'ajv'" in p and "api/package.json" in p for p in guard.problems(root))


def test_a_python_package_with_tests_not_run_by_ci_is_caught(tmp_path):
    root = repo(tmp_path, {"agent/pyproject.toml": "", "agent/tests/test_x.py": "",
                           "sync/pyproject.toml": "", "sync/tests/test_y.py": ""})
    found = guard.problems(root)
    assert any("sync" in p and "not run by CI" in p for p in found)
    assert not any("agent" in p for p in found)


def test_an_npm_package_with_a_test_script_not_run_by_ci_is_caught(tmp_path):
    root = repo(tmp_path, {"web/package.json": json.dumps({"scripts": {"test": "vitest run"}})})
    assert any("web" in p and "not run by CI" in p for p in guard.problems(root))


def test_icloud_style_duplicate_files_are_caught(tmp_path):
    root = repo(tmp_path, {"agent/src/models 2.py": "", "docs/notes 3.md": ""})
    found = guard.problems(root)
    assert any("models 2.py" in p for p in found) and any("notes 3.md" in p for p in found)


def test_untracked_files_are_ignored(tmp_path):
    root = repo(tmp_path, {})
    (root / "stray 2.py").write_text("", encoding="utf-8")  # not committed
    assert guard.problems(root) == []


def test_dates_in_real_file_names_are_not_mistaken_for_duplicates(tmp_path):
    root = repo(tmp_path, {"docs/olena_data/FPS for import 7.8.26.xlsm": "", "docs/APS 10.22.26.xlsm": ""})
    assert guard.problems(root) == []
