"""WO-010 STEP-2B: FREE/PAID marketing cutover to unified LEG input contract.

검증 범위:
  · T1  /run-leg 배선 : run_diagnosis 에 unified_step1_factory_func=build_unified_leg_input 전달,
        canonical_step1_factory_func 미전달(경로 cutover 확정).
  · T2  INDUSTRIAL INTENDED DELTA : OLD(build_industrial_www_step1→build_facility) 대비
        NEW(unified→build_facility) 는 기존 key/value 모두 EXACT 보존, ADDED 값 EXACT, REMOVED=0.
  · T3  INDUSTRIAL WO-007 12축 build_facility 도달.
  · T4  INDUSTRIAL N1 firewall(floor_count 등 build_facility 미도달).
  · T5  chemical alias : IND has_chemical_substance→has_chemical / CST rename / false 보존 / 신규 alias 0.
  · T6  BUILDING elevator derived : None→ABSENT, 0→false, 1→true (cutover 전후 EXACT).
  · T7  BUILDING FACILITY PARITY(OLD vs NEW build_facility diff = 0).
  · T8  CONSTRUCTION FACILITY PARITY(diff = 0) + construction_type "건축" COMPAT 유지.
  · T9  worker51 parity(BLD/IND/CST 51→51).
  · T10 zero/false/absent 계약 회귀 0.
  · T11 PAID CONSTRUCTION equipment enrichment(inp.setdefault has_* True) 도달 유지.
  · T14 계약 파일 정적 delta 게이트(import 유지 + 핵심 심볼 stable).
T12(auth/저장 semantic delta 0) / T13(legacy /diagnosis/run delta 0) / T14(계약파일 파일 diff 0)
git 게이트는 pytest 외부에서 receipt 로 보고.
"""
from __future__ import annotations

import asyncio
import importlib
import inspect
import os
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

from clients.leg_runtime_client import (
    _BUILDING_N1_FIELDS,
    _LEG_CODE_TO_CONSUMER,
    _LEG_INPUT_FIELDS,
    build_facility,
)
from schemas.diagnosis_integrated import DiagnosisRunBody
from schemas.legal_engine import DiagnoseStep1Body
from services.canonical.industrial_www import build_industrial_www_step1
from services.canonical.leg_input_contract import build_unified_leg_input
from services.canonical.materialization import canonical_applicability
from services.diagnosis_integrated_svc import _build_unified_step1_body


# WO-007 12축 = PATCH-2A 15축 - CST-only 3축
# (construction_machine_weight_ton / same_site_construction_count / has_construction_machine 제외)
WO007_12_AXES = (
    "scaffold_height_m",
    "grinding_wheel_diameter_cm",
    "breathing_gas_cylinder_pressure_kgf_cm2",
    "structure_height_m",
    "object_drop_height_m",
    "hazmat_designated_quantity_multiple",
    "rotor_peripheral_speed_m_s",
    "rotor_shaft_weight_ton",
    "diving_worker_count",
    "has_structure",
    "has_object_drop",
    "has_high_speed_rotor",
)

WO007_12_VALUES: Dict[str, Any] = {
    "scaffold_height_m": 1.2,
    "grinding_wheel_diameter_cm": 20,
    "breathing_gas_cylinder_pressure_kgf_cm2": 100,
    "structure_height_m": 10.0,
    "object_drop_height_m": 3.0,
    "hazmat_designated_quantity_multiple": 2.0,
    "rotor_peripheral_speed_m_s": 40.0,
    "rotor_shaft_weight_ton": 1.0,
    "diving_worker_count": 2,
    "has_structure": True,
    "has_object_drop": True,
    "has_high_speed_rotor": True,
}


def _mk_body(sector: str, form_data: Optional[Dict[str, Any]] = None, **extra) -> DiagnosisRunBody:
    """DiagnosisRunBody 인스턴스(테스트 헬퍼)."""
    payload = {"sector": sector, "form_data": form_data or {}}
    payload.update(extra)
    return DiagnosisRunBody(**payload)


def _simulate_inp(body: Any) -> Dict[str, Any]:
    """run_diagnosis 의 inp 조립 축약 : canonical_applicability(body_fields + form_data)."""
    inp: Dict[str, Any] = {}
    available: Dict[str, Any] = {f: getattr(body, f, None) for f in type(body).model_fields}
    available.update(getattr(body, "form_data", None) or {})
    for c, v in canonical_applicability(available).items():
        inp.setdefault(c, v)
    return inp


def _simulate_workers(body: Any) -> int:
    """run_diagnosis 의 workers 계산 축약."""
    fd = getattr(body, "form_data", None) or {}
    if body.worker_count is not None:
        return body.worker_count
    for k in ("worker_count", "workers"):
        v = fd.get(k)
        if v is not None and v != "":
            try:
                return int(float(v))
            except (TypeError, ValueError):
                pass
    if body.direct_workers is not None:
        return body.direct_workers
    return 0


def _new_facility(body: Any, engine_sector: str,
                  extra_inp: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """svc._build_unified_step1_body → build_facility."""
    inp = _simulate_inp(body)
    if extra_inp:
        for k, v in extra_inp.items():
            inp.setdefault(k, v)
    workers = _simulate_workers(body)
    fd = getattr(body, "form_data", None) or {}
    step1 = _build_unified_step1_body(
        engine_sector=engine_sector,
        inp=inp,
        workers=workers,
        body=body,
        factory_id=None,
        construction_type_fallback=(body.construction_type or fd.get("construction_type")),
        unified_factory=build_unified_leg_input,
    )
    return build_facility(step1)


def _old_industrial_facility(body: Any) -> Dict[str, Any]:
    """OLD IND 경로 : build_industrial_www_step1 → build_facility."""
    step1 = build_industrial_www_step1(body)
    return build_facility(step1)


def _old_building_step1(body: Any) -> DiagnoseStep1Body:
    """run_diagnosis 의 legacy BUILDING elif 축약."""
    inp = _simulate_inp(body)
    workers = _simulate_workers(body)
    employees = body.employee_count if body.employee_count is not None else workers
    floor_area = body.floor_area or 400.0
    bld_fd = getattr(body, "form_data", None) or {}
    bld_elev = body.elevator_count if body.elevator_count is not None else bld_fd.get("elevator_count")
    return DiagnoseStep1Body(
        factory_id=None,
        sector="BUILDING",
        input=inp,
        floor_area=float(floor_area),
        worker_count=workers,
        employee_count=employees,
        electric_capacity=body.electric_capacity,
        elevator_count=bld_elev,
    )


def _old_construction_step1(body: Any, workers: int, contract_eok: float) -> DiagnoseStep1Body:
    """run_diagnosis 의 legacy CONSTRUCTION elif 축약."""
    inp = _simulate_inp(body)
    cst_fd = getattr(body, "form_data", None) or {}
    construction_type = body.construction_type or cst_fd.get("construction_type") or "건축"
    return DiagnoseStep1Body(
        factory_id=None,
        sector="CONSTRUCTION",
        input=inp,
        construction_type=construction_type,
        contract_amount_eok=float(contract_eok),
        worker_count=workers,
        direct_workers=body.direct_workers or workers,
        subcon_workers=body.subcon_workers or 0,
        has_chemical_substance=cst_fd.get("has_chemical_substance"),
    )


def _facility_diff(old: Dict[str, Any], new: Dict[str, Any]):
    """(added, removed, changed_existing) — set-of-keys diff + value change."""
    o_k, n_k = set(old), set(new)
    added = n_k - o_k
    removed = o_k - n_k
    changed = {k for k in (o_k & n_k) if old[k] != new[k]}
    return added, removed, changed


# ─────────────────────────────────────────────────────────────────────────
# T1: /run-leg → run_diagnosis 배선(unified factory)
# ─────────────────────────────────────────────────────────────────────────
def test_T1_run_leg_wires_unified_factory():
    """/run-leg 라우터 소스에서 unified factory 배선 + industrial_www factory 미참조."""
    import routers.diagnosis_integrated_leg as leg_mod
    src = inspect.getsource(leg_mod)
    assert "from services.canonical.leg_input_contract import build_unified_leg_input" in src, (
        "unified factory import missing"
    )
    assert "build_industrial_www_step1" not in src, "legacy industrial_www factory import 잔존"
    run_src = inspect.getsource(leg_mod._run_leg_impl)
    assert "unified_step1_factory_func=build_unified_leg_input" in run_src, (
        "run_diagnosis 호출부에서 unified_step1_factory_func=build_unified_leg_input 배선이 안 됨"
    )
    assert "canonical_step1_factory_func" not in run_src, (
        "canonical_step1_factory_func 는 unified 배선에서 미전달이어야 한다"
    )


def test_T1b_run_leg_actual_call_binds_unified():
    """실제 _run_leg_impl 호출 시 run_diagnosis kwargs 검사(정적 소스 + 동적 kwargs 이중 확인).

    LEG_PIPELINE_ENABLED / is_enabled 는 module-level 캐시라 env reload 대신
    patch.object 로 직접 override 한다(테스트 격리).
    """
    import routers.diagnosis_integrated_leg as leg_mod

    with patch.object(leg_mod, "LEG_PIPELINE_ENABLED", True), \
         patch.object(leg_mod, "is_enabled", return_value=True), \
         patch.object(leg_mod, "get_supabase", return_value=MagicMock()), \
         patch.object(leg_mod.diagnosis_integrated_svc, "run_diagnosis") as _rd:
        _rd.return_value = {
            "status": "success", "public_token": "tk", "diagnosis_id": "d",
            "tier_code": "INDUSTRY_FREE", "is_free": True, "expires_at": None,
            "free_remaining_after": 3, "result": {},
        }
        body = _mk_body("INDUSTRIAL",
                        form_data={"worker_count": 10},
                        auth_token="tok", disclaimer_log_id="dlog")
        asyncio.run(leg_mod._run_leg_impl(body, None))

    assert _rd.call_count == 1
    kwargs = _rd.call_args.kwargs
    assert kwargs.get("unified_step1_factory_func") is build_unified_leg_input, (
        "unified_step1_factory_func 배선 실패"
    )
    assert kwargs.get("canonical_step1_factory_func") is None, (
        "canonical_step1_factory_func 는 unified 배선에서 미전달이어야 한다"
    )


# ─────────────────────────────────────────────────────────────────────────
# T2: INDUSTRIAL INTENDED DELTA
# ─────────────────────────────────────────────────────────────────────────
def test_T2_industrial_intended_delta():
    """IND WO-007 FREE payload : OLD ⊆ NEW, REMOVED=0, CHANGED(existing)=0, ADDED 값 EXACT."""
    fd = {
        # canonical29 subset
        "worker_count": 51,
        "total_floor_area": 11860.03,
        "building_use_type": "제조업",
        "ksic_major": "24",
        "has_boiler": False,
        "has_chemical_substance": True,
        "has_high_pressure_gas": False,
        "gas_capacity_kg": 0,
        "has_safety_manager": True,
        "electric_capacity": 500,   # LEG vocab 밖 — 양측 facility 미포함
        "work_height_m": 3.5,
        "has_truck_loading_unloading": True,
        "truck_loading_height_m": 2.0,
        "has_manual_heavy_handling": False,
        "manual_handling_weight_kg": 15,
        # WO-007 12축(unified 로 새로 노출)
        **WO007_12_VALUES,
    }
    body = _mk_body("INDUSTRIAL", form_data=fd)
    old = _old_industrial_facility(body)
    new = _new_facility(body, engine_sector="MANUFACTURING")
    added, removed, changed = _facility_diff(old, new)
    assert removed == set(), "REMOVED must be 0, got: {}".format(removed)
    assert changed == set(), "CHANGED(existing) must be 0, got: {}".format(changed)
    for k in added:
        # OLD 는 has_chemical_substance canonical29 → build_facility rename 로 facility[has_chemical]=...
        # NEW 도 alias 승격 → facility[has_chemical]=... (동일 key).
        # 따라서 added 되는 축은 form_data 명시값이어야 한다.
        assert k in fd, "발명된 키가 facility 에 등장: {}".format(k)
        assert new[k] == fd[k], "{}: form_data 값과 EXACT 아님 ({} vs {})".format(k, fd[k], new[k])


# ─────────────────────────────────────────────────────────────────────────
# T3: INDUSTRIAL WO-007 12축 build_facility 도달
# ─────────────────────────────────────────────────────────────────────────
def test_T3_industrial_wo007_12_axes_reach_facility():
    body = _mk_body("INDUSTRIAL", form_data=dict(WO007_12_VALUES))
    fac = _new_facility(body, engine_sector="MANUFACTURING")
    missing = [a for a in WO007_12_AXES if a not in fac]
    assert not missing, "IND WO-007 12축 미도달: {}".format(missing)
    for a in WO007_12_AXES:
        assert fac[a] == WO007_12_VALUES[a], "{} 값 EXACT 아님".format(a)


# ─────────────────────────────────────────────────────────────────────────
# T4: INDUSTRIAL N1 firewall
# ─────────────────────────────────────────────────────────────────────────
def test_T4_industrial_n1_firewall():
    fd = {
        "worker_count": 10,
        "floor_count": 7,
        "building_height_m": 21.0,
        "cantilever_projection_m": 1.5,
        "has_flat_plate_structure": True,
    }
    body = _mk_body("INDUSTRIAL", form_data=fd)
    fac = _new_facility(body, engine_sector="MANUFACTURING")
    for k in ("floor_count", "building_height_m", "cantilever_projection_m", "has_flat_plate_structure"):
        assert k not in fac, "N1 firewall 파괴 : {} 이 IND facility 로 유입".format(k)


# ─────────────────────────────────────────────────────────────────────────
# T5: CHEMICAL ALIAS
# ─────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("hcs_val", [True, False])
def test_T5_ind_chemical_substance_to_has_chemical(hcs_val):
    """IND : has_chemical_substance → facility.has_chemical (false 보존, rename 없음)."""
    fd = {"worker_count": 10, "has_chemical_substance": hcs_val}
    body = _mk_body("INDUSTRIAL", form_data=fd)
    fac = _new_facility(body, engine_sector="MANUFACTURING")
    assert fac.get("has_chemical") == hcs_val
    assert "has_chemical_substance" not in fac  # IND rename 없음


@pytest.mark.parametrize("hcs_val", [True, False])
def test_T5_cst_chemical_substance_rename(hcs_val):
    """CST : has_chemical_substance → build_facility CST rename → facility.has_chemical_substance."""
    fd = {"worker_count": 10, "has_chemical_substance": hcs_val, "construction_type": "건축"}
    body = _mk_body("CONSTRUCTION", form_data=fd)
    fac = _new_facility(body, engine_sector="CONSTRUCTION")
    assert fac.get("has_chemical_substance") == hcs_val
    assert "has_chemical" not in fac, "CST rename 이후 has_chemical 잔존"


def test_T5_no_new_alias_registered():
    """신규 alias 0 : _LEG_CODE_TO_CONSUMER 는 승인 2개만."""
    assert _LEG_CODE_TO_CONSUMER == {
        "has_chemical": "has_chemical_substance",
        "has_high_place_work": "has_high_work",
    }


# ─────────────────────────────────────────────────────────────────────────
# T6: BUILDING elevator derived (None/0/1/N)
# ─────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("elev_val,expected", [
    (None, None),
    (0, False),
    (1, True),
    (3, True),
])
def test_T6_building_elevator_derived(elev_val, expected):
    """cutover 전후 EXACT : None→ABSENT · 0→false · 1→true."""
    fd = {"worker_count": 10}
    if elev_val is not None:
        fd["elevator_count"] = elev_val
    body = _mk_body("BUILDING", form_data=fd)
    old = build_facility(_old_building_step1(body))
    new = _new_facility(body, engine_sector="BUILDING")
    if expected is None:
        assert "has_building_elevator" not in new
        assert "has_building_elevator" not in old
    else:
        assert new.get("has_building_elevator") is expected
        assert old.get("has_building_elevator") is expected


# ─────────────────────────────────────────────────────────────────────────
# T7: BUILDING FACILITY PARITY (OLD vs NEW diff = 0)
# ─────────────────────────────────────────────────────────────────────────
def test_T7_building_facility_parity_free_and_paid():
    fd_cases = [
        {  # FREE 대표
            "worker_count": 51,
            "total_floor_area": 11860.03,
            "building_use_type": "업무시설",
            "elevator_count": 2,
            "floor_count": 12,
            "has_safety_manager": True,
            "has_boiler": False,
        },
        {  # PAID 대표(N1 32 축 다양)
            "worker_count": 100,
            "total_floor_area": 25000.0,
            "building_use_type": "판매시설",
            "elevator_count": 0,
            "floor_count": 20,
            "building_height_m": 65.0,
            "floor_area_sum_at_or_above_11f": 3000.0,
            "has_flat_plate_structure": True,
            "is_collapse_risk_land": False,
            "authority_designated_special_structure": True,
        },
    ]
    for fd in fd_cases:
        body = _mk_body("BUILDING", form_data=fd)
        old = build_facility(_old_building_step1(body))
        new = _new_facility(body, engine_sector="BUILDING")
        added, removed, changed = _facility_diff(old, new)
        assert added == set() and removed == set() and changed == set(), (
            "BUILDING facility diff 0 위반. fd={} · added={} removed={} changed={}"
            .format(fd, added, removed, changed)
        )


# ─────────────────────────────────────────────────────────────────────────
# T8: CONSTRUCTION FACILITY PARITY + construction_type COMPAT
# ─────────────────────────────────────────────────────────────────────────
def test_T8_construction_facility_parity_and_compat():
    fd_cases = [
        {"worker_count": 20, "construction_type": "건축", "has_chemical_substance": True},
        {"worker_count": 30},  # construction_type 미지정 → COMPAT "건축"
        {"worker_count": 40, "construction_type": "토목",
         "construction_machine_weight_ton": 5.5,
         "same_site_construction_count": 3,
         "has_construction_machine": True,
         "diving_worker_count": 2},
    ]
    for fd in fd_cases:
        body = _mk_body("CONSTRUCTION", form_data=fd, contract_amount_eok=10.0)
        workers = _simulate_workers(body)
        old = build_facility(_old_construction_step1(body, workers, 10.0))
        new = _new_facility(body, engine_sector="CONSTRUCTION")
        added, removed, changed = _facility_diff(old, new)
        assert added == set() and removed == set() and changed == set(), (
            "CST facility diff 0 위반. fd={} · added={} removed={} changed={}"
            .format(fd, added, removed, changed)
        )
        # COMPAT : form_data 에 construction_type 없어도 "건축" 도달
        if "construction_type" not in fd:
            assert new.get("construction_type") == "건축", "construction_type COMPAT 유지 실패"


# ─────────────────────────────────────────────────────────────────────────
# T9: worker51 parity (BLD/IND/CST)
# ─────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("sector,engine_sector", [
    ("BUILDING", "BUILDING"),
    ("INDUSTRIAL", "MANUFACTURING"),
    ("CONSTRUCTION", "CONSTRUCTION"),
])
def test_T9_worker51_parity(sector, engine_sector):
    body = _mk_body(sector, form_data={"worker_count": 51})
    fac = _new_facility(body, engine_sector=engine_sector)
    assert fac.get("worker_count") == 51, (
        "{} worker51 parity 실패 : facility.worker_count={}"
        .format(sector, fac.get("worker_count"))
    )


# ─────────────────────────────────────────────────────────────────────────
# T10: zero/false/absent 계약
# ─────────────────────────────────────────────────────────────────────────
def test_T10_zero_false_absent_contract():
    fd = {
        "worker_count": 0,
        "has_boiler": False,
        "gas_capacity_kg": 0,
        "has_scaffold": False,
    }
    body = _mk_body("INDUSTRIAL", form_data=fd)
    fac = _new_facility(body, engine_sector="MANUFACTURING")
    assert fac.get("worker_count") == 0
    assert fac.get("has_boiler") is False
    assert fac.get("gas_capacity_kg") == 0
    assert fac.get("has_scaffold") is False
    # 미제공 축은 절대 발명되지 않는다
    assert "has_press" not in fac
    assert "has_conveyor" not in fac
    assert "has_emergency_gen" not in fac


# ─────────────────────────────────────────────────────────────────────────
# T11: PAID CONSTRUCTION equipment enrichment 도달
# ─────────────────────────────────────────────────────────────────────────
def test_T11_construction_equipment_enrichment_reaches_facility():
    """svc.run_diagnosis CST PAID 는 equipment_assets 조회로 inp.setdefault has_* True 를 넣는다.
    그 결과가 unified 경로에서 build_facility 에 도달해야 한다."""
    body = _mk_body("CONSTRUCTION", form_data={"worker_count": 20})
    fac = _new_facility(
        body, engine_sector="CONSTRUCTION",
        extra_inp={
            "has_emergency_gen": True,
            "has_boiler": True,
            "has_press": True,
            "has_conveyor": True,
            "has_pressure_vessel": True,
        },
    )
    for k in ("has_emergency_gen", "has_boiler", "has_press", "has_conveyor", "has_pressure_vessel"):
        assert fac.get(k) is True, "PAID equipment enrichment 축 {} 미도달".format(k)


# ─────────────────────────────────────────────────────────────────────────
# T14: 계약 파일 정적 delta 게이트 (import + 심볼 stable)
# ─────────────────────────────────────────────────────────────────────────
def test_T14_contract_files_still_importable_and_stable():
    from services.canonical import industrial_www as m1
    from services.canonical import leg_input_contract as m2
    from services import safe_industrial_canonical_assembler as m3
    import schemas.legal_engine as m4
    from clients import leg_runtime_client as m5

    assert hasattr(m1, "build_industrial_www_step1")
    assert hasattr(m2, "build_unified_leg_input")
    assert m3.TARGET_FIELDS == [
        "address", "ksic_major", "worker_count", "total_floor_area", "floor_count",
        "basement_count", "building_use_type", "built_year", "main_structure",
        "has_safety_manager", "electric_capacity", "has_boiler", "has_chemical_substance",
        "has_high_pressure_gas", "gas_capacity_kg", "elevator_count", "annual_energy_toe",
        "work_height_m", "has_truck_loading_unloading", "truck_loading_height_m",
        "has_manual_heavy_handling", "manual_handling_weight_kg",
        "material_profile", "business_activity_types", "building_qualifications",
        "regulated_facility_types", "hazardous_work_environments",
        "process_list", "equipment_list",
    ]
    assert hasattr(m4, "DiagnoseStep1Body")
    assert len(m5._LEG_INPUT_FIELDS) == 103
    assert len(m5._BUILDING_N1_FIELDS) == 32
