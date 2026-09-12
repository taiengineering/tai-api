"""Stage3 thin daily trigger — no business logic in the runner."""
from __future__ import annotations

import importlib.util
import inspect
import runpy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_daily_operation_schedule_materializer.py"


def _load_runner_module():
    spec = importlib.util.spec_from_file_location(
        "run_daily_operation_schedule_materializer", RUNNER
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_T1_success_result_exit_0(monkeypatch):
    mod = _load_runner_module()
    monkeypatch.setattr(
        "services.inspection_sets_svc.schedules.generate_schedules_all",
        lambda: {"status": "success", "data": {"processed": 1}},
    )
    # patch import target used inside main
    import services.inspection_sets_svc.schedules as S

    monkeypatch.setattr(
        S,
        "generate_schedules_all",
        lambda: {"status": "success", "data": {"processed": 1}},
    )
    assert mod.main() == 0


def test_T2_generator_exception_nonzero(monkeypatch):
    mod = _load_runner_module()
    import services.inspection_sets_svc.schedules as S

    def boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(S, "generate_schedules_all", boom)
    assert mod.main() == 1


def test_T3_status_not_success_nonzero(monkeypatch):
    mod = _load_runner_module()
    import services.inspection_sets_svc.schedules as S

    monkeypatch.setattr(
        S, "generate_schedules_all", lambda: {"status": "error", "message": "x"}
    )
    assert mod.main() == 1


def test_T4_calls_generate_schedules_all_exactly_once(monkeypatch):
    mod = _load_runner_module()
    import services.inspection_sets_svc.schedules as S

    calls = {"n": 0}

    def once():
        calls["n"] += 1
        return {"status": "success", "data": {}}

    monkeypatch.setattr(S, "generate_schedules_all", once)
    assert mod.main() == 0
    assert calls["n"] == 1


def test_T5_runner_has_no_business_logic():
    src = RUNNER.read_text(encoding="utf-8")
    forbidden = [
        "work_schedules",
        "active_yn",
        "operation_time_rule",
        "planned_date",
        "for fac in",
        "factories",
        "stale_",
        "reactivat",
        "_child_linked",
        "upsert",
        ".delete(",
    ]
    for token in forbidden:
        assert token not in src, f"forbidden token in runner: {token}"
    assert "from services.inspection_sets_svc.schedules import generate_schedules_all" in src
    assert "result = generate_schedules_all()" in src
