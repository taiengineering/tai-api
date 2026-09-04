"""WO-BLD-FINALIZATION PATCH-A(+1) — BUILDING has_chemical_substance exact-key + alias 차단.

C1 화관법: has_chemical_substance 명시 → facility exact-key. has_chemical 이중생성 금지
(_LEG_CODE_TO_CONSUMER alias 차단, BUILDING sector).
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from clients.leg_runtime_client import build_facility
from schemas.legal_engine import DiagnoseStep1Body


def _bld(input=None, **top):
    return DiagnoseStep1Body(sector="BUILDING", input=input or {}, **top)


# ── 1. BUILDING hcs=true → exact + has_chemical absent ──
def test_hcs_true_exact_no_has_chemical():
    fac = build_facility(_bld(input={"has_chemical_substance": True}))
    assert fac.get("has_chemical_substance") is True
    assert "has_chemical" not in fac          # alias 이중생성 금지

# ── 2. BUILDING hcs=false → exact false + has_chemical absent ──
def test_hcs_false_exact_no_has_chemical():
    fac = build_facility(_bld(input={"has_chemical_substance": False}))
    assert fac.get("has_chemical_substance") is False
    assert "has_chemical" not in fac

# ── 3. BUILDING hcs=None → 둘 다 absent ──
def test_hcs_none_both_absent():
    fac = build_facility(_bld(input={}))
    assert "has_chemical_substance" not in fac
    assert "has_chemical" not in fac

# ── 4. CONSTRUCTION 기존 rename 유지 ──
def test_construction_rename_intact():
    fac = build_facility(DiagnoseStep1Body(sector="CONSTRUCTION", input={"has_chemical": True}))
    assert fac.get("has_chemical_substance") is True   # 건설 rename
    assert "has_chemical" not in fac

# ── 5. INDUSTRIAL 기존 동작 유지 ──
def test_industrial_intact():
    # 산업: has_chemical 직접 입력 → facility has_chemical (alias/rename 없음, 기존 동작)
    fac = build_facility(DiagnoseStep1Body(sector="MANUFACTURING", input={"has_chemical": True}))
    assert fac.get("has_chemical") is True
    # 산업 has_chemical_substance(alias 역방향)는 _LEG_INPUT_FIELDS 순회 상 has_chemical으로 매핑되던 기존 동작 확인
    fac2 = build_facility(DiagnoseStep1Body(sector="MANUFACTURING", input={"has_chemical_substance": True}))
    # 산업은 alias 차단 안 함(BUILDING gate) → 기존대로 has_chemical alias 경유
    assert fac2.get("has_chemical") is True   # 기존 동작 불변(alias)
