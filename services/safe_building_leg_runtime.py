"""WO-BLD-FINALIZATION — SAFE BUILDING 공식 LEG 진입 (industrial/construction 대칭).

경로: OWNED_EXACT 3(factories SAFE READ: floor_count/has_boiler/is_multi_use)
      + VERIFIED_SOURCE 3(employee_count→worker_count / building_area→total_floor_area /
        elevator_count; WO-SAAS-BUILDING-SOURCE-AUTHORITY-RECONCILE-001 semantic proof 확정)
      + consumer override(SafeBuildingConsumerInput, non-null) → DiagnoseStep1Body(sector="BUILDING")
      → run_leg_diagnosis(build_facility -> /rtm/evaluate -> full_result).

SEMANTIC-PROOF 반영: OWNED_EXACT 3 + VERIFIED_SOURCE 3. 나머지(runtime/UI) +
  GAS-CHEM G1/C1 3(has_high_pressure_gas/has_chemical_substance/has_hazardous_material 별개 법령)는
  consumer 명시 override 유지(WP3-BLOCKER).
build_facility N1 32 sector-gate(main 기존) + WP-1/WP3-BLOCKER-FIX(OVER-CLAIM 제거) 반영.
WO-LFR-OBJ-H01-FAST-01: building_height + floor_count on-demand hydration.
  PROVENANCE RULE: floor_count / building_height 는 building_register_updated_at non-null 일 때만
  AUTHORITATIVE. 미연결 시 hydrate_factory_h01() 로 건물대장 API 1회 호출 → factories PATCH.
DB WRITE: hydration path 한정(1 PATCH / leg call, 조건부). factory 생성 side effect 0.
"""
from __future__ import annotations
from typing import Any, Dict

from services.canonical.saas_leg_source_adapter import build_saas_leg_step1
from services.leg_diagnosis_svc import run_leg_diagnosis

# SEMANTIC-PROOF OWNED_EXACT 3 — factories exact-name SAFE READ (semantic 자명).
_SAFE_OWNED_EXACT = ("floor_count", "has_boiler", "is_multi_use")

# VERIFIED_SOURCE 3 — WO-SAAS-BUILDING-SOURCE-AUTHORITY-RECONCILE-001 semantic proof 확정.
#   employee_count = 상시근로자 수 (law_to_rules.py + safe_industrial_canonical_assembler 코드 권위)
#   building_area  = 연면적 ㎡ (building_register.py totArea 원천 확정)
#   elevator_count = 승강기 수 → build_facility 0→False / 1+→True / None→absent
#   GAS/CHEM G1/C1(has_high_pressure_gas/has_chemical_substance/has_hazardous_material):
#     WP3-BLOCKER 유지 — 별개 법령, consumer explicit 필수. 자동 승격 금지.
_SAFE_VERIFIED_SOURCE_MAP = {
    "worker_count": "employee_count",
    "total_floor_area": "building_area",
    "elevator_count": "elevator_count",
}

# factories READ columns = OWNED_EXACT 3 + VERIFIED_SOURCE factory columns
# + H01 provenance columns (building_height, building_register_updated_at). select("*") 금지.
_FACTORY_SELECT = (
    "floor_count, has_boiler, is_multi_use, "
    "employee_count, building_area, elevator_count, "
    "building_height, building_register_updated_at"
)


def _rows(res):
    return list(getattr(res, "data", None) or [])


def run_safe_building_leg(supabase, factory_id: str, consumer_input) -> Dict[str, Any]:
    """SAFE BUILDING 공식 LEG 진단. full_result 반환(저장/결제/factory 생성 없음).
    H01: building_height / floor_count provenance guard → on-demand hydration.
    """
    values: Dict[str, Any] = {}
    unresolved: set = set()

    # A. OWNED_EXACT 3 SAFE READ (factories, READ-ONLY). 값 있으면 사용, 없으면 unresolved.
    frow = (
        supabase.table("factories")
        .select(_FACTORY_SELECT)
        .eq("id", factory_id).limit(1).execute()
    )
    fac = (_rows(frow) or [{}])[0]
    for f in _SAFE_OWNED_EXACT:
        v = fac.get(f)
        if v is None:
            unresolved.add(f)
        else:
            values[f] = v

    # B. VERIFIED_SOURCE 3 — None=absent(미입력), false/0=명시값 보존. truthy filter 금지.
    #    consumer explicit(C)이 이후에 덮어쓰므로 factory값은 fallback 역할.
    for leg_key, fac_col in _SAFE_VERIFIED_SOURCE_MAP.items():
        v = fac.get(fac_col)
        if v is not None:
            values[leg_key] = v

    # H01. building_height / floor_count provenance guard.
    #   PROVENANCE RULE: building_register_updated_at non-null → AUTHORITATIVE.
    #   미연결(ts None) → on-demand hydration 1회 → factories PATCH → 재사용.
    _ts = fac.get("building_register_updated_at")
    _bh = fac.get("building_height")
    _fc_h01 = fac.get("floor_count")  # same column as OWNED_EXACT floor_count

    _h01_bh_auth = _bh is not None and _ts is not None
    _h01_fc_auth = _fc_h01 is not None and _ts is not None

    if not _h01_bh_auth or not _h01_fc_auth:
        from services.building_register_hydration import hydrate_factory_h01
        _hyd = hydrate_factory_h01(supabase, factory_id)
        if _hyd.get("updated"):
            if _hyd.get("building_height") is not None:
                _bh = _hyd["building_height"]
                _h01_bh_auth = True
            if _hyd.get("floor_count") is not None:
                _fc_h01 = _hyd["floor_count"]
                _h01_fc_auth = True
                # Promote hydrated floor_count into values (overrides OWNED_EXACT absent).
                values["floor_count"] = _fc_h01
                unresolved.discard("floor_count")

    # building_height → building_height_m (LEG alias). AUTHORITATIVE source only.
    if _h01_bh_auth and _bh is not None:
        values["building_height_m"] = _bh

    # C. consumer override — non-null 만(None=미override, false/0=명시값). extra=forbid 이미 스키마 검증.
    #    consumer explicit은 항상 factory source(A+B+H01)를 덮어쓴다.
    if hasattr(consumer_input, "model_dump"):
        overrides = consumer_input.model_dump(exclude_none=True)
    else:
        overrides = {k: v for k, v in dict(consumer_input or {}).items() if v is not None}
    for k, v in overrides.items():
        values[k] = v
        unresolved.discard(k)

    # D. WO-010 STEP-2C : unified LEG input contract 경유. values 는 OWNED_EXACT 3 + VERIFIED_SOURCE 3
    #    + H01(building_height_m / floor_count hydrated) + consumer override(SafeBuildingConsumerInput
    #    extra=forbid 로 이미 검증된 축) 병합 dict.
    #    build_saas_leg_step1 이 _LEG_INPUT_FIELDS 필터 + BUILDING alias 규약 + elevator_count
    #    derived setattr 를 적용한다. build_facility N1 32 sector-gate 는 중앙 로직 그대로.
    from services.work_source.store import load_work_rows_optional
    from services.material_source.store import load_factory_material_rows_optional
    from services.equipment_source.store import load_equipment_rows_optional
    step1 = build_saas_leg_step1(
        sector="BUILDING",
        source_facts=values,
        factory_id=factory_id,
        work_rows=load_work_rows_optional(supabase, factory_id),
        # WO-OBS009-MATERIAL-CANONICAL-RUNTIME-WIRING-PATCH-001: Common Material canonical
        # adapter feeds is_managed_/is_permit_required_/is_special_management_hazardous_substance.
        # BUILDING has_chemical_substance patch-A path preserved separately:
        # the 3 new canonical booleans are DIFFERENT keys, not aliases; no collapse.
        # READ FAILURE != EMPTY SOURCE — MaterialSourceLoadError propagates fail-closed.
        material_rows=load_factory_material_rows_optional(supabase, factory_id),
        # WO-EQUIPMENT-A2-REMAINING-CONSUMER-PARITY-IMPLEMENT-001:
        # Equipment A2 shared seam — same reader/projector as MANUFACTURING (PR #450).
        # READ FAILURE != EMPTY SOURCE — EquipmentSourceLoadError propagates fail-closed.
        equipment_rows=load_equipment_rows_optional(supabase, factory_id),
    )

    # E. 공식 Runtime Delegate 1회.
    full_result = run_leg_diagnosis(step1)

    return {
        "full_result": full_result,
        "contract_version": "SAFE_BUILDING_LEG_V1",
        "unresolved_fields": sorted(unresolved),
    }
