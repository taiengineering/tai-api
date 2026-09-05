"""WO-DUAL-IND-STEP2-IMPLEMENT-001 GATE-4A — SAFE INDUSTRIAL 공식 LEG 진입.

경로: FROZEN assemble_industrial_marketing_contract(SAFE 자산 READ) -> canonical29
      -> consumer override(non-null) -> DiagnoseStep1Body(sector="INDUSTRIAL", input=values)
      -> run_leg_diagnosis(공식 Runtime Delegate: build_facility -> /rtm/evaluate -> full_result).

FROZEN handoff(send_industrial_canonical_to_leg / evaluate_rtm direct)는 production 미사용
(projection 검증 자산으로만 보존). canonical denominator 29 불변(신규 30번째 key 금지).
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


def run_safe_industrial_leg(supabase, factory_id: str, consumer_input) -> Dict[str, Any]:
    """SAFE INDUSTRIAL 공식 LEG 진단. full_result 반환(저장/결제 없음)."""
    # A. asset canonical (FROZEN assembler, READ ONLY)
    contract = assemble_industrial_marketing_contract(supabase, factory_id)
    values: Dict[str, Any] = dict(contract["values"])           # 정확히 29
    unresolved = set(contract.get("unresolved_fields") or [])
    provenance: Dict[str, Any] = dict(contract.get("provenance") or {})

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
    step1 = build_saas_leg_step1(
        sector="INDUSTRIAL", source_facts=values, factory_id=factory_id,
    )

    # D. 공식 Runtime Delegate 1회 (direct evaluate_rtm / send_industrial_canonical_to_leg 미사용).
    full_result = run_leg_diagnosis(step1)

    return {
        "full_result": full_result,
        "contract_version": CONTRACT_VERSION,
        "unresolved_fields": sorted(unresolved),
    }
