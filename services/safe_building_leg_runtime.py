"""WO-BLD-FINALIZATION — SAFE BUILDING 공식 LEG 진입 (industrial/construction 대칭).

경로: OWNED_EXACT 2(factories SAFE READ: has_boiler/is_multi_use)
      + VERIFIED_SOURCE 3(employee_count→worker_count / building_area→total_floor_area /
        elevator_count; WO-SAAS-BUILDING-SOURCE-AUTHORITY-RECONCILE-001 semantic proof 확정)
      + consumer override(SafeBuildingConsumerInput, non-null) → DiagnoseStep1Body(sector="BUILDING")
      → run_leg_diagnosis(build_facility -> /rtm/evaluate -> full_result).

SEMANTIC-PROOF 반영: OWNED_EXACT 2 + VERIFIED_SOURCE 3. 나머지(runtime/UI) +
  GAS-CHEM G1/C1 3(has_high_pressure_gas/has_chemical_substance/has_hazardous_material 별개 법령)는
  consumer 명시 override 유지(WP3-BLOCKER).
build_facility N1 32 sector-gate(main 기존) + WP-1/WP3-BLOCKER-FIX(OVER-CLAIM 제거) 반영.
WO-LFR-OBJ-H01-FAST-01: building_height + floor_count on-demand hydration.
WO-LFR-OBJ-H03-FAST-01: floor_area_sum_at_or_above_11f derivation from 층별개요 API.
  H01 PROVENANCE CORRECTION: floor_count는 building_register_updated_at non-null 일 때만
  AUTHORITATIVE. timestamp 없는 기존 floor_count → LEG input 주입 금지.
  H03 TRIGGER: authoritative floor_count >= 11 일 때만 H03 derivation 실행.
DB WRITE: H01 hydration path 한정(1 PATCH / leg call, 조건부). factory 생성 side effect 0.
"""
from __future__ import annotations
from typing import Any, Dict

from services.canonical.saas_leg_source_adapter import build_saas_leg_step1
from services.leg_diagnosis_svc import run_leg_diagnosis

# SEMANTIC-PROOF OWNED_EXACT 2 — factories exact-name SAFE READ (semantic 자명).
# floor_count는 H01 provenance block에서만 주입 (timestamp 확인 후).
_SAFE_OWNED_EXACT = ("has_boiler", "is_multi_use")

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

# factories READ columns = OWNED_EXACT 2 + VERIFIED_SOURCE factory columns
# + H01 provenance columns + H03 entity identity columns. select("*") 금지.
_FACTORY_SELECT = (
    "has_boiler, is_multi_use, "
    "employee_count, building_area, elevator_count, "
    "floor_count, building_height, building_register_updated_at, "
    "bdmgtsn, mgm_bldrgst_pk"
)


def _rows(res):
    return list(getattr(res, "data", None) or [])


def run_safe_building_leg(
    supabase,
    factory_id: str,
    consumer_input,
    material_inout_event_id: str = None,
    occupancy_assessment_id: str = None,
) -> Dict[str, Any]:
    """SAFE BUILDING 공식 LEG 진단. full_result 반환(저장/결제/factory 생성 없음).
    H01: floor_count / building_height provenance guard → on-demand hydration.
    H03: floor_area_sum_at_or_above_11f derivation (authoritative floor_count >= 11 시).
    H02: occupancy_capacity — direct numeric input PROHIBITED; exact assessment only.
    """
    values: Dict[str, Any] = {}
    unresolved: set = set()

    # A. OWNED_EXACT 2 SAFE READ (factories, READ-ONLY). floor_count는 H01 provenance block.
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

    # H01. floor_count + building_height provenance guard.
    #   PROVENANCE RULE: building_register_updated_at non-null → AUTHORITATIVE.
    #   timestamp 없는 floor_count → LEG input 주입 금지.
    #   미연결(ts None) → on-demand hydration 1회 → factories PATCH.
    _ts = fac.get("building_register_updated_at")
    _bh = fac.get("building_height")
    _fc_h01 = fac.get("floor_count")
    _mgm_pk = fac.get("mgm_bldrgst_pk") or None
    _bdmgtsn = str(fac.get("bdmgtsn") or "").strip()

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
            if _hyd.get("mgm_bldrgst_pk"):
                _mgm_pk = _hyd["mgm_bldrgst_pk"]

    # floor_count: AUTHORITATIVE source only (provenance confirmed).
    if _h01_fc_auth and _fc_h01 is not None:
        values["floor_count"] = _fc_h01
        unresolved.discard("floor_count")
    else:
        unresolved.add("floor_count")

    # building_height → building_height_m (LEG alias). AUTHORITATIVE source only.
    if _h01_bh_auth and _bh is not None:
        values["building_height_m"] = _bh

    # H03. floor_area_sum_at_or_above_11f derivation.
    #   TRIGGER: authoritative floor_count >= 11 only. H01 precondition required.
    #   direct user input workaround closed (removed from SafeBuildingConsumerInput).
    if _h01_fc_auth and _fc_h01 is not None and _fc_h01 >= 11:
        if _bdmgtsn and len(_bdmgtsn) == 19:
            from services.building_floor_hydration import resolve_floor_area_sum_11f_plus
            _h03 = resolve_floor_area_sum_11f_plus(_bdmgtsn, _mgm_pk)
            if _h03.get("resolved"):
                values["floor_area_sum_at_or_above_11f"] = _h03["value"]

    # P4A. Hazardous material event source binding.
    #   Exact CONFIRMED event_id + same factory → canonical TRUE only.
    #   No event_id → 0 DB reads, fact absent.
    #   DB failure → HazardousMaterialEventSourceLoadError propagated to router (503).
    if material_inout_event_id is not None:
        from services.hazardous_material_event_source.store import load_confirmed_event_context
        from services.hazardous_material_event_source.canonical_adapter import (
            project_hazardous_material_event_fact,
        )
        event_ctx = load_confirmed_event_context(
            supabase,
            factory_id=factory_id,
            event_id=material_inout_event_id,
        )
        event_fact = project_hazardous_material_event_fact(event_ctx)
        if event_fact:
            values["has_hazardous_material_in_out_event"] = True

    # H02. occupancy_capacity — exact CONFIRMED assessment source only (no direct numeric injection).
    #   occupancy_assessment_id absent → fact not injected (SOURCE_UNRESOLVED, LEG runs without it).
    #   Wrong factory / not CONFIRMED / stale ruleset → SourceUnresolved propagated to caller.
    if occupancy_assessment_id is not None:
        from services.occupancy_capacity.canonical_adapter import load_confirmed_assessment_context
        occ_ctx = load_confirmed_assessment_context(
            supabase,
            assessment_id=occupancy_assessment_id,
            factory_id=factory_id,
        )
        values["occupancy_capacity"] = occ_ctx["occupancy_capacity"]
        unresolved.discard("occupancy_capacity")

    # C. consumer override — non-null 만(None=미override, false/0=명시값). extra=forbid 이미 스키마 검증.
    #    consumer explicit은 항상 factory source(A+B+H01+H03)를 덮어쓴다.
    if hasattr(consumer_input, "model_dump"):
        overrides = consumer_input.model_dump(exclude_none=True)
    else:
        overrides = {k: v for k, v in dict(consumer_input or {}).items() if v is not None}
    for k, v in overrides.items():
        values[k] = v
        unresolved.discard(k)

    # D. WO-010 STEP-2C : unified LEG input contract 경유.
    from services.work_source.store import load_work_rows_optional
    from services.material_source.store import load_factory_material_rows_optional
    from services.equipment_source.store import load_equipment_rows_optional
    step1 = build_saas_leg_step1(
        sector="BUILDING",
        source_facts=values,
        factory_id=factory_id,
        work_rows=load_work_rows_optional(supabase, factory_id),
        material_rows=load_factory_material_rows_optional(supabase, factory_id),
        equipment_rows=load_equipment_rows_optional(supabase, factory_id),
    )

    # E. 공식 Runtime Delegate 1회.
    full_result = run_leg_diagnosis(step1)

    return {
        "full_result": full_result,
        "contract_version": "SAFE_BUILDING_LEG_V1",
        "unresolved_fields": sorted(unresolved),
    }
