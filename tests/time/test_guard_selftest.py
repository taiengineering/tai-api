"""Guard self-test: ratchet behavior on a temp tree (does not mutate repo baseline)."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
GUARD = REPO / "scripts" / "check_time_contract.py"
EXPAND = REPO / "scripts" / "check_baseline_no_expand.py"


def _load_guard():
    spec = importlib.util.spec_from_file_location("check_time_contract", GUARD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _tree(tmp_path: Path, files: dict[str, str]):
    for rel, src in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(src, encoding="utf-8")


def _run_guard(mod, tmp_path: Path, *args):
    orig_root, orig_base, orig_allow = mod.ROOT, mod.BASELINE, mod.ALLOWLIST
    mod.ROOT = str(tmp_path)
    mod.BASELINE = str(tmp_path / "time_debt_baseline.json")
    mod.ALLOWLIST = str(tmp_path / "time_exception_allowlist.json")
    argv = sys.argv
    try:
        sys.argv = ["check_time_contract.py", *args]
        return mod.main()
    finally:
        sys.argv = argv
        mod.ROOT, mod.BASELINE, mod.ALLOWLIST = orig_root, orig_base, orig_allow


SRC_NOW = "from datetime import datetime\ndef tick():\n    return datetime.now()\n"
SRC_TWO = (
    "from datetime import datetime\n"
    "def tick():\n"
    "    datetime.now()\n"
    "    return datetime.now()\n"
)
SRC_CLEAN = "def tick():\n    return 1\n"
SRC_DDL = 'SQL = "CREATE TABLE t (ts timestamp without time zone)"\n'


def test_new_violation_fails(tmp_path):
    _tree(tmp_path, {"app.py": SRC_NOW})
    (tmp_path / "time_debt_baseline.json").write_text("{}", encoding="utf-8")
    (tmp_path / "time_exception_allowlist.json").write_text("{}", encoding="utf-8")
    assert _run_guard(_load_guard(), tmp_path, "--check") == 1


def test_existing_baseline_passes(tmp_path):
    _tree(tmp_path, {"app.py": SRC_NOW})
    g = _load_guard()
    assert _run_guard(g, tmp_path, "--baseline") == 0
    assert _run_guard(g, tmp_path, "--check") == 0


def test_removal_passes(tmp_path):
    _tree(tmp_path, {"app.py": SRC_NOW})
    g = _load_guard()
    assert _run_guard(g, tmp_path, "--baseline") == 0
    (tmp_path / "app.py").write_text(SRC_CLEAN, encoding="utf-8")
    assert _run_guard(g, tmp_path, "--check") == 0


def test_duplicate_count_up_fails(tmp_path):
    _tree(tmp_path, {"app.py": SRC_NOW})
    g = _load_guard()
    assert _run_guard(g, tmp_path, "--baseline") == 0
    (tmp_path / "app.py").write_text(SRC_TWO, encoding="utf-8")
    assert _run_guard(g, tmp_path, "--check") == 1


def test_new_naive_ddl_fails(tmp_path):
    _tree(tmp_path, {"app.py": SRC_DDL})
    (tmp_path / "time_debt_baseline.json").write_text("{}", encoding="utf-8")
    (tmp_path / "time_exception_allowlist.json").write_text("{}", encoding="utf-8")
    assert _run_guard(_load_guard(), tmp_path, "--check") == 1


def test_baseline_expansion_blocked(tmp_path):
    old = {"aaaa": {"count": 1, "rule": "PY_DIRECT_NOW"}}
    new = {
        "aaaa": {"count": 1, "rule": "PY_DIRECT_NOW"},
        "bbbb": {"count": 1, "rule": "PY_DIRECT_NOW"},
    }
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "time_exception_allowlist.json").write_text("{}", encoding="utf-8")
    (repo / "time_debt_baseline.json").write_text(json.dumps(old), encoding="utf-8")
    subprocess.check_call(["git", "init", "-q"], cwd=repo)
    subprocess.check_call(["git", "config", "user.email", "t@t"], cwd=repo)
    subprocess.check_call(["git", "config", "user.name", "t"], cwd=repo)
    subprocess.check_call(["git", "add", "time_debt_baseline.json", "time_exception_allowlist.json"], cwd=repo)
    subprocess.check_call(["git", "commit", "-qm", "base"], cwd=repo)
    (repo / "time_debt_baseline.json").write_text(json.dumps(new), encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(EXPAND), "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 1
    assert "BASELINE EXPANSION BLOCKED" in r.stdout
    assert "bbbb" in r.stdout
