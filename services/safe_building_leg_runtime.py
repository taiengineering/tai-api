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
from typing import Any, Dict, Optional

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


def collect_building_leg_input(
    supabase,
    factory_id: str,
    consumer_input,
    material_inout_event_id: str = None,
    occupancy_assessment_id: str = None,
    app3_projection=None,
    *,
    allow_h01_db_write: bool = True,
    company_id: Optional[str] = None,
):
    """BUILDING 입력 조립(A-D단계). LEG 미호출.

    allow_h01_db_write=False(WP01-A 비교용): H01 on-demand hydration DB WRITE 차단.
      H01 미인증 필드는 absent 처리. 반환값 h01_absent_fields에 해당 필드명 포함.

    반환 (step1, sorted_unresolved, h01_absent_fields).
    h01_absent_fields: H01 write 없이 확인 불가한 필드 집합 (빈 set이면 모두 인증됨).
    """
    from services.work_source.store import load_work_rows_optional
    from services.material_source.store import load_factory_material_rows_optional
    from services.equipment_source.store import load_equipment_rows_optional

    values: Dict[str, Any] = {}
    unresolved: set = set()
    h01_absent_fields: set = set()

    # A. OWNED_EXACT 2 SAFE READ (factories, READ-ONLY).
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

    # B. VERIFIED_SOURCE 3
    for leg_key, fac_col in _SAFE_VERIFIED_SOURCE_MAP.items():
        v = fac.get(fac_col)
        if v is not None:
            values[leg_key] = v

    # H01. floor_count + building_height provenance guard.
    _ts = fac.get("building_register_updated_at")
    _bh = fac.get("building_height")
    _fc_h01 = fac.get("floor_count")
    _mgm_pk = fac.get("mgm_bldrgst_pk") or None
    _bdmgtsn = str(fac.get("bdmgtsn") or "").strip()

    _h01_bh_auth = _bh is not None and _ts is not None and _mgm_pk is not None
    _h01_fc_auth = _fc_h01 is not None and _ts is not None and _mgm_pk is not None

    if not _h01_bh_auth or not _h01_fc_auth:
        if allow_h01_db_write:
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
        else:
            # WP01-A: DB write 차단 — 미인증 H01 필드를 absent로 기록
            if not _h01_fc_auth:
                h01_absent_fields.add("floor_count")
            if not _h01_bh_auth:
                h01_absent_fields.add("building_height_m")

    if _h01_fc_auth and _fc_h01 is not None:
        values["floor_count"] = _fc_h01
        unresolved.discard("floor_count")
    else:
        unresolved.add("floor_count")

    if _h01_bh_auth and _bh is not None:
        values["building_height_m"] = _bh

    # H03. floor_area_sum_at_or_above_11f derivation (READ-ONLY).
    if _h01_fc_auth and _fc_h01 is not None and _fc_h01 >= 11:
        if _bdmgtsn and len(_bdmgtsn) == 19:
            from services.building_floor_hydration import resolve_floor_area_sum_11f_plus
            _h03 = resolve_floor_area_sum_11f_plus(_bdmgtsn, _mgm_pk)
            if _h03.get("resolved"):
                values["floor_area_sum_at_or_above_11f"] = _h03["value"]

    # P4A. Hazardous material event source binding.
    if material_inout_event_id is not None:
        from services.hazardous_material_event_source.store import load_confirmed_event_context
        from services.hazardous_material_event_source.canonical_adapter import (
            project_hazardous_material_event_fact,
        )
        event_ctx = load_confirmed_event_context(
            supabase, factory_id=factory_id, event_id=material_inout_event_id,
        )
        event_fact = project_hazardous_material_event_fact(event_ctx)
        if event_fact:
            values["has_hazardous_material_in_out_event"] = True

    # H02. occupancy_capacity.
    if occupancy_assessment_id is not None:
        from services.occupancy_capacity.canonical_adapter import load_confirmed_assessment_context
        occ_ctx = load_confirmed_assessment_context(
            supabase, assessment_id=occupancy_assessment_id, factory_id=factory_id,
        )
        values["occupancy_capacity"] = occ_ctx["occupancy_capacity"]
        unresolved.discard("occupancy_capacity")

    # C. consumer override
    if hasattr(consumer_input, "model_dump"):
        overrides = consumer_input.model_dump(exclude_none=True)
    else:
        overrides = {k: v for k, v in dict(consumer_input or {}).items() if v is not None}
    for k, v in overrides.items():
        values[k] = v
        unresolved.discard(k)

    # C'. WO-008: app3_projection
    if app3_projection:
        for leaf_key, leaf_val in app3_projection.items():
            values[leaf_key] = leaf_val

    # WIRING-012: L1 company_id → CHEM L4 DIRECT load (fail-closed: re-raise on error).
    chemical_facts = None
    if company_id:
        from clients.chem_internal_client import load_chemical_facts
        chemical_facts = load_chemical_facts(factory_id, company_id)

    # D. build_saas_leg_step1
    step1 = build_saas_leg_step1(
        sector="BUILDING",
        source_facts=values,
        factory_id=factory_id,
        work_rows=load_work_rows_optional(supabase, factory_id),
        material_rows=load_factory_material_rows_optional(supabase, factory_id),
        equipment_rows=load_equipment_rows_optional(supabase, factory_id),
        chemical_facts=chemical_facts,
    )
    return step1, sorted(unresolved), h01_absent_fields


def run_safe_building_leg(
    supabase,
    factory_id: str,
    consumer_input,
    material_inout_event_id: str = None,
    occupancy_assessment_id: str = None,
    app3_projection=None,
    company_id: Optional[str] = None,
) -> Dict[str, Any]:
    """SAFE BUILDING 공식 LEG 진단. full_result 반환(저장/결제/factory 생성 없음).

    app3_projection: WO-008 서버 생성 AP01-05 leaves (flag ON 시만 비None).
    H01: floor_count / building_height provenance guard → on-demand hydration.
    H03: floor_area_sum_at_or_above_11f derivation (authoritative floor_count >= 11 시).
    H02: occupancy_capacity — direct numeric input PROHIBITED; exact assessment only.
    company_id: WIRING-012 L1 인증 회사 ID. None이면 CHEM 미호출(backward-compat).
    """
    step1, unresolved_fields, _ = collect_building_leg_input(
        supabase, factory_id, consumer_input,
        material_inout_event_id=material_inout_event_id,
        occupancy_assessment_id=occupancy_assessment_id,
        app3_projection=app3_projection,
        allow_h01_db_write=True,
        company_id=company_id,
    )
    # E. 공식 Runtime Delegate 1회.
    full_result = run_leg_diagnosis(step1)
    return {
        "full_result": full_result,
        "contract_version": "SAFE_BUILDING_LEG_V1",
        "unresolved_fields": unresolved_fields,
    }
