"""WO-TAI-C1-C3-MARKETING-LEG-SECTOR-PARITY-LOCAL-ONLY-003

Mandatory proof table (WO-003):
  M1  leg_sector = sector 선언이 engine_sector 할당 직후에 존재 (STATIC)
  M2  unified 분기 호출부가 engine_sector=leg_sector 사용 (STATIC)
  M3  source loader guard 가 engine_sector 사용 (STATIC)
  M4  _build_unified_step1_body(engine_sector="INDUSTRIAL") → step1_body.sector=="INDUSTRIAL"
  M5  indoor_workplace=True  → build_facility 포함 (sector=INDUSTRIAL)
  M6  indoor_workplace=False → build_facility 포함 (sector=INDUSTRIAL)
  M7  indoor_workplace absent → build_facility 미포함 (sector=INDUSTRIAL)
  M8  indoor_workplace 제공 → build_facility 미포함 (sector=BUILDING)
  M9  indoor_workplace 제공 → build_facility 미포함 (sector=CONSTRUCTION)
  M10 BUILDING/CONSTRUCTION step1_body.sector 변동 없음
  M11 engine_sector="MANUFACTURING" 시 step1_body.sector=="MANUFACTURING" (helper직접호출 기존동작보존)

STATIC_PROOF = 소스 레벨 검사 (M1/M2/M3)
EXECUTED_OFFLINE = 실제 함수 호출 (M4–M11)
"""
from __future__ import annotations

import inspect
from typing import Any, Dict, Optional

from clients.leg_runtime_client import build_facility
from schemas.legal_engine import DiagnoseStep1Body
from services.canonical.leg_input_contract import build_unified_leg_input
from services.diagnosis_integrated_svc import _build_unified_step1_body


# ─────────────────────────────────────────────────────────────────────────
# STATIC PROOF
# ─────────────────────────────────────────────────────────────────────────

def test_M1_leg_sector_declared_after_engine_sector():
    """STATIC: leg_sector = sector 선언이 engine_sector 할당 직후 존재."""
    import services.diagnosis_integrated_svc as svc_mod
    src = inspect.getsource(svc_mod)
    engine_pos = src.find('engine_sector = "MANUFACTURING" if sector == "INDUSTRIAL" else sector')
    leg_pos = src.find("leg_sector = sector")
    assert engine_pos != -1, "engine_sector 할당 라인이 소스에서 사라짐"
    assert leg_pos != -1, "leg_sector = sector 선언이 소스에 없음"
    assert leg_pos > engine_pos, "leg_sector 선언이 engine_sector 할당보다 앞에 있음"


def test_M2_unified_branch_uses_leg_sector():
    """STATIC: unified 분기 _build_unified_step1_body 호출이 engine_sector=leg_sector 사용."""
    import services.diagnosis_integrated_svc as svc_mod
    src = inspect.getsource(svc_mod.run_diagnosis)
    assert "engine_sector=leg_sector," in src, (
        "unified 분기 호출부에서 engine_sector=leg_sector 미사용"
    )


def test_M3_source_loader_guard_uses_engine_sector():
    """STATIC: 유료 factory 소스 로더 guard 가 engine_sector 기준으로 유지됨."""
    import services.diagnosis_integrated_svc as svc_mod
    src = inspect.getsource(svc_mod.run_diagnosis)
    assert 'engine_sector in {"MANUFACTURING", "BUILDING", "CONSTRUCTION"}' in src, (
        "source loader guard 가 engine_sector 기준에서 변경됨"
    )


# ─────────────────────────────────────────────────────────────────────────
# EXECUTED OFFLINE helpers
# ─────────────────────────────────────────────────────────────────────────

def _make_step1(
    leg_sector: str,
    inp: Optional[Dict[str, Any]] = None,
    workers: int = 10,
) -> DiagnoseStep1Body:
    from types import SimpleNamespace
    body = SimpleNamespace(
        form_data={},
        direct_workers=None,
        worker_count=workers,
        employee_count=None,
        floor_area=None,
        elevator_count=None,
    )
    return _build_unified_step1_body(
        engine_sector=leg_sector,
        inp=inp or {},
        workers=workers,
        body=body,
        factory_id=None,
        construction_type_fallback=None,
        unified_factory=build_unified_leg_input,
    )


# ─────────────────────────────────────────────────────────────────────────
# M4: INDUSTRIAL engine_sector → step1_body.sector == "INDUSTRIAL"
# ─────────────────────────────────────────────────────────────────────────

def test_M4_industrial_leg_sector_step1_sector():
    """EXECUTED: engine_sector="INDUSTRIAL" → step1_body.sector="INDUSTRIAL"."""
    step1 = _make_step1("INDUSTRIAL")
    assert step1.sector == "INDUSTRIAL", (
        f"step1_body.sector={step1.sector!r}, expected INDUSTRIAL"
    )


# ─────────────────────────────────────────────────────────────────────────
# M5–M7: indoor_workplace pass-through for INDUSTRIAL
# ─────────────────────────────────────────────────────────────────────────

def test_M5_industrial_indoor_workplace_true_reaches_facility():
    """EXECUTED: indoor_workplace=True → build_facility 포함 (sector=INDUSTRIAL)."""
    step1 = _make_step1("INDUSTRIAL", inp={"indoor_workplace": True})
    facility = build_facility(step1)
    assert facility.get("indoor_workplace") is True, (
        "indoor_workplace=True 가 facility 에서 누락됨 (sector=INDUSTRIAL)"
    )


def test_M6_industrial_indoor_workplace_false_reaches_facility():
    """EXECUTED: indoor_workplace=False → build_facility 포함 (sector=INDUSTRIAL), false 보존."""
    step1 = _make_step1("INDUSTRIAL", inp={"indoor_workplace": False})
    facility = build_facility(step1)
    assert "indoor_workplace" in facility, (
        "indoor_workplace=False 가 facility 에서 누락됨 (sector=INDUSTRIAL)"
    )
    assert facility["indoor_workplace"] is False


def test_M7_industrial_indoor_workplace_absent_omitted():
    """EXECUTED: indoor_workplace 미제공 → facility 에 키 없음 (sector=INDUSTRIAL)."""
    step1 = _make_step1("INDUSTRIAL", inp={})
    facility = build_facility(step1)
    assert "indoor_workplace" not in facility, (
        "indoor_workplace 미제공인데 facility 에 키가 생성됨"
    )


# ─────────────────────────────────────────────────────────────────────────
# M8–M9: BUILDING/CONSTRUCTION sector gate — indoor_workplace 차단
# ─────────────────────────────────────────────────────────────────────────

def test_M8_building_indoor_workplace_blocked():
    """EXECUTED: sector=BUILDING → indoor_workplace 제공해도 facility 미포함."""
    step1 = _make_step1("BUILDING", inp={"indoor_workplace": True})
    facility = build_facility(step1)
    assert "indoor_workplace" not in facility, (
        "indoor_workplace 가 BUILDING sector facility 에 유입됨"
    )


def test_M9_construction_indoor_workplace_blocked():
    """EXECUTED: sector=CONSTRUCTION → indoor_workplace 제공해도 facility 미포함."""
    step1 = _make_step1("CONSTRUCTION", inp={"indoor_workplace": True})
    facility = build_facility(step1)
    assert "indoor_workplace" not in facility, (
        "indoor_workplace 가 CONSTRUCTION sector facility 에 유입됨"
    )


# ─────────────────────────────────────────────────────────────────────────
# M10: BUILDING/CONSTRUCTION step1_body.sector 보존
# ─────────────────────────────────────────────────────────────────────────

def test_M10_building_sector_unchanged():
    """EXECUTED: leg_sector=BUILDING → step1_body.sector=="BUILDING"."""
    step1 = _make_step1("BUILDING")
    assert step1.sector == "BUILDING"


def test_M10_construction_sector_unchanged():
    """EXECUTED: leg_sector=CONSTRUCTION → step1_body.sector=="CONSTRUCTION"."""
    step1 = _make_step1("CONSTRUCTION")
    assert step1.sector == "CONSTRUCTION"


# ─────────────────────────────────────────────────────────────────────────
# M11: helper 직접 호출 시 MANUFACTURING 전달 기존 동작 보존
# ─────────────────────────────────────────────────────────────────────────

def test_M11_helper_direct_manufacturing_preserved():
    """EXECUTED: _build_unified_step1_body(engine_sector="MANUFACTURING") → step1_body.sector=="MANUFACTURING".

    기존 테스트(WO-010 T2 등)가 helper 직접 호출 시 MANUFACTURING 전달하는 경우
    helper 자체 동작이 변경되지 않았음을 확인.
    """
    step1 = _make_step1("MANUFACTURING")
    assert step1.sector == "MANUFACTURING"
    facility = build_facility(step1)
    assert "indoor_workplace" not in facility, (
        "MANUFACTURING sector 직접 전달 시 indoor_workplace 가 facility 에 유입됨 (기존 동작 회귀)"
    )
