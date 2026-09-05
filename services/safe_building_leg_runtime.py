"""WO-BLD-FINALIZATION — SAFE BUILDING 공식 LEG 진입 (industrial/construction 대칭).

경로: OWNED_EXACT 3(factories SAFE READ: floor_count/has_boiler/is_multi_use)
      + consumer override(SafeBuildingConsumerInput, non-null) → DiagnoseStep1Body(sector="BUILDING")
      → run_leg_diagnosis(build_facility -> /rtm/evaluate -> full_result).

SEMANTIC-PROOF 반영: BUILDING SAFE 자산 재사용 = OWNED_EXACT 3축만(대장 파생은 실데이터 부재 +
  semantic 미증명 PROOF_FAIL). 나머지 45(runtime/UI) + GAS-CHEM G1/C1 3(has_high_pressure_gas/
  has_chemical_substance/has_hazardous_material 별개 법령)는 consumer 명시 override.
build_facility N1 32 sector-gate(main 기존) + WP-1/WP3-BLOCKER-FIX(OVER-CLAIM 제거) 반영.
DB WRITE 0 (READ-ONLY LEG diagnosis). factory 생성 side effect 0.
"""
from __future__ import annotations
from typing import Any, Dict

from services.canonical.saas_leg_source_adapter import build_saas_leg_step1
from services.leg_diagnosis_svc import run_leg_diagnosis

# SEMANTIC-PROOF OWNED_EXACT 3 — factories exact-name SAFE READ (semantic 자명).
_SAFE_OWNED_EXACT = ("floor_count", "has_boiler", "is_multi_use")


def _rows(res):
    return list(getattr(res, "data", None) or [])


def run_safe_building_leg(supabase, factory_id: str, consumer_input) -> Dict[str, Any]:
    """SAFE BUILDING 공식 LEG 진단. full_result 반환(저장/결제/factory 생성 없음)."""
    values: Dict[str, Any] = {}
    unresolved: set = set()

    # A. OWNED_EXACT 3 SAFE READ (factories, READ-ONLY). 값 있으면 사용, 없으면 unresolved.
    frow = (
        supabase.table("factories")
        .select("floor_count, has_boiler, is_multi_use")
        .eq("id", factory_id).limit(1).execute()
    )
    fac = (_rows(frow) or [{}])[0]
    for f in _SAFE_OWNED_EXACT:
        v = fac.get(f)
        if v is None:
            unresolved.add(f)
        else:
            values[f] = v

    # B. consumer override — non-null 만(None=미override, false/0=명시값). extra=forbid 이미 스키마 검증.
    if hasattr(consumer_input, "model_dump"):
        overrides = consumer_input.model_dump(exclude_none=True)
    else:
        overrides = {k: v for k, v in dict(consumer_input or {}).items() if v is not None}
    for k, v in overrides.items():
        values[k] = v
        unresolved.discard(k)

    # C. WO-010 STEP-2C : unified LEG input contract 경유. values 는 OWNED_EXACT 3 + consumer
    #    override(SafeBuildingConsumerInput extra=forbid 로 이미 검증된 축) 병합 dict. 상한 없이
    #    전량 전달하고 build_saas_leg_step1 이 _LEG_INPUT_FIELDS(103) 필터 + BUILDING alias 규약
    #    (has_chemical 승격 스킵 · has_chemical_substance exact-key patch-A 경로 유지) + elevator_count
    #    derived setattr 를 적용한다. build_facility N1 32 sector-gate 는 중앙 로직 그대로.
    step1 = build_saas_leg_step1(
        sector="BUILDING", source_facts=values, factory_id=factory_id,
    )

    # D. 공식 Runtime Delegate 1회.
    full_result = run_leg_diagnosis(step1)

    return {
        "full_result": full_result,
        "contract_version": "SAFE_BUILDING_LEG_V1",
        "unresolved_fields": sorted(unresolved),
    }
