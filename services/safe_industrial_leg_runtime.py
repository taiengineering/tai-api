"""WO-DUAL-IND-STEP2-IMPLEMENT-001 GATE-4A — SAFE INDUSTRIAL 공식 LEG 진입.

경로: FROZEN assemble_industrial_marketing_contract(SAFE 자산 READ) -> canonical29
      -> consumer override(non-null) -> DiagnoseStep1Body(sector="INDUSTRIAL", input=values)
      -> run_leg_diagnosis(공식 Runtime Delegate: build_facility -> /rtm/evaluate -> full_result).

FROZEN handoff(send_industrial_canonical_to_leg / evaluate_rtm direct)는 production 미사용
(projection 검증 자산으로만 보존). canonical denominator 29 불변(신규 30번째 key 금지).

WO-SAAS-THREE-SECTOR-LEGAL-INPUT-ALIGNMENT-IMPLEMENT-001:
Safe route USER_CONFIRM mask(_SAFE_EXPLICIT_CONFIRM_FIELDS 10축) — assembler FACTORY_DIRECT가
자동 source한 값이라도 사용자 명시 확인 없이 LEG source fact가 되어서는 안 된다.
assembler 자체(assemble_industrial_marketing_contract)와 Marketing 계약은 불변.
"""
from __future__ import annotations
from typing import Any, Dict, Optional

from services.safe_industrial_canonical_assembler import (
    assemble_industrial_marketing_contract, TARGET_FIELDS, CONTRACT_VERSION,
)
from services.canonical.saas_leg_source_adapter import build_saas_leg_step1
from services.leg_diagnosis_svc import run_leg_diagnosis

# SAFE 화면에서 직접 확보 가능한 canonical override field 13 (기존6 + GATE-3 신규7).
SAFE_UI_OVERRIDE_FIELDS = (
    "ksic_major", "worker_count", "electric_capacity",
    "has_high_pressure_gas", "has_chemical_substance", "has_boiler",
    "building_use_type", "has_safety_manager", "work_height_m",
    "has_truck_loading_unloading", "truck_loading_height_m",
    "has_manual_heavy_handling", "manual_handling_weight_kg",
)

# USER_CONFIRM 10축 — Safe route에서 assembler 자동 source를 차단, consumer explicit만 허용.
# factories 등록값이 있더라도 사용자가 명시 확인하지 않으면 LEG에 전달되지 않는다.
# assembler/Marketing contract 불변 — Safe route 전용 mask.
_SAFE_EXPLICIT_CONFIRM_FIELDS = (
    "has_high_pressure_gas",
    "has_chemical_substance",
    "has_boiler",
    "building_use_type",
    "has_safety_manager",
    "work_height_m",
    "has_truck_loading_unloading",
    "truck_loading_height_m",
    "has_manual_heavy_handling",
    "manual_handling_weight_kg",
)


def run_safe_industrial_leg(supabase, factory_id: str, consumer_input) -> Dict[str, Any]:
    """SAFE INDUSTRIAL 공식 LEG 진단. full_result 반환(저장/결제 없음)."""
    # A. asset canonical (FROZEN assembler, READ ONLY)
    contract = assemble_industrial_marketing_contract(supabase, factory_id)
    values: Dict[str, Any] = dict(contract["values"])           # 정확히 29
    unresolved = set(contract.get("unresolved_fields") or [])
    provenance: Dict[str, Any] = dict(contract.get("provenance") or {})

    # B'. Safe-route USER_CONFIRM mask — assembler 이후, consumer override 이전.
    #     _SAFE_EXPLICIT_CONFIRM_FIELDS(10)는 consumer explicit confirm 없이 LEG source가 될 수 없다.
    #     factories 등록값(FACTORY_DIRECT)이 assembler를 통해 values에 들어왔더라도 제거.
    for f in _SAFE_EXPLICIT_CONFIRM_FIELDS:
        values[f] = None
        provenance[f] = {"mode": "EXPLICIT_CONFIRM_REQUIRED", "source": "safe-route-mask"}
        unresolved.add(f)

    # B. consumer override — non-null 만 우선(None=미override, false/0/""=override).
    #    Pydantic model 이면 exclude_none, dict 이면 None 제외.
    if hasattr(consumer_input, "model_dump"):
        overrides = consumer_input.model_dump(exclude_none=True)
    else:
        overrides = {k: v for k, v in dict(consumer_input or {}).items() if v is not None}
    for f in SAFE_UI_OVERRIDE_FIELDS:
        if f in overrides:
            values[f] = overrides[f]
            provenance[f] = {"mode": "CONSUMER_OVERRIDE", "source": "safe.diagnosis-step1"}
            unresolved.discard(f)     # 명시 입력으로 해소(None 은 여기 안 옴)

    # C. WO-010 STEP-2C : canonical29 final-cut 제거. TARGET_FIELDS 는 assembler 의 source contract
    #    로 계속 import(unresolved_fields 반환용) — 계약 파일 delta 0. source_facts 는 상한 없이
    #    전량 전달하고 build_saas_leg_step1 이 _LEG_INPUT_FIELDS(103) 로 필터한다. R1 축 등
    #    source 에 값이 있으면 배선 상한 없이 build_facility 에 도달, 없으면 ABSENT/UNRESOLVED 유지.
    from services.work_source.store import load_work_rows_optional
    from services.material_source.store import load_factory_material_rows_optional
    step1 = build_saas_leg_step1(
        sector="INDUSTRIAL",
        source_facts=values,
        factory_id=factory_id,
        work_rows=load_work_rows_optional(supabase, factory_id),
        # WO-OBS009-MATERIAL-CANONICAL-RUNTIME-WIRING-PATCH-001: Common Material canonical
        # adapter feeds is_managed_/is_permit_required_/is_special_management_hazardous_substance
        # into the LEG input bag. READ FAILURE != EMPTY SOURCE — MaterialSourceLoadError
        # propagates fail-closed and LEG is NOT called on material read failure.
        material_rows=load_factory_material_rows_optional(supabase, factory_id),
    )

    # D. 공식 Runtime Delegate 1회 (direct evaluate_rtm / send_industrial_canonical_to_leg 미사용).
    full_result = run_leg_diagnosis(step1)

    return {
        "full_result": full_result,
        "contract_version": CONTRACT_VERSION,
        "unresolved_fields": sorted(unresolved),
    }
