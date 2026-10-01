"""SEM-P0-01A-R4 — CST process projector + runtime injection tests.

Covers:
  T01-T08 : project_cst_process_codes (pure projector)
  T09-T13 : _load_site_process_work_type_codes (fail-closed reader)
  T14-T17 : run_safe_construction_leg integration (process projection wired)
"""
import copy
import pytest

from services.cst_process_projector import project_cst_process_codes, _APPROVED_PROCESS_MAPPINGS_V1
from services.safe_construction_leg_runtime import (
    ConstructionProcessSourceLoadError,
    _load_site_process_work_type_codes,
    run_safe_construction_leg,
    SAFE_CST_OVERRIDE_FIELDS,
)
import services.safe_construction_leg_runtime as cst_rt


# ── FakeSB (supports eq + in_ for multi-table tests) ──────────────────────────
class _Res:
    def __init__(s, d): s.data = d

class _Q:
    def __init__(s, store, c):
        s.store = store; s.c = c; s._f = {}; s._in = {}
    def select(s, *a, **k): return s
    def eq(s, col, val): s._f[col] = val; return s
    def in_(s, col, vals): s._in[col] = set(vals); return s
    def limit(s, n): return s
    def order(s, *a, **k): return s
    def execute(s):
        s.c["reads"] += 1
        rows = [
            r for r in s.store
            if all(r.get(k) == v for k, v in s._f.items())
            and all(r.get(k) in vs for k, vs in s._in.items())
        ]
        return _Res(copy.deepcopy(rows))

class _T:
    def __init__(s, name, store, c): s.name = name; s.store = store; s.c = c
    def select(s, *a, **k): return _Q(s.store, s.c)

class FakeSB:
    def __init__(s, **stores):
        s.stores = {
            "construction_sites": [],
            "construction_workers": [],
            "construction_site_processes": [],
            "kcsc_process_master": [],
            "factory_work_facts": [],
            "factory_materials": [],
        }
        s.stores.update(stores)
        s.counters = {"writes": 0, "reads": 0}
    def table(s, n): s.stores.setdefault(n, []); return _T(n, s.stores[n], s.counters)

class BrokenSB:
    """Raises on every table().select()...execute()."""
    def table(s, n): return _BrokenQ()

class _BrokenQ:
    def select(s, *a, **k): return s
    def eq(s, *a, **k): return s
    def in_(s, *a, **k): return s
    def execute(s): raise RuntimeError("simulated DB failure")


def _site(**kw):
    base = {"id": "S1", "factory_id": "F1", "total_workers": 30, "direct_workers": 10,
            "subcon_workers": 20, "site_type": "BUILDING", "site_address": "서울", "contract_amount": 50}
    base.update(kw)
    return base

def _sb(**extra_stores):
    return FakeSB(construction_sites=[_site()], **extra_stores)

def _sb_with_process(work_type_code: str, *, site_id="S1", proc_id="P1", master_id="M1"):
    return FakeSB(
        construction_sites=[_site()],
        construction_site_processes=[
            {"id": proc_id, "site_id": site_id, "kcsc_process_id": master_id, "is_active": True}
        ],
        kcsc_process_master=[
            {"id": master_id, "work_type_code": work_type_code, "is_active": True}
        ],
    )

def _patch_leg(monkeypatch, capture):
    def fake_run_leg(step1):
        capture["called"] += 1
        capture["step1"] = step1
        return {"engine_family": "LEG", "sector": "CONSTRUCTION", "status_ok": True}
    monkeypatch.setattr(cst_rt, "run_leg_diagnosis", fake_run_leg)


# ── T01-T08 : pure projector ───────────────────────────────────────────────────

def test_T01_empty_codes():
    assert project_cst_process_codes([]) == {}

def test_T02_confined_space():
    result = project_cst_process_codes(["CONFINED_SPACE"])
    assert result == {"performs_confined_space_work": True}

def test_T03_temp_electric():
    result = project_cst_process_codes(["TEMP_ELECTRIC"])
    assert result == {"performs_electrical_work": True}

def test_T04_both_mappings():
    result = project_cst_process_codes(["CONFINED_SPACE", "TEMP_ELECTRIC"])
    assert result == {"performs_confined_space_work": True, "performs_electrical_work": True}

def test_T05_unknown_code_omitted():
    result = project_cst_process_codes(["BLASTING"])
    assert result == {}

def test_T06_mixed_known_unknown():
    result = project_cst_process_codes(["CONFINED_SPACE", "BLASTING", "EXCAVATION"])
    assert result == {"performs_confined_space_work": True}

def test_T07_duplicate_codes_idempotent():
    result = project_cst_process_codes(["CONFINED_SPACE", "CONFINED_SPACE"])
    assert result == {"performs_confined_space_work": True}

def test_T08_none_in_list_skipped():
    result = project_cst_process_codes([None, "CONFINED_SPACE"])
    assert result == {"performs_confined_space_work": True}


# ── T09-T13 : _load_site_process_work_type_codes ──────────────────────────────

def test_T09_no_processes_returns_empty():
    sb = _sb()  # construction_site_processes = []
    result = _load_site_process_work_type_codes(sb, "S1")
    assert result == []

def test_T10_confined_space_process_returns_code():
    sb = _sb_with_process("CONFINED_SPACE")
    result = _load_site_process_work_type_codes(sb, "S1")
    assert result == ["CONFINED_SPACE"]

def test_T10b_temp_electric_process_returns_code():
    sb = _sb_with_process("TEMP_ELECTRIC")
    result = _load_site_process_work_type_codes(sb, "S1")
    assert result == ["TEMP_ELECTRIC"]

def test_T11_supabase_none_raises():
    with pytest.raises(ConstructionProcessSourceLoadError) as exc_info:
        _load_site_process_work_type_codes(None, "S1")
    assert exc_info.value.site_id == "S1"
    assert exc_info.value.code == "CST_PROCESS_SOURCE_UNAVAILABLE"

def test_T12_processes_query_failure_raises():
    class _FailOnProcesses:
        def table(s, n):
            if n == "construction_site_processes":
                return _BrokenQ()
            return _T(n, [], {"writes": 0, "reads": 0})
    with pytest.raises(ConstructionProcessSourceLoadError):
        _load_site_process_work_type_codes(_FailOnProcesses(), "S1")

def test_T13_master_query_failure_raises():
    class _FailOnMaster:
        def __init__(s):
            s._proc_store = [
                {"id": "P1", "site_id": "S1", "kcsc_process_id": "M1", "is_active": True}
            ]
        def table(s, n):
            if n == "kcsc_process_master":
                return _BrokenQ()
            c = {"reads": 0, "writes": 0}
            return _T(n, s._proc_store, c)
    with pytest.raises(ConstructionProcessSourceLoadError):
        _load_site_process_work_type_codes(_FailOnMaster(), "S1")


# ── T14-T17 : run_safe_construction_leg integration ───────────────────────────

def test_T14_confined_space_injected_into_leg(monkeypatch):
    cap = {"called": 0, "step1": None}
    _patch_leg(monkeypatch, cap)
    sb = _sb_with_process("CONFINED_SPACE")
    out = run_safe_construction_leg(sb, "S1", {})
    assert cap["called"] == 1
    assert cap["step1"].input.get("performs_confined_space_work") is True
    assert "performs_confined_space_work" not in out["unresolved_fields"]

def test_T15_no_processes_no_injection(monkeypatch):
    cap = {"called": 0, "step1": None}
    _patch_leg(monkeypatch, cap)
    sb = _sb()  # no processes
    run_safe_construction_leg(sb, "S1", {})
    assert "performs_confined_space_work" not in cap["step1"].input
    assert "performs_electrical_work" not in cap["step1"].input

def test_T16_process_source_failure_leg_not_called(monkeypatch):
    cap = {"called": 0}
    _patch_leg(monkeypatch, cap)

    def _fail_reader(supabase, site_id):
        raise ConstructionProcessSourceLoadError("simulated DB failure", site_id=site_id)

    monkeypatch.setattr(cst_rt, "_load_site_process_work_type_codes", _fail_reader)
    with pytest.raises(ConstructionProcessSourceLoadError):
        run_safe_construction_leg(_sb(), "S1", {})
    assert cap["called"] == 0

def test_T17_performs_fields_not_in_override_allowlist():
    assert "performs_confined_space_work" not in SAFE_CST_OVERRIDE_FIELDS
    assert "performs_electrical_work" not in SAFE_CST_OVERRIDE_FIELDS


# ── T18-T19 : malformed payload hardening ────────────────────────────────────

class _MalformedRes:
    data = {"unexpected": "dict"}  # non-list payload

class _MalformedQ:
    def select(s, *a, **k): return s
    def eq(s, *a, **k): return s
    def in_(s, *a, **k): return s
    def limit(s, n): return s
    def execute(s): return _MalformedRes()

def test_T18_malformed_process_payload_raises():
    class _MalformedProcessSB:
        def table(s, n):
            if n == "construction_site_processes":
                return _MalformedQ()
            return _T(n, [], {"writes": 0, "reads": 0})
    with pytest.raises(ConstructionProcessSourceLoadError):
        _load_site_process_work_type_codes(_MalformedProcessSB(), "S1")

def test_T19_malformed_master_payload_raises():
    class _MalformedMasterSB:
        def __init__(s):
            s._proc_store = [
                {"id": "P1", "site_id": "S1", "kcsc_process_id": "M1", "is_active": True}
            ]
        def table(s, n):
            if n == "kcsc_process_master":
                return _MalformedQ()
            c = {"reads": 0, "writes": 0}
            return _T(n, s._proc_store, c)
    with pytest.raises(ConstructionProcessSourceLoadError):
        _load_site_process_work_type_codes(_MalformedMasterSB(), "S1")
