"""WO-DUAL-CST-STEP2-IMPLEMENT-001 GATE-1 — SAFE CONSTRUCTION 공식 LEG 진입.

경로: assemble_construction_marketing_contract(SAFE 자산 READ) -> canonical27
      -> consumer override(RUNTIME20, non-null) -> DiagnoseStep1Body(sector="CONSTRUCTION", input=values)
      -> run_leg_diagnosis(공식 Runtime Delegate: build_facility -> /rtm/evaluate -> full_result).

산업 GATE-4A(run_safe_industrial_leg)와 대칭. canonical denominator 27 불변.
override allowlist = RUNTIME_INPUT_FIELDS(20). subcontractor_count 는 override 대상 아님
(CANONICAL_UNRESOLVED, LEG passthrough 아님 — VERIFIER CORRECTION).
DB WRITE 0(READ-ONLY LEG diagnosis). factory 생성 side effect 0.
"""
from __future__ import annotations
from typing import Any, Dict

from services.safe_construction_canonical_assembler import (
    assemble_construction_marketing_contract, TARGET_FIELDS, CONTRACT_VERSION,
    RUNTIME_INPUT_FIELDS,
)
from services.leg_diagnosis_svc import run_leg_diagnosis
from schemas.legal_engine import DiagnoseStep1Body


class ConstructionSiteBridgeError(Exception):
    """site 에 factory_id 연결이 없을 때(진단 중 factory 생성 금지 — fail-closed)."""


# SAFE 화면에서 진단 시 명시 가능한 canonical override field(RUNTIME20).
#   assembler 가 값을 만들지 않는 위험작업/규제/has_subcontractor 축(20).
#   subcontractor_count 는 포함하지 않는다(정본 컬럼 없음 · LEG passthrough 아님).
SAFE_CST_OVERRIDE_FIELDS = tuple(RUNTIME_INPUT_FIELDS)


def run_safe_construction_leg(supabase, site_id: str, consumer_input) -> Dict[str, Any]:
    """SAFE CONSTRUCTION 공식 LEG 진단. full_result 반환(저장/결제/factory 생성 없음)."""
    # A. asset canonical (assembler, READ ONLY) — site↔factory bridge 포함.
    contract = assemble_construction_marketing_contract(supabase, site_id)
    factory_id = contract.get("factory_id")
    if not factory_id:
        # 진단 실행이 factory 를 생성하지 않는다 → fail-closed.
        raise ConstructionSiteBridgeError("현장과 시설 연결이 완료되지 않았습니다.")

    values: Dict[str, Any] = dict(contract["values"])           # 정확히 27
    unresolved = set(contract.get("unresolved_fields") or [])
    provenance: Dict[str, Any] = dict(contract.get("provenance") or {})

    # B. consumer override — RUNTIME20 만, non-null(None=미override, false/0=override).
    if hasattr(consumer_input, "model_dump"):
        overrides = consumer_input.model_dump(exclude_none=True)
    else:
        overrides = {k: v for k, v in dict(consumer_input or {}).items() if v is not None}
    for f in SAFE_CST_OVERRIDE_FIELDS:
        if f in overrides:
            values[f] = overrides[f]
            provenance[f] = {"mode": "CONSUMER_OVERRIDE", "source": "safe.construction-diagnosis"}
            unresolved.discard(f)

    # C. canonical denominator 불변: 정확히 27, TARGET_FIELDS exact.
    values = {f: values[f] for f in TARGET_FIELDS}
    assert len(values) == 27 and list(values.keys()) == list(TARGET_FIELDS)

    # D. 공식 step1 — sector=CONSTRUCTION, canonical 은 input 에.
    #    construction_type/contract_amount_eok 는 build_facility 통로상 canonical(input)에 이미 존재.
    step1 = DiagnoseStep1Body(factory_id=factory_id, sector="CONSTRUCTION", input=values)

    # E. 공식 Runtime Delegate 1회 (direct evaluate_rtm / master_building_legal_rules / v510 미사용).
    full_result = run_leg_diagnosis(step1)

    return {
        "full_result": full_result,
        "contract_version": CONTRACT_VERSION,
        "unresolved_fields": sorted(unresolved),
    }
