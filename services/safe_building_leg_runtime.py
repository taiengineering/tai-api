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

from services.leg_diagnosis_svc import run_leg_diagnosis
from schemas.legal_engine import DiagnoseStep1Body

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

    # C. 공식 step1 — sector=BUILDING, canonical 은 input 에(build_facility 가 N1 32 sector-gate 처리).
    step1 = DiagnoseStep1Body(factory_id=factory_id, sector="BUILDING", input=values)

    # D. 공식 Runtime Delegate 1회.
    full_result = run_leg_diagnosis(step1)

    return {
        "full_result": full_result,
        "contract_version": "SAFE_BUILDING_LEG_V1",
        "unresolved_fields": sorted(unresolved),
    }
