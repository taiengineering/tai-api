"""Guard self-test: EXACT ledger, expansion, coverage, stability (TIME_CONTRACT_ROOT temp trees)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
GUARD = REPO / "scripts" / "check_time_contract.py"


def _run(root: Path, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "TIME_CONTRACT_ROOT": str(root)}
    return subprocess.run(
        [sys.executable, str(GUARD), *args],
        env=env,
        capture_output=True,
        text=True,
        cwd=str(root),
    )


def _git(root: Path, *args: str) -> None:
    subprocess.check_call(["git", *args], cwd=str(root), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _write(root: Path, rel: str, src: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(src, encoding="utf-8")


def _tree(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, src in files.items():
        _write(tmp_path, rel, src)
    _write(tmp_path, "time_exception_allowlist.json", "{}")
    return tmp_path


def _scan(root: Path) -> dict:
    r = _run(root, "--scan")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _capture(root: Path) -> dict:
    cur = _scan(root)
    payload = {fp: {"repo": "tmp", "fp": fp, "count": c} for fp, c in cur.items()}
    (root / "time_debt_baseline.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return cur


def _init_git(root: Path) -> None:
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")


SRC_NOW = "from datetime import datetime\ndef tick():\n    return datetime.now()\n"
SRC_TWO = "from datetime import datetime\ndef tick():\n    datetime.now()\n    return datetime.now()\n"
SRC_CLEAN = "def tick():\n    return 1\n"
GUARD_MARKER = '#!/usr/bin/env python3\nprint("guard")\n'


class TestExact:
    def test_unchanged_pass(self, tmp_path):
        _tree(tmp_path, {"app.py": SRC_NOW})
        _capture(tmp_path)
        r = _run(tmp_path, "--check")
        assert r.returncode == 0, r.stdout
        assert "TIME GUARD PASS" in r.stdout

    def test_new_fail(self, tmp_path):
        _tree(tmp_path, {"app.py": SRC_NOW})
        (tmp_path / "time_debt_baseline.json").write_text("{}", encoding="utf-8")
        r = _run(tmp_path, "--check")
        assert r.returncode == 1
        assert "NEW " in r.stdout

    def test_count_plus_fail(self, tmp_path):
        _tree(tmp_path, {"app.py": SRC_NOW})
        _capture(tmp_path)
        (tmp_path / "app.py").write_text(SRC_TWO, encoding="utf-8")
        r = _run(tmp_path, "--check")
        assert r.returncode == 1
        assert "COUNT+" in r.stdout

    def test_stale_baseline_fail(self, tmp_path):
        _tree(tmp_path, {"app.py": SRC_NOW})
        _capture(tmp_path)
        (tmp_path / "app.py").write_text(SRC_CLEAN, encoding="utf-8")
        r = _run(tmp_path, "--check")
        assert r.returncode == 1
        assert "STALE BASELINE" in r.stdout

    def test_stale_count_fail(self, tmp_path):
        _tree(tmp_path, {"app.py": SRC_TWO})
        _capture(tmp_path)
        (tmp_path / "app.py").write_text(SRC_NOW, encoding="utf-8")
        r = _run(tmp_path, "--check")
        assert r.returncode == 1
        assert "STALE count" in r.stdout

    def test_removed_shrink_pass(self, tmp_path):
        _tree(tmp_path, {"app.py": SRC_NOW})
        _capture(tmp_path)
        (tmp_path / "app.py").write_text(SRC_CLEAN, encoding="utf-8")
        _capture(tmp_path)
        r = _run(tmp_path, "--check")
        assert r.returncode == 0, r.stdout

    def test_allowlisted_pass(self, tmp_path):
        _tree(tmp_path, {"app.py": SRC_NOW})
        cur = _scan(tmp_path)
        fp = next(iter(cur))
        (tmp_path / "time_debt_baseline.json").write_text("{}", encoding="utf-8")
        (tmp_path / "time_exception_allowlist.json").write_text(
            json.dumps({fp: {"rule": "PY_DIRECT_NOW", "repo": "tmp", "file": "app.py", "symbol": "tick", "reason": "t", "boundary_type": "x", "owner": "t", "review_after": "2099-01-01"}}),
            encoding="utf-8",
        )
        r = _run(tmp_path, "--check")
        assert r.returncode == 0, r.stdout

    def test_orphan_allowlist_fail(self, tmp_path):
        _tree(tmp_path, {"app.py": SRC_CLEAN})
        (tmp_path / "time_debt_baseline.json").write_text("{}", encoding="utf-8")
        (tmp_path / "time_exception_allowlist.json").write_text(
            json.dumps({"deadfp": {"rule": "PY_DIRECT_NOW", "repo": "tmp", "file": "x", "symbol": "x", "reason": "x", "boundary_type": "x", "owner": "t", "review_after": "2099-01-01"}}),
            encoding="utf-8",
        )
        r = _run(tmp_path, "--check")
        assert r.returncode == 1
        assert "ORPHAN ALLOWLIST" in r.stdout

    def test_baseline_intersect_allowlist_fail(self, tmp_path):
        _tree(tmp_path, {"app.py": SRC_NOW})
        cur = _capture(tmp_path)
        fp = next(iter(cur))
        (tmp_path / "time_exception_allowlist.json").write_text(
            json.dumps({fp: {"rule": "PY_DIRECT_NOW", "repo": "tmp", "file": "app.py", "symbol": "tick", "reason": "x", "boundary_type": "x", "owner": "t", "review_after": "2099-01-01"}}),
            encoding="utf-8",
        )
        r = _run(tmp_path, "--check")
        assert r.returncode == 1
        assert "INVALID POLICY" in r.stdout

    def test_reintroduce_after_removal_fail(self, tmp_path):
        _tree(tmp_path, {"app.py": SRC_CLEAN})
        (tmp_path / "time_debt_baseline.json").write_text("{}", encoding="utf-8")
        assert _run(tmp_path, "--check").returncode == 0
        (tmp_path / "app.py").write_text(SRC_NOW, encoding="utf-8")
        r = _run(tmp_path, "--check")
        assert r.returncode == 1
        assert "NEW " in r.stdout


class TestExpand:
    def test_target_ref_unavailable_fail(self, tmp_path):
        _tree(tmp_path, {"app.py": SRC_CLEAN})
        _init_git(tmp_path)
        (tmp_path / "time_debt_baseline.json").write_text("{}", encoding="utf-8")
        r = _run(tmp_path, "--check-expand", "missing-ref")
        assert r.returncode == 1
        assert "TARGET REF UNAVAILABLE" in r.stdout

    def test_true_bootstrap_pass(self, tmp_path):
        _tree(tmp_path, {"app.py": SRC_CLEAN})
        _init_git(tmp_path)
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-qm", "pre-guard")
        (tmp_path / "time_debt_baseline.json").write_text("{}", encoding="utf-8")
        r = _run(tmp_path, "--check-expand", "HEAD")
        assert r.returncode == 0, r.stdout
        assert "BASELINE BOOTSTRAP" in r.stdout

    def test_target_guard_baseline_missing_fail(self, tmp_path):
        _tree(tmp_path, {"app.py": SRC_CLEAN, "scripts/check_time_contract.py": GUARD_MARKER})
        _init_git(tmp_path)
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-qm", "guard-no-baseline")
        r = _run(tmp_path, "--check-expand", "HEAD")
        assert r.returncode == 1
        assert "upstream reset" in r.stdout

    def test_pr_baseline_delete_fail(self, tmp_path):
        _tree(tmp_path, {"app.py": SRC_NOW, "scripts/check_time_contract.py": GUARD_MARKER})
        _init_git(tmp_path)
        _capture(tmp_path)
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-qm", "with-baseline")
        (tmp_path / "time_debt_baseline.json").unlink()
        r = _run(tmp_path, "--check-expand", "HEAD")
        assert r.returncode == 1
        assert "PR delete reset" in r.stdout

    def test_baseline_new_fp_fail(self, tmp_path):
        _tree(tmp_path, {"app.py": SRC_NOW, "scripts/check_time_contract.py": GUARD_MARKER})
        _init_git(tmp_path)
        _capture(tmp_path)
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-qm", "base")
        (tmp_path / "app.py").write_text(SRC_TWO, encoding="utf-8")
        extra = _scan(tmp_path)
        (tmp_path / "time_debt_baseline.json").write_text(
            json.dumps({fp: {"fp": fp, "count": c} for fp, c in extra.items()}),
            encoding="utf-8",
        )
        r = _run(tmp_path, "--check-expand", "HEAD")
        assert r.returncode == 1
        assert "debt NEW" in r.stdout or "debt count+" in r.stdout

    def test_baseline_count_plus_fail(self, tmp_path):
        _tree(tmp_path, {"app.py": SRC_NOW, "scripts/check_time_contract.py": GUARD_MARKER})
        _init_git(tmp_path)
        cur = _capture(tmp_path)
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-qm", "base")
        fp = next(iter(cur))
        (tmp_path / "time_debt_baseline.json").write_text(
            json.dumps({fp: {"fp": fp, "count": cur[fp] + 1}}),
            encoding="utf-8",
        )
        r = _run(tmp_path, "--check-expand", "HEAD")
        assert r.returncode == 1
        assert "debt count+" in r.stdout

    def test_allowlist_new_fail(self, tmp_path):
        _tree(tmp_path, {"app.py": SRC_NOW, "scripts/check_time_contract.py": GUARD_MARKER})
        _init_git(tmp_path)
        _capture(tmp_path)
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-qm", "base")
        (tmp_path / "time_exception_allowlist.json").write_text(
            json.dumps({"newfp": {"rule": "PY_DIRECT_NOW", "repo": "tmp", "file": "x", "symbol": "x", "reason": "x", "boundary_type": "x", "owner": "t", "review_after": "2099-01-01"}}),
            encoding="utf-8",
        )
        r = _run(tmp_path, "--check-expand", "HEAD")
        assert r.returncode == 1
        assert "allowlist NEW" in r.stdout

    def test_bootstrap_allowlist_nonempty_fail(self, tmp_path):
        _tree(tmp_path, {"app.py": SRC_CLEAN})
        _init_git(tmp_path)
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-qm", "pre")
        (tmp_path / "time_debt_baseline.json").write_text("{}", encoding="utf-8")
        (tmp_path / "time_exception_allowlist.json").write_text(
            json.dumps({"sneak": {"rule": "PY_DIRECT_NOW", "repo": "tmp", "file": "x", "symbol": "x", "reason": "x", "boundary_type": "x", "owner": "t", "review_after": "2099-01-01"}}),
            encoding="utf-8",
        )
        r = _run(tmp_path, "--check-expand", "HEAD")
        assert r.returncode == 1
        assert "BOOTSTRAP FAIL" in r.stdout

    def test_unchanged_pass(self, tmp_path):
        _tree(tmp_path, {"app.py": SRC_NOW, "scripts/check_time_contract.py": GUARD_MARKER})
        _init_git(tmp_path)
        _capture(tmp_path)
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-qm", "base")
        r = _run(tmp_path, "--check-expand", "HEAD")
        assert r.returncode == 0, r.stdout
        assert "baseline non-expansion OK" in r.stdout

    def test_shrink_pass(self, tmp_path):
        _tree(tmp_path, {"app.py": SRC_TWO, "scripts/check_time_contract.py": GUARD_MARKER})
        _init_git(tmp_path)
        _capture(tmp_path)
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-qm", "base")
        (tmp_path / "app.py").write_text(SRC_NOW, encoding="utf-8")
        _capture(tmp_path)
        r = _run(tmp_path, "--check-expand", "HEAD")
        assert r.returncode == 0, r.stdout


class TestCoverage:
    DETECT_PY = '''
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo
import pytz
def tick():
    datetime.now()
    datetime.utcnow()
    datetime.today()
    date.today()
    timezone.utc
    datetime.timezone.utc
    ZoneInfo("UTC")
    pytz.UTC
'''
    DETECT_SQL = """
CREATE TABLE t (ts timestamp without time zone);
SELECT localtimestamp, current_date;
SELECT x AT TIME ZONE 'UTC';
SELECT timezone('UTC', x);
"""
    COMMENT_PY = '''
# datetime.now() datetime.utcnow() datetime.today() date.today() timezone.utc ZoneInfo("UTC") pytz.UTC
def tick():
    return 1
'''
    COMMENT_SQL = """
-- timestamp without time zone localtimestamp current_date AT TIME ZONE 'UTC' timezone('UTC', x)
SELECT 1;
"""

    def test_detect_each_rule(self, tmp_path):
        _tree(tmp_path, {"app.py": self.DETECT_PY, "schema.sql": self.DETECT_SQL})
        # import scanner helpers in-process with TIME_CONTRACT_ROOT
        env = {**os.environ, "TIME_CONTRACT_ROOT": str(tmp_path)}
        code = r"""
import json, sys
sys.path.insert(0, r"%s")
import importlib.util
spec = importlib.util.spec_from_file_location("g", r"%s")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
hits=[]
for rel,src in [("app.py", open("app.py",encoding="utf-8").read()), ("schema.sql", open("schema.sql",encoding="utf-8").read())]:
    fn = m.scan_py if rel.endswith(".py") else m.scan_sql
    hits.extend(fn(rel, src))
print(json.dumps([r for r,_ in hits]))
""" % (str(tmp_path).replace("\\", "\\\\"), str(GUARD).replace("\\", "\\\\"))
        r = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(tmp_path),
            env=env,
            capture_output=True,
            text=True,
        )
        assert r.returncode == 0, r.stderr
        rules = json.loads(r.stdout)
        for need in (
            "PY_DIRECT_NOW", "PY_UTCNOW", "PY_DATETIME_TODAY", "PY_DATE_TODAY",
            "PY_EXPLICIT_UTC", "PY_ZONEINFO_UTC", "PY_PYTZ_UTC",
            "SQL_NEW_NAIVE_TIMESTAMP", "SQL_LOCALTIMESTAMP", "SQL_CURRENT_DATE",
            "SQL_AT_TIME_ZONE_UTC", "SQL_TIMEZONE_UTC",
        ):
            assert need in rules, (need, rules)
        # timezone.utc + datetime.timezone.utc both EXPLICIT_UTC
        assert rules.count("PY_EXPLICIT_UTC") >= 2

    def test_comments_not_detected(self, tmp_path):
        _tree(tmp_path, {"app.py": self.COMMENT_PY, "schema.sql": self.COMMENT_SQL})
        cur = _scan(tmp_path)
        assert cur == {}

    def test_services_time_and_tests_exempt(self, tmp_path):
        _tree(tmp_path, {
            "services/time/clock.py": SRC_NOW,
            "tests/evil.py": SRC_NOW,
            "app.py": SRC_CLEAN,
        })
        cur = _scan(tmp_path)
        assert cur == {}


class TestStability:
    def _fps(self, tmp_path, src: str) -> dict:
        _tree(tmp_path, {"app.py": src})
        return _scan(tmp_path)

    def test_unrelated_line_same(self, tmp_path):
        a = self._fps(tmp_path, SRC_NOW)
        b = self._fps(tmp_path / "b", "x = 1\n" + SRC_NOW)
        assert set(a) == set(b)

    def test_whitespace_same(self, tmp_path):
        a = self._fps(tmp_path, SRC_NOW)
        b = self._fps(tmp_path / "b", "from datetime import datetime\ndef tick():\n    return datetime.now( )\n")
        assert set(a) == set(b)

    def test_comment_same(self, tmp_path):
        a = self._fps(tmp_path, SRC_NOW)
        b = self._fps(tmp_path / "b", "# note\n" + SRC_NOW)
        assert set(a) == set(b)

    def test_function_rename_same(self, tmp_path):
        a = self._fps(tmp_path, SRC_NOW)
        b = self._fps(tmp_path / "b", "from datetime import datetime\ndef tock():\n    return datetime.now()\n")
        assert set(a) == set(b)

    def test_token_now_to_utcnow_new(self, tmp_path):
        a = self._fps(tmp_path, SRC_NOW)
        b = self._fps(tmp_path / "b", "from datetime import datetime\ndef tick():\n    return datetime.utcnow()\n")
        assert set(a).isdisjoint(set(b))
        assert b

    def test_duplicate_count_two(self, tmp_path):
        a = self._fps(tmp_path, SRC_TWO)
        assert len(a) == 1
        assert next(iter(a.values())) == 2


SRC_UTC_NOW = (
    "from datetime import datetime, timezone\n"
    "def f():\n"
    "    return datetime.now(timezone.utc)\n"
)


def test_archive_quarantine_exempt(tmp_path):
    _tree(tmp_path, {"_archive/routers_20260608/x.py": SRC_UTC_NOW})
    cur = _scan(tmp_path)
    assert sum(cur.values()) == 0


def test_active_runtime_protected(tmp_path):
    _tree(tmp_path, {"routers/x.py": SRC_UTC_NOW})
    cur = _scan(tmp_path)
    assert sum(cur.values()) > 0

