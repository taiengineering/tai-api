"""WO-DUAL-CST-STEP2-IMPLEMENT-001 GATE-1 — SAFE CONSTRUCTION assembler + LEG runtime tests.

mock 은 CURRENT PRODUCTION PHYSICAL CONTRACT(construction_sites 실제 컬럼) 기준.
run_leg_diagnosis / build_facility 는 monkeypatch(실 LEG 미호출).
"""
import copy
import pytest
from pydantic import ValidationError

from services.safe_construction_canonical_assembler import (
    assemble_construction_marketing_contract, TARGET_FIELDS, CONTRACT_VERSION, SECTOR,
    RUNTIME_INPUT_FIELDS,
)
import services.safe_construction_leg_runtime as cst_rt
from services.safe_construction_leg_runtime import (
    run_safe_construction_leg, SAFE_CST_OVERRIDE_FIELDS, ConstructionSiteBridgeError,
)


class _Res:
    def __init__(s, d): s.data = d
class _Q:
    def __init__(s, store, c): s.store = store; s.c = c; s._f = {}
    def select(s, *a, **k): return s
    def eq(s, col, val): s._f[col] = val; return s
    def limit(s, n): return s
    def insert(s, *a, **k): s.c["writes"] += 1; return s
    def update(s, *a, **k): s.c["writes"] += 1; return s
    def delete(s, *a, **k): s.c["writes"] += 1; return s
    def execute(s):
        s.c["reads"] += 1
        rows = [r for r in s.store if all(r.get(k) == v for k, v in s._f.items())]
        return _Res(copy.deepcopy(rows))
class _T:
    def __init__(s, name, store, c): s.name = name; s.store = store; s.c = c
    def select(s, *a, **k): return _Q(s.store, s.c)
    def insert(s, *a, **k): s.c["writes"] += 1; return _Q(s.store, s.c)
    def update(s, *a, **k): s.c["writes"] += 1; return _Q(s.store, s.c)
    def delete(s, *a, **k): s.c["writes"] += 1; return _Q(s.store, s.c)
class FakeSB:
    def __init__(s, **stores):
        s.stores = {"construction_sites": [], "construction_workers": []}
        s.stores.update(stores)
        s.counters = {"writes": 0, "reads": 0}
    def table(s, n): s.stores.setdefault(n, []); return _T(n, s.stores[n], s.counters)

def _site(**kw):
    base = {"id": "S1", "factory_id": "F1", "total_workers": 30, "direct_workers": 10,
            "subcon_workers": 20, "site_type": "BUILDING", "site_address": "서울", "contract_amount": 50}
    base.update(kw)
    return base

def _sb(site=None, **kw):
    row = [_site(**(site or {}))] if site is not None else [_site()]
    return FakeSB(construction_sites=row, **kw)


# ── canonical denominator ──────────────────────────────────────────────
def test_canonical_27_exact():
    r = assemble_construction_marketing_contract(_sb(), "S1")
    assert list(r["values"].keys()) == TARGET_FIELDS
    assert len(r["values"]) == 27
    assert r["contract_version"] == CONTRACT_VERSION and r["sector"] == SECTOR
    assert r["factory_id"] == "F1"


# ── A. worker source (total_workers, NOT direct_workers) ───────────────
def test_A_worker_count_from_total_workers():
    r = assemble_construction_marketing_contract(
        _sb(site={"total_workers": 30, "direct_workers": 10, "subcon_workers": 20}), "S1")
    assert r["values"]["worker_count"] == 30   # NOT 10


# ── DIRECT_EXACT 4 원값 보존 ───────────────────────────────────────────
def test_direct_exact_4():
    r = assemble_construction_marketing_contract(
        _sb(site={"total_workers": 0, "site_type": "CIVIL", "site_address": "부산", "contract_amount": 0}), "S1")
    v = r["values"]
    assert v["worker_count"] == 0            # 0 보존
    assert v["construction_type"] == "CIVIL"
    assert v["project_address"] == "부산"
    assert v["project_amount"] == 0          # 0 보존(억 단위, 변환 없음)
    for f in ("worker_count", "construction_type", "project_address", "project_amount"):
        assert f not in r["unresolved_fields"]


# ── B. subcontractor derivation firewall ───────────────────────────────
def test_B_subcontractor_no_auto_derive():
    r = assemble_construction_marketing_contract(_sb(site={"subcon_workers": 20}), "S1")
    assert r["values"]["has_subcontractor"] is None       # subcon_workers>0 이어도 자동 true 금지
    assert "has_subcontractor" in r["unresolved_fields"]
    assert r["values"]["subcontractor_count"] is None
    assert "subcontractor_count" in r["unresolved_fields"]


# ── C. distinct firewall (construction_workers 조회 안 함) ──────────────
def test_C_no_distinct_count():
    sb = _sb(construction_workers=[
        {"site_id": "S1", "is_active": True, "subcontractor_id": "A"},
        {"site_id": "S1", "is_active": True, "subcontractor_id": "B"},
        {"site_id": "S1", "is_active": True, "subcontractor_id": "C"}])
    r = assemble_construction_marketing_contract(sb, "S1")
    assert r["values"]["subcontractor_count"] is None      # distinct 3 이어도 생성 금지
    assert sb.counters["reads"] == 1                       # construction_sites 만 읽음(workers 조회 0)


# ── special_work derivation firewall (assembler 는 works/kcsc 미조회) ──
def test_no_special_work_read():
    sb = _sb()
    assemble_construction_marketing_contract(sb, "S1")
    # construction_works / kcsc_work_master 조회 0 (assembler store 에 없음 = 접근 안 함)
    assert "construction_works" not in sb.stores or sb.stores.get("construction_works") == []
    # derivation 소스 부재: works/kcsc/process 테이블 조회 0 (코드 호출만 검사).
    src = open("services/safe_construction_canonical_assembler.py").read()
    assert '.table("construction_works")' not in src
    assert '.table("kcsc_work_master")' not in src
    assert '.table("construction_site_processes")' not in src
    # docstring(module + 함수) 전부 제거 후, 순수 코드에 special_work_type/hazard_type 부재.
    import re
    code = re.sub(r'"""(?:.|\n)*?"""', "", src)          # 모든 triple-quoted docstring 제거
    code = "\n".join(ln for ln in code.splitlines() if not ln.lstrip().startswith("#"))
    assert "special_work_type" not in code, "derivation source found in code"
    assert "hazard_type" not in code


# ── RUNTIME20 unresolved 초기화 ────────────────────────────────────────
def test_runtime20_unresolved_initial():
    r = assemble_construction_marketing_contract(_sb(), "S1")
    for f in RUNTIME_INPUT_FIELDS:
        assert r["values"][f] is None and f in r["unresolved_fields"], f
    assert len(RUNTIME_INPUT_FIELDS) == 20
    assert "has_subcontractor" in RUNTIME_INPUT_FIELDS
    assert "subcontractor_count" not in RUNTIME_INPUT_FIELDS


def test_unresolved_23():
    r = assemble_construction_marketing_contract(_sb(), "S1")
    assert len(r["unresolved_fields"]) == 23   # 27 - DIRECT_EXACT 4


# ── DB write 0 ─────────────────────────────────────────────────────────
def test_assembler_no_db_write():
    sb = _sb()
    assemble_construction_marketing_contract(sb, "S1")
    assert sb.counters["writes"] == 0


# ── runtime service ────────────────────────────────────────────────────
def _patch_leg(monkeypatch, capture):
    def fake_run_leg(step1):
        capture["called"] += 1
        capture["step1"] = step1
        return {"engine_family": "LEG", "sector": "CONSTRUCTION", "status_ok": True}
    monkeypatch.setattr(cst_rt, "run_leg_diagnosis", fake_run_leg)


# ── G. LEG path (run_leg_diagnosis exactly 1) ──────────────────────────
def test_G_run_leg_exactly_once(monkeypatch):
    cap = {"called": 0}
    _patch_leg(monkeypatch, cap)
    out = run_safe_construction_leg(_sb(), "S1", {})
    assert cap["called"] == 1
    assert out["contract_version"] == CONTRACT_VERSION
    assert out["full_result"]["engine_family"] == "LEG"


# ── D. explicit runtime override (false/0 보존) ────────────────────────
def test_D_explicit_override_false_zero(monkeypatch):
    cap = {"called": 0}
    _patch_leg(monkeypatch, cap)
    out = run_safe_construction_leg(
        _sb(), "S1",
        {"has_subcontractor": False, "has_excavation": True, "work_height_m": 0, "has_demolition": None})
    inp = cap["step1"].input
    assert inp["has_subcontractor"] is False          # explicit false 보존
    assert inp["has_excavation"] is True
    assert inp["work_height_m"] == 0                  # explicit 0 보존
    assert inp["has_demolition"] is None              # None=미override → canonical None 유지
    assert "has_subcontractor" not in out["unresolved_fields"]  # 명시 해소
    assert "has_demolition" in out["unresolved_fields"]         # 미override 유지


# ── override allowlist = RUNTIME20 (subcontractor_count 제외) ───────────
def test_override_allowlist_20(monkeypatch):
    cap = {"called": 0}
    _patch_leg(monkeypatch, cap)
    # subcontractor_count 는 override 대상 아님 → 넘겨도 canonical None 유지
    out = run_safe_construction_leg(_sb(), "S1", {"subcontractor_count": 5})
    assert cap["step1"].input["subcontractor_count"] is None
    assert "subcontractor_count" in out["unresolved_fields"]
    assert len(SAFE_CST_OVERRIDE_FIELDS) == 20


# ── canonical 27 불변 (override 후에도) ────────────────────────────────
def test_canonical_27_after_override(monkeypatch):
    cap = {"called": 0}
    _patch_leg(monkeypatch, cap)
    run_safe_construction_leg(_sb(), "S1", {"has_excavation": True})
    assert list(cap["step1"].input.keys()) == TARGET_FIELDS
    assert len(cap["step1"].input) == 27


# ── factory bridge fail-closed (factory 생성 0) ────────────────────────
def test_factory_bridge_fail_closed(monkeypatch):
    cap = {"called": 0}
    _patch_leg(monkeypatch, cap)
    sb = _sb(site={"factory_id": None})   # site↔factory 미연결
    with pytest.raises(ConstructionSiteBridgeError):
        run_safe_construction_leg(sb, "S1", {})
    assert cap["called"] == 0             # LEG 호출 0
    assert sb.counters["writes"] == 0     # factory 생성 0


# ── sector = CONSTRUCTION ──────────────────────────────────────────────
def test_sector_construction(monkeypatch):
    cap = {"called": 0}
    _patch_leg(monkeypatch, cap)
    run_safe_construction_leg(_sb(), "S1", {})
    assert cap["step1"].sector == "CONSTRUCTION"
    assert cap["step1"].factory_id == "F1"


# ── runtime DB write 0 ─────────────────────────────────────────────────
def test_runtime_no_db_write(monkeypatch):
    cap = {"called": 0}
    _patch_leg(monkeypatch, cap)
    sb = _sb()
    run_safe_construction_leg(sb, "S1", {"has_excavation": True})
    assert sb.counters["writes"] == 0



# ── CORRECTION-1: RUNTIME20 + 규제 override + construction_type code fixture ──
def test_T1_runtime_denominator_20():
    assert len(RUNTIME_INPUT_FIELDS) == 20
    assert len(set(RUNTIME_INPUT_FIELDS)) == 20

def test_T2_request_schema_20():
    from schemas.legal_engine import SafeConstructionConsumerInput
    assert len(SafeConstructionConsumerInput.model_fields) == 20
    # exact-set: request schema == RUNTIME_INPUT_FIELDS (EXTRA 0, MISSING 0).
    assert set(SafeConstructionConsumerInput.model_fields) == set(RUNTIME_INPUT_FIELDS)

def test_T3_regulatory_false_preserved(monkeypatch):
    cap = {"called": 0}; _patch_leg(monkeypatch, cap)
    out = run_safe_construction_leg(_sb(), "S1", {"has_gas": False, "is_multi_use": False})
    inp = cap["step1"].input
    assert inp["has_gas"] is False and "has_gas" not in out["unresolved_fields"]
    assert inp["is_multi_use"] is False and "is_multi_use" not in out["unresolved_fields"]

def test_T4_regulatory_true(monkeypatch):
    cap = {"called": 0}; _patch_leg(monkeypatch, cap)
    out = run_safe_construction_leg(_sb(), "S1", {"has_high_pressure_gas": True})
    assert cap["step1"].input["has_high_pressure_gas"] is True
    assert "has_high_pressure_gas" not in out["unresolved_fields"]

def test_T5_regulatory_none(monkeypatch):
    cap = {"called": 0}; _patch_leg(monkeypatch, cap)
    out = run_safe_construction_leg(_sb(), "S1", {"has_asbestos": None})
    assert cap["step1"].input["has_asbestos"] is None
    assert "has_asbestos" in out["unresolved_fields"]

def test_T6_non_runtime_canonical_firewall():
    # fail-closed: schema 가 실제로 REJECT 해야 PASS. ACCEPT 하면 ValidationError 미발생 → 테스트 FAIL.
    from schemas.legal_engine import SafeConstructionLegBody
    for bad in ("subcontractor_count", "process_list", "subcontractor"):
        with pytest.raises(ValidationError):
            SafeConstructionLegBody(site_id="S1", input={bad: 1})

def test_T7_construction_type_code_fixture():
    r = assemble_construction_marketing_contract(_sb(site={"site_type": "BUILDING"}), "S1")
    assert r["values"]["construction_type"] == "BUILDING"   # 한글 변환 없음
