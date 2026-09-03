"""WP3-BLOCKER-FIX-001 — BUILDING gas/chem OVER-CLAIM 제거 검증.

기존 BUILDING Step1: has_high_pressure_gas=body.has_gas / has_hazardous_material=body.has_chemical
  = "가스 사용"→고압가스, "화학물질 취급"→산안 유해물질 부정 발동(별개 법령).
제거 후: build_facility 가 inp(사용자 명시값)만 사용. 사용자가 has_high_pressure_gas/
  has_hazardous_material 를 명시하지 않으면 facility 미포함(부정 발동 없음).
BUILDING sector 만. 정상 동명매핑(다른 분기) 무접촉.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from clients.leg_runtime_client import build_facility
from schemas.legal_engine import DiagnoseStep1Body


def _bld(input=None, **top):
    return DiagnoseStep1Body(sector="BUILDING", input=input or {}, **top)


# ── OVER-CLAIM 제거: has_gas 입력이 has_high_pressure_gas 로 부정 발동 안 함 ──
def test_has_gas_does_not_overclaim_high_pressure():
    # 사용자가 has_gas(도시가스 가능)만 입력. has_high_pressure_gas 미명시.
    fac = build_facility(_bld(input={"has_gas": True}))
    assert fac.get("has_gas") is True                      # 도시가스는 정상 전달
    assert "has_high_pressure_gas" not in fac              # 고압가스 부정 발동 없음 (OVER-CLAIM 제거)

def test_has_chemical_does_not_overclaim_hazardous():
    fac = build_facility(_bld(input={"has_chemical": True}))
    # has_chemical 은 _LEG_INPUT_FIELDS 통로 존재(BUILDING rename 없음) → facility 에 has_chemical
    assert "has_hazardous_material" not in fac             # 산안 유해물질 부정 발동 없음


# ── 명시적 입력은 정상 발동 (OVER-CLAIM 제거가 정상 경로 안 막음) ──
def test_explicit_high_pressure_gas_reaches_facility():
    fac = build_facility(_bld(input={"has_high_pressure_gas": True}))
    assert fac.get("has_high_pressure_gas") is True        # 명시 고압가스 = 정상 발동

def test_explicit_hazardous_material_reaches_facility():
    fac = build_facility(_bld(input={"has_hazardous_material": True}))
    assert fac.get("has_hazardous_material") is True       # 명시 산안 유해물질 = 정상 발동


# ── FIREWALL: 산업/건설 sector 의 gas/chem 매핑 무접촉 ──
def test_firewall_construction_has_chemical_rename():
    # CONSTRUCTION 은 has_chemical → has_chemical_substance rename (기존 동작 유지).
    fac = build_facility(DiagnoseStep1Body(sector="CONSTRUCTION", input={"has_chemical": True}))
    assert fac.get("has_chemical_substance") is True       # 건설 rename 유지
    assert "has_chemical" not in fac

def test_firewall_industrial_has_chemical_kept():
    # INDUSTRIAL(MANUFACTURING) 은 has_chemical 유지 (rename 없음).
    fac = build_facility(DiagnoseStep1Body(sector="MANUFACTURING", input={"has_chemical": True}))
    assert fac.get("has_chemical") is True


# ── 소스 가드: BUILDING 실시간 분기에 OVER-CLAIM 코드 부재 ──
def test_source_no_overclaim_in_building():
    src = open("services/diagnosis_integrated_svc.py").read()
    # 코드 라인(주석 제외)에 has_high_pressure_gas=body.has_gas / has_hazardous_material=body.has_chemical 부재
    import re
    code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    assert "has_high_pressure_gas=body.has_gas" not in code
    assert "has_hazardous_material=body.has_chemical" not in code
    # 정상 동명매핑(다른 분기)은 유지
    assert "has_hazardous_material=body.has_hazardous_material" in code
