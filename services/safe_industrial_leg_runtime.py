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
# WO-008: +2 (appendix3_item_no, is_real_estate_management) — source facts only.
# expected_app3_revision은 control field이므로 포함하지 않는다.
SAFE_UI_OVERRIDE_FIELDS = (
    "ksic_major", "worker_count", "electric_capacity",
    "has_high_pressure_gas", "has_chemical_substance", "has_boiler",
    "building_use_type", "has_safety_manager", "work_height_m",
    "has_truck_loading_unloading", "truck_loading_height_m",
    "has_manual_heavy_handling", "manual_handling_weight_kg",
    # WO-008 source facts
    "appendix3_item_no", "is_real_estate_management",
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


def collect_industrial_leg_input(
    supabase,
    factory_id: str,
    consumer_input,
    app3_projection: Optional[Dict[str, Any]] = None,
):
    """INDUSTRIAL 입력 조립(A-C단계). LEG 미호출, DB 쓰기 없음.

    반환 (step1, sorted_unresolved_fields).
    WP01-A 비교 모듈이 재사용한다.
    """
    from services.work_source.store import load_work_rows_optional
    from services.material_source.store import load_factory_material_rows_optional
    from services.equipment_source.store import load_equipment_rows_optional

    # A. asset canonical (FROZEN assembler, READ ONLY)
    contract = assemble_industrial_marketing_contract(supabase, factory_id)
    values: Dict[str, Any] = dict(contract["values"])           # 정확히 29
    unresolved = set(contract.get("unresolved_fields") or [])
    provenance: Dict[str, Any] = dict(contract.get("provenance") or {})

    # B'. Safe-route USER_CONFIRM mask — assembler 이후, consumer override 이전.
    for f in _SAFE_EXPLICIT_CONFIRM_FIELDS:
        values[f] = None
        provenance[f] = {"mode": "EXPLICIT_CONFIRM_REQUIRED", "source": "safe-route-mask"}
        unresolved.add(f)

    # B. consumer override — non-null 만(None=미override, false/0/""=override).
    if hasattr(consumer_input, "model_dump"):
        overrides = consumer_input.model_dump(exclude_none=True)
    else:
        overrides = {k: v for k, v in dict(consumer_input or {}).items() if v is not None}
    for f in SAFE_UI_OVERRIDE_FIELDS:
        if f in overrides:
            values[f] = overrides[f]
            provenance[f] = {"mode": "CONSUMER_OVERRIDE", "source": "safe.diagnosis-step1"}
            unresolved.discard(f)

    # B''. WO-008: server AP01-05 projection injection (flag ON only).
    if app3_projection:
        for leaf_key, leaf_val in app3_projection.items():
            values[leaf_key] = leaf_val

    # C. build_saas_leg_step1 — _LEG_INPUT_FIELDS(103) 필터, LEG 미호출.
    step1 = build_saas_leg_step1(
        sector="INDUSTRIAL",
        source_facts=values,
        factory_id=factory_id,
        work_rows=load_work_rows_optional(supabase, factory_id),
        material_rows=load_factory_material_rows_optional(supabase, factory_id),
        equipment_rows=load_equipment_rows_optional(supabase, factory_id),
    )
    return step1, sorted(unresolved)


def run_safe_industrial_leg(
    supabase,
    factory_id: str,
    consumer_input,
    app3_projection: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """SAFE INDUSTRIAL 공식 LEG 진단. full_result 반환(저장/결제 없음).

    app3_projection: WO-008 서버 생성 AP01-05 leaves (flag ON 시만 비None).
                     consumer override 이후, build_saas_leg_step1 이전에 values에 주입.
    """
    step1, unresolved_fields = collect_industrial_leg_input(
        supabase, factory_id, consumer_input, app3_projection
    )
    # D. 공식 Runtime Delegate 1회 (direct evaluate_rtm / send_industrial_canonical_to_leg 미사용).
    full_result = run_leg_diagnosis(step1)
    return {
        "full_result": full_result,
        "contract_version": CONTRACT_VERSION,
        "unresolved_fields": unresolved_fields,
    }
