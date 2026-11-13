"""WO-E2E2000-TRACK-A-C1C3-INVESTIGATION-001 — C1~C3 입력 경로 갭 조사 결과 검증.

조사 결과:
  WP-01: floor_count ALREADY_RESOLVED
    - _BUILDING_N1_FIELDS에 존재, _LEG_INPUT_FIELDS에 존재
    - safe_building_leg_runtime.py H01 hydration 경로로 처리됨
    - 수정 없음.

  WP-07: actor fields (S02 4-fact) ALREADY_RESOLVED
    - _S02_OVERRIDE_FIELDS가 SAFE_CST_OVERRIDE_FIELDS에 포함됨
    - test_e2e2000_obj06_g1_s02_transport.py 19/19 PASS 확인됨
    - 수정 없음.

  WP-08: C2→C3 NUMERIC gap 조사
    - PATCH-2A 11축(scaffold_height_m 등)은 work_source/projector.py가 처리
    - diving_worker_count, same_site_construction_count 등은 소비자 override 경로 존재
    - test_free_consumer_c1_c3_guard.py G-11/G-12 (118 PASS)가 경로 보증
    - C2 갭 없음 — REVIEW_REQUIRED 원인은 소비자 미제공 (C1 갭) + work_source 행 없는 경우

  TRACK B 채석작업 C1 현황:
    - 별도 'has_quarrying_work' / 'quarrying' 필드 없음
    - 발파작업: has_blasting (_LEG_INPUT_FIELDS 존재, cst_process_projector BLASTING 매핑)
    - 채석작업 단독 LEG vocabulary 없음 → TRACK B Owner 판단 필요

테스트:
  - _LEG_INPUT_FIELDS 포함 여부 (WP-01/07/08 필드)
  - _BUILDING_N1_FIELDS 소속 확인 (WP-01)
  - SAFE_CST_OVERRIDE_FIELDS 포함 여부 (WP-07)
  - TRACK B: has_blasting 경로 확인, quarrying 전용 필드 부재 확인
"""
from __future__ import annotations

import pytest

from clients.leg_runtime_client import (
    _LEG_INPUT_FIELDS,
    _BUILDING_N1_FIELDS,
    build_facility,
)
from services.safe_construction_leg_runtime import SAFE_CST_OVERRIDE_FIELDS
from services.cst_process_projector import _APPROVED_PROCESS_MAPPINGS_V1


# ── WP-01: floor_count ALREADY_RESOLVED 확인 ─────────────────────────────────

def test_wp01_floor_count_in_leg_input_fields():
    """floor_count는 _LEG_INPUT_FIELDS에 존재한다."""
    assert "floor_count" in _LEG_INPUT_FIELDS


def test_wp01_floor_count_in_building_n1_fields():
    """floor_count는 _BUILDING_N1_FIELDS에 존재한다 (BUILDING sector-gated)."""
    assert "floor_count" in _BUILDING_N1_FIELDS


def test_wp01_floor_count_building_sector_reaches_facility():
    """floor_count는 BUILDING sector에서 build_facility 출력에 포함된다."""
    class _Body:
        sector = "BUILDING"
        input = {"floor_count": 10}
    fac = build_facility(_Body())
    assert fac.get("floor_count") == 10


def test_wp01_floor_count_absent_in_non_building_facility():
    """floor_count는 BUILDING 외 sector에서 build_facility 출력에 포함되지 않는다."""
    for sector in ("INDUSTRIAL", "CONSTRUCTION"):
        class _Body:
            input = {"floor_count": 10}
        _Body.sector = sector
        fac = build_facility(_Body())
        assert "floor_count" not in fac, (
            f"floor_count must not appear in {sector} facility (BUILDING N1 gate)"
        )


# ── WP-07: actor fields (S02 4-fact) ALREADY_RESOLVED 확인 ───────────────────

_S02_FIELDS = (
    "contracts_construction_work_at_site",
    "leads_and_manages_construction_execution",
    "recontracts_received_construction_work",
    "same_site_contracted_construction_work_count",
)


def test_wp07_s02_fields_in_leg_input_fields():
    """S02 4-fact가 _LEG_INPUT_FIELDS에 존재한다."""
    for f in _S02_FIELDS:
        assert f in _LEG_INPUT_FIELDS, f"S02 field '{f}' missing from _LEG_INPUT_FIELDS"


def test_wp07_s02_fields_in_safe_cst_override_fields():
    """S02 4-fact가 SAFE_CST_OVERRIDE_FIELDS에 존재한다 (C1→C2 경로 확인)."""
    for f in _S02_FIELDS:
        assert f in SAFE_CST_OVERRIDE_FIELDS, (
            f"S02 field '{f}' missing from SAFE_CST_OVERRIDE_FIELDS — C1 transport blocked"
        )


def test_wp07_s02_boolean_false_preserved_in_facility():
    """S02 boolean False는 build_facility에서 보존된다."""
    class _Body:
        sector = "CONSTRUCTION"
        input = {
            "contracts_construction_work_at_site": False,
            "leads_and_manages_construction_execution": True,
        }
    fac = build_facility(_Body())
    assert fac.get("contracts_construction_work_at_site") is False
    assert fac.get("leads_and_manages_construction_execution") is True


def test_wp07_s02_count_zero_preserved_in_facility():
    """same_site_contracted_construction_work_count=0은 build_facility에서 보존된다."""
    class _Body:
        sector = "CONSTRUCTION"
        input = {"same_site_contracted_construction_work_count": 0}
    fac = build_facility(_Body())
    assert fac.get("same_site_contracted_construction_work_count") == 0


# ── WP-08: NUMERIC C2→C3 경로 확인 ──────────────────────────────────────────

# 32개 NUMERIC_FIELDS 전체
_ALL_NUMERIC_FIELDS = {
    # INT 8개
    "worker_count", "total_floor_area", "floor_count", "occupancy_capacity",
    "same_site_construction_count", "diving_worker_count",
    "same_site_contracted_construction_work_count", "appendix3_item_no",
    # FLOAT 24개
    "work_height_m", "truck_loading_height_m", "manual_handling_weight_kg",
    "building_height_m", "floor_area_sum_at_or_above_11f", "performance_use_floor_area_sum",
    "cantilever_projection_m", "column_span_m", "flat_plate_column_section_ratio",
    "underground_connection_entrance_distance_m", "connection_open_space_floor_area_m2",
    "connection_open_space_open_area_ratio", "stair_or_ramp_effective_width_m",
    "scaffold_height_m", "grinding_wheel_diameter_cm", "breathing_gas_cylinder_pressure_kgf_cm2",
    "structure_height_m", "object_drop_height_m", "construction_machine_weight_ton",
    "hazmat_designated_quantity_multiple", "rotor_peripheral_speed_m_s", "rotor_shaft_weight_ton",
    "contract_amount_eok", "diving_depth_m",
}


def test_wp08_all_numeric_fields_in_leg_input_fields():
    """32개 NUMERIC_FIELDS 전체가 _LEG_INPUT_FIELDS에 존재한다 (C3 경로 보증)."""
    missing = _ALL_NUMERIC_FIELDS - set(_LEG_INPUT_FIELDS)
    assert not missing, (
        f"NUMERIC_FIELDS not in _LEG_INPUT_FIELDS (C3 transport impossible): {sorted(missing)}"
    )


def test_wp08_patch2a_scaffold_height_reaches_facility():
    """scaffold_height_m은 build_facility에서 전달된다 (sector-agnostic)."""
    for sector in ("INDUSTRIAL", "CONSTRUCTION", "BUILDING"):
        class _Body:
            input = {"scaffold_height_m": 4.5}
        _Body.sector = sector
        fac = build_facility(_Body())
        assert fac.get("scaffold_height_m") == pytest.approx(4.5), (
            f"scaffold_height_m not in facility for sector {sector}"
        )


def test_wp08_patch2a_diving_worker_count_reaches_facility():
    """diving_worker_count는 build_facility에서 전달된다."""
    class _Body:
        sector = "CONSTRUCTION"
        input = {"diving_worker_count": 3}
    fac = build_facility(_Body())
    assert fac.get("diving_worker_count") == 3


def test_wp08_patch2a_same_site_construction_count_reaches_facility():
    """same_site_construction_count는 build_facility에서 전달된다."""
    class _Body:
        sector = "CONSTRUCTION"
        input = {"same_site_construction_count": 2}
    fac = build_facility(_Body())
    assert fac.get("same_site_construction_count") == 2


def test_wp08_numeric_zero_preserved_facility():
    """NUMERIC_FIELDS에서 0 값은 build_facility에서 보존된다 (falsy filter 금지)."""
    class _Body:
        sector = "CONSTRUCTION"
        input = {
            "worker_count": 0,
            "contract_amount_eok": 0.0,
            "scaffold_height_m": 0.0,
        }
    fac = build_facility(_Body())
    assert fac.get("worker_count") == 0
    assert fac.get("contract_amount_eok") == pytest.approx(0.0)
    assert fac.get("scaffold_height_m") == pytest.approx(0.0)


def test_wp08_numeric_none_absent_in_facility():
    """NUMERIC_FIELDS에서 None 값은 build_facility 출력에서 제외된다."""
    class _Body:
        sector = "CONSTRUCTION"
        input = {}
    fac = build_facility(_Body())
    for f in ("scaffold_height_m", "diving_worker_count", "same_site_construction_count"):
        assert f not in fac, f"None numeric field '{f}' must be absent from facility"


# ── TRACK B: 채석작업 C1 입력 현황 ────────────────────────────────────────────

def test_track_b_has_blasting_in_leg_input_fields():
    """has_blasting은 _LEG_INPUT_FIELDS에 존재한다 (발파작업 C1 경로 확인)."""
    assert "has_blasting" in _LEG_INPUT_FIELDS


def test_track_b_blasting_work_projector_mapping_exists():
    """cst_process_projector에 BLASTING→has_blasting 매핑이 존재한다."""
    key = ("kcsc_work_master", "BLASTING")
    assert key in _APPROVED_PROCESS_MAPPINGS_V1
    assert _APPROVED_PROCESS_MAPPINGS_V1[key] == "has_blasting"


def test_track_b_no_dedicated_quarrying_field():
    """채석작업 전용 필드가 _LEG_INPUT_FIELDS에 없음을 확인한다.

    has_quarrying_work / quarrying_work 등 채석작업 전용 vocabulary는
    현재 LEG input fields에 등록되지 않았음을 명시한다.
    TRACK B Owner 결정 필요: 채석작업을 별도 필드로 추가할지 has_blasting으로 처리할지.
    """
    quarrying_candidates = {
        "has_quarrying_work",
        "has_quarrying",
        "quarrying_work",
        "quarrying",
    }
    present = quarrying_candidates & set(_LEG_INPUT_FIELDS)
    assert not present, (
        f"예상치 않은 채석작업 전용 필드가 _LEG_INPUT_FIELDS에 존재함: {present} "
        f"(TRACK B 조사 기준 변경 — 재확인 필요)"
    )


def test_track_b_has_blasting_reaches_facility():
    """has_blasting=True는 CONSTRUCTION sector build_facility 출력에 포함된다."""
    class _Body:
        sector = "CONSTRUCTION"
        input = {"has_blasting": True}
    fac = build_facility(_Body())
    assert fac.get("has_blasting") is True


def test_track_b_has_blasting_false_preserved():
    """has_blasting=False는 build_facility에서 보존된다 (명시적 부재)."""
    class _Body:
        sector = "CONSTRUCTION"
        input = {"has_blasting": False}
    fac = build_facility(_Body())
    assert fac.get("has_blasting") is False
