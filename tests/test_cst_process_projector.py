"""SEM-P0-01A-R4 + WO-BLK008 + WO-BLK009C — CST process/work projector + runtime injection tests.

Covers:
  T01-T08 : project_cst_process_codes (pure projector) [SEM-P0-01A-R4]
  T09-T13 : _load_site_process_work_type_codes (fail-closed reader)
  T14-T17 : run_safe_construction_leg integration (process projection wired)
  T18-T19 : malformed payload hardening
  T20-T26 : BLK-008 EXCAVATION → has_excavation mapping
  T27-T33 : BLK-009 BLASTING → has_blasting mapping (work namespace)
"""
import copy
import pytest

from services.cst_process_projector import (
    project_cst_process_codes,
    project_cst_work_codes,
    _APPROVED_PROCESS_MAPPINGS_V1,
)
from services.safe_construction_leg_runtime import (
    ConstructionProcessSourceLoadError,
    ConstructionWorkSourceLoadError,
    _load_site_process_work_type_codes,
    _load_site_work_type_codes,
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
            "construction_works": [],
            "kcsc_work_master": [],
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

def _sb_with_work(work_type_code: str, *, site_id="S1", work_id="W1", master_id="M2"):
    return FakeSB(
        construction_sites=[_site()],
        construction_works=[
            {"id": work_id, "site_id": site_id, "work_master_id": master_id, "is_active": True}
        ],
        kcsc_work_master=[
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
    assert result == {"performs_confined_space_work": True, "has_excavation": True}

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


# ── T20-T26 : BLK-008 EXCAVATION → has_excavation ────────────────────────────

def test_T20_blk008_excavation_positive():
    """T20: EXCAVATION code → has_excavation = True."""
    result = project_cst_process_codes(["EXCAVATION"])
    assert result == {"has_excavation": True}

def test_T21_blk008_confined_space_no_excavation():
    """T21: CONFINED_SPACE → has_excavation absent."""
    result = project_cst_process_codes(["CONFINED_SPACE"])
    assert "has_excavation" not in result
    assert result.get("performs_confined_space_work") is True

def test_T22_blk008_temp_electric_regression():
    """T22: TEMP_ELECTRIC → performs_electrical_work, has_excavation absent."""
    result = project_cst_process_codes(["TEMP_ELECTRIC"])
    assert result == {"performs_electrical_work": True}
    assert "has_excavation" not in result

def test_T23_blk008_confined_space_regression():
    """T23: CONFINED_SPACE → performs_confined_space_work, has_excavation absent."""
    result = project_cst_process_codes(["CONFINED_SPACE"])
    assert result == {"performs_confined_space_work": True}
    assert "has_excavation" not in result

def test_T24_blk008_unknown_code_empty():
    """T24: unrecognized code → empty dict."""
    result = project_cst_process_codes(["UNKNOWN_CODE"])
    assert result == {}

def test_T25_blk008_namespace_guard():
    """T25: EXCAVATION from wrong namespace (kcsc_work_master) produces nothing.

    project_cst_process_codes() receives only work_type_code strings, not
    (table, code) tuples. The caller (_load_site_process_work_type_codes) reads
    exclusively from kcsc_process_master. This test confirms the dict lookup
    uses the exact (kcsc_process_master, code) key — a wrong-table key is absent.
    """
    wrong_table_key = ("kcsc_work_master", "EXCAVATION")
    assert wrong_table_key not in _APPROVED_PROCESS_MAPPINGS_V1
    correct_key = ("kcsc_process_master", "EXCAVATION")
    assert correct_key in _APPROVED_PROCESS_MAPPINGS_V1

def test_T26_blk008_registry_count():
    """T26: registry has exactly 4 entries after BLK-009 extension (BLK-008 updated)."""
    assert len(_APPROVED_PROCESS_MAPPINGS_V1) == 4
    assert ("kcsc_process_master", "EXCAVATION") in _APPROVED_PROCESS_MAPPINGS_V1
    assert _APPROVED_PROCESS_MAPPINGS_V1[("kcsc_process_master", "EXCAVATION")] == "has_excavation"


# ── T27-T33 : BLK-009 BLASTING → has_blasting (work namespace) ───────────────

def test_T27_blk009_blasting_positive():
    """T27: BLASTING code (kcsc_work_master) → has_blasting = True."""
    result = project_cst_work_codes(["BLASTING"])
    assert result == {"has_blasting": True}

def test_T28_blk009_work_namespace_unknown_code():
    """T28: unrecognized code in work namespace → empty dict."""
    result = project_cst_work_codes(["EXCAVATION"])
    assert result == {}

def test_T29_blk009_namespace_isolation_process_side():
    """T29: BLASTING in process namespace produces nothing (cross-namespace guard)."""
    result = project_cst_process_codes(["BLASTING"])
    assert result == {}

def test_T30_blk009_registry_count():
    """T30: registry has exactly 4 entries after BLK-009 extension."""
    assert len(_APPROVED_PROCESS_MAPPINGS_V1) == 4
    assert ("kcsc_work_master", "BLASTING") in _APPROVED_PROCESS_MAPPINGS_V1
    assert _APPROVED_PROCESS_MAPPINGS_V1[("kcsc_work_master", "BLASTING")] == "has_blasting"

def test_T31_blk009_registry_entry():
    """T31: ("kcsc_work_master","BLASTING") → "has_blasting" confirmed."""
    assert _APPROVED_PROCESS_MAPPINGS_V1[("kcsc_work_master", "BLASTING")] == "has_blasting"

def test_T32_blk009_process_regression():
    """T32: process-namespace entries unchanged after BLK-009."""
    assert _APPROVED_PROCESS_MAPPINGS_V1[("kcsc_process_master", "CONFINED_SPACE")] == "performs_confined_space_work"
    assert _APPROVED_PROCESS_MAPPINGS_V1[("kcsc_process_master", "TEMP_ELECTRIC")] == "performs_electrical_work"
    assert _APPROVED_PROCESS_MAPPINGS_V1[("kcsc_process_master", "EXCAVATION")] == "has_excavation"

def test_T33_blk009_namespace_separation():
    """T33: same code name, different namespace → different result."""
    assert project_cst_process_codes(["BLASTING"]) == {}
    assert project_cst_work_codes(["BLASTING"]) == {"has_blasting": True}
    assert project_cst_process_codes(["EXCAVATION"]) == {"has_excavation": True}
    assert project_cst_work_codes(["EXCAVATION"]) == {}


# ── T34-T38 : BLK-009 runtime integration ────────────────────────────────────

def test_T34_blk009_blasting_injected_into_leg(monkeypatch):
    """T34: BLASTING work row → has_blasting injected into LEG step1."""
    cap = {"called": 0, "step1": None}
    _patch_leg(monkeypatch, cap)
    sb = _sb_with_work("BLASTING")
    out = run_safe_construction_leg(sb, "S1", {})
    assert cap["called"] == 1
    assert cap["step1"].input.get("has_blasting") is True
    assert "has_blasting" not in out["unresolved_fields"]

def test_T35_blk009_no_work_rows_no_injection(monkeypatch):
    """T35: no work rows → has_blasting absent from step1."""
    cap = {"called": 0, "step1": None}
    _patch_leg(monkeypatch, cap)
    sb = _sb()
    run_safe_construction_leg(sb, "S1", {})
    assert "has_blasting" not in cap["step1"].input

def test_T36_blk009_work_source_failure_leg_not_called(monkeypatch):
    """T36: work source DB failure → ConstructionWorkSourceLoadError, LEG not called."""
    cap = {"called": 0}
    _patch_leg(monkeypatch, cap)

    def _fail_work_reader(supabase, site_id):
        raise ConstructionWorkSourceLoadError("simulated DB failure", site_id=site_id)

    monkeypatch.setattr(cst_rt, "_load_site_work_type_codes", _fail_work_reader)
    with pytest.raises(ConstructionWorkSourceLoadError):
        run_safe_construction_leg(_sb(), "S1", {})
    assert cap["called"] == 0

def test_T37_blk009_has_blasting_in_override_allowlist():
    """T37: has_blasting IS in SAFE_CST_OVERRIDE_FIELDS (in RUNTIME20).

    has_blasting is a RUNTIME_INPUT_FIELDS member — consumers can provide it.
    B-prime-prime work projection writes it with higher priority (source data wins).
    This is the same pattern as has_excavation (BLK-008). Contrast with
    performs_confined_space_work (MAP-01) which is NOT in RUNTIME20.
    """
    assert "has_blasting" in SAFE_CST_OVERRIDE_FIELDS
    assert "has_excavation" in SAFE_CST_OVERRIDE_FIELDS
    assert "performs_confined_space_work" not in SAFE_CST_OVERRIDE_FIELDS

def test_T38_blk009_process_injection_regression(monkeypatch):
    """T38: BLASTING work + CONFINED_SPACE process → both injected independently."""
    cap = {"called": 0, "step1": None}
    _patch_leg(monkeypatch, cap)
    sb = FakeSB(
        construction_sites=[_site()],
        construction_site_processes=[
            {"id": "P1", "site_id": "S1", "kcsc_process_id": "M1", "is_active": True}
        ],
        kcsc_process_master=[
            {"id": "M1", "work_type_code": "CONFINED_SPACE", "is_active": True}
        ],
        construction_works=[
            {"id": "W1", "site_id": "S1", "work_master_id": "M2", "is_active": True}
        ],
        kcsc_work_master=[
            {"id": "M2", "work_type_code": "BLASTING", "is_active": True}
        ],
    )
    out = run_safe_construction_leg(sb, "S1", {})
    assert cap["step1"].input.get("performs_confined_space_work") is True
    assert cap["step1"].input.get("has_blasting") is True
