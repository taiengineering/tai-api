"""WO-QA-COST-001B AUTO-A01~A08 — CI workflow structural contract.

Ensures .github/workflows/ci.yml never drifts back to auto-trigger.
"""
from __future__ import annotations

import pathlib
import re

import pytest

_CI_PATH = pathlib.Path(__file__).parents[1] / ".github" / "workflows" / "ci.yml"


def _load() -> str:
    return _CI_PATH.read_text(encoding="utf-8")


def test_AUTO_A01_workflow_dispatch_present():
    """ci.yml must declare workflow_dispatch trigger."""
    assert "workflow_dispatch" in _load()


def test_AUTO_A02_no_push_trigger():
    """ci.yml must NOT have a push trigger (auto-CI off)."""
    content = _load()
    # Allow 'push' only inside comments or step names, not as a YAML trigger key
    for line in content.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        # Trigger keys appear as '  push:' with optional leading spaces, no deeper indent
        if re.match(r"^\s{0,4}push\s*:", line):
            pytest.fail(f"push trigger found: {line!r}")


def test_AUTO_A03_no_pull_request_trigger():
    """ci.yml must NOT have a pull_request trigger."""
    content = _load()
    for line in content.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if re.match(r"^\s{0,4}pull_request\s*:", line):
            pytest.fail(f"pull_request trigger found: {line!r}")


def test_AUTO_A04_no_schedule_trigger():
    """ci.yml must NOT have a schedule trigger."""
    content = _load()
    for line in content.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if re.match(r"^\s{0,4}schedule\s*:", line):
            pytest.fail(f"schedule trigger found: {line!r}")


def test_AUTO_A05_concurrency_present():
    """ci.yml must declare concurrency."""
    assert "concurrency:" in _load()


def test_AUTO_A06_cancel_in_progress_true():
    """concurrency.cancel-in-progress must be true."""
    content = _load()
    assert "cancel-in-progress: true" in content, (
        "cancel-in-progress: true not found in ci.yml"
    )


def test_AUTO_A07_timeout_present():
    """unit-test job must declare timeout-minutes."""
    assert "timeout-minutes:" in _load()


def test_AUTO_A08_single_active_job():
    """Only one active (non-if:false) job: unit-test."""
    content = _load()
    # Count job-level keys (lines like '  job-name:' under jobs:)
    in_jobs = False
    active_jobs = []
    lines = content.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == "jobs:":
            in_jobs = True
            continue
        if in_jobs:
            m = re.match(r"^  ([a-zA-Z0-9_-]+)\s*:", line)
            if m:
                job_name = m.group(1)
                # Check if the next lines contain 'if: false' within 3 lines
                next_block = " ".join(lines[i+1:i+4])
                if "if: false" not in next_block:
                    active_jobs.append(job_name)
    assert active_jobs == ["unit-test"], (
        f"Expected exactly ['unit-test'] active job, got {active_jobs}"
    )
