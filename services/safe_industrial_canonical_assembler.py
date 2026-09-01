"""services/safe_industrial_canonical_assembler.py

WO-SAFE-LEGAL-IND-CANONICAL-IMPLEMENT-001 / STEP7 — INDUSTRIAL canonical → Marketing 29 assembler.

실제 SaaS 자산(factories / factory_process / equipment_assets / factory_materials)을 READ-ONLY 로 읽어
Marketing INDUSTRIAL 계약(MKT_IND_PAID_CONTRACT_V1, 29 target)으로 조립한다. 저장모델/진단엔진 미접촉.

원칙:
  - source NULL → output NULL. NULL→false/0/[] 승격 금지. 추정/현재연도/LLM/fuzzy 금지(no-invention).
  - false/0/[] 는 보존(truthy filter 금지).
  - vocabulary(business_activity/hazardous_environment/building_composition/regulatory_designation)는
    system_codes code → code_name EXACT 변환. unknown code 하나라도 있으면 그 field = NULL + unresolved.
  - 법적 판단(의무관리대상 공동주택 / 안전성평가 대상시설 등) 신규 로직 작성 금지 → 미해결 시 NULL + unresolved.
  - is_hazardous_material/sewage 단순 가정으로 규제시설 자동출력 금지.
  - table/row 중 하나라도 정확히 표현 불가하면 해당 table field 전체 = NULL + unresolved(조용히 버리지 않음).
  - diagnosis_input_fields 미조회(29 계약은 코드 frozen constant). DB WRITE 0.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

CONTRACT_VERSION = "MKT_IND_PAID_CONTRACT_V1"
SECTOR = "INDUSTRIAL"

# frozen 29 target (순서 고정)
TARGET_FIELDS = [
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

# factories 직접 매핑 (target -> factories column). worker_count=employee_count ONLY(total_worker_count_calc 금지).
FACTORY_DIRECT = {
    "address": "site_address",
    "ksic_major": "ksic_code",
    "worker_count": "employee_count",
    "total_floor_area": "building_area",
    "floor_count": "floor_count",
    "basement_count": "underground_floor_count",
    "built_year": "completion_year",
    "has_safety_manager": "has_safety_manager",
    "electric_capacity": "electrical_capacity_kw",
    "has_boiler": "has_boiler",
    "has_chemical_substance": "has_chemical_substance",
    "has_high_pressure_gas": "has_high_pressure_gas",
    "gas_capacity_kg": "gas_capacity_kg",
    "elevator_count": "elevator_count",
    "annual_energy_toe": "annual_energy_toe",
    "work_height_m": "work_height_m",
    "has_truck_loading_unloading": "has_truck_loading_unloading",
    "truck_loading_height_m": "truck_loading_height_m",
    "has_manual_heavy_handling": "has_manual_heavy_handling",
    "manual_handling_weight_kg": "manual_handling_weight_kg",
}
# rename(다른 이름) = TRANSFORM, 동일 이름 passthrough = DIRECT
_TRANSFORM_RENAMES = {
    "ksic_major", "worker_count", "total_floor_area", "basement_count", "built_year",
    "electric_capacity",
}

VOCAB_ARRAY_MAP = {  # target -> (factories column, system_codes category)
    "business_activity_types": ("business_activity_types", "factory_business_activity"),
    "hazardous_work_environments": ("hazardous_work_environments", "factory_hazardous_environment"),
    "building_qualifications": ("building_composition_codes", "factory_building_composition"),
    "regulated_facility_types": ("regulatory_designation_codes", "factory_regulatory_designation"),
}


def _rows(res) -> List[dict]:
    return list(getattr(res, "data", None) or [])


def _load_code_name_map(supabase, category: str) -> Dict[str, str]:
    res = (
        supabase.table("system_codes")
        .select("code, code_name")
        .eq("category", category)
        .eq("is_active", True)
        .execute()
    )
    out: Dict[str, str] = {}
    for r in _rows(res):
        if r.get("code") is not None:
            out[r["code"]] = r.get("code_name")
    return out


def assemble_industrial_marketing_contract(supabase, factory_id: str) -> Dict[str, Any]:
    values: Dict[str, Any] = {}
    provenance: Dict[str, Dict[str, Any]] = {}
    unresolved: set = set()

    def _resolve(field, value, mode, source):
        values[field] = value
        provenance[field] = {"mode": mode, "source": source}

    def _unresolved(field, source):
        values[field] = None
        provenance[field] = {"mode": "UNRESOLVED", "source": source}
        unresolved.add(field)

    # ── factories (single row) ──
    fac_res = supabase.table("factories").select("*").eq("id", factory_id).limit(1).execute()
    fac_rows = _rows(fac_res)
    fac = fac_rows[0] if fac_rows else {}

    for field, col in FACTORY_DIRECT.items():
        mode = "TRANSFORM" if field in _TRANSFORM_RENAMES else "DIRECT"
        _resolve(field, fac.get(col), mode, f"factories.{col}")  # None/false/0 보존

    # ── building_use_type / main_structure : deterministic normalization 없음 → unresolved (no-invention) ──
    # building_use_code / building_structure_code 의 Marketing accepted-enum exact map 이 확정되지 않았으므로
    # 신규 fuzzy/추정 금지. 미해결로 남긴다(override 저장 금지).
    if fac.get("building_use_code") is None:
        _resolve("building_use_type", None, "DIRECT", "factories.building_use_code")
    else:
        _unresolved("building_use_type", "factories.building_use_code(정규화 매핑 미확정)")
    if fac.get("building_structure_code") is None and fac.get("building_structure_name") is None:
        _resolve("main_structure", None, "DIRECT", "factories.building_structure_code")
    else:
        _unresolved("main_structure", "factories.building_structure_code(정규화 매핑 미확정)")

    # ── vocabulary arrays (code[] → code_name[]) ──
    for field, (col, category) in VOCAB_ARRAY_MAP.items():
        raw = fac.get(col)
        if raw is None:
            _resolve(field, None, "TRANSFORM", f"factories.{col}")
            continue
        if raw == []:
            _resolve(field, [], "TRANSFORM", f"factories.{col}")
            continue
        code_map = _load_code_name_map(supabase, category)
        labels = []
        ok = True
        for code in raw:
            if code in code_map and code_map[code] is not None:
                labels.append(code_map[code])
            else:
                ok = False
                break
        if ok:
            _resolve(field, labels, "TRANSFORM", f"factories.{col}->{category}")
        else:
            _unresolved(field, f"factories.{col}->{category}(unknown code)")

    # building_qualifications / regulated_facility_types 는 위에서 direct code 매핑만 수행.
    # 법적 파생(의무관리대상/안전성평가) 및 physical-derive 는 STEP7 에서 신규 작성 금지 →
    # 매핑 성공해도 "composite 완전성"이 별도 승인 로직 없이는 보장되지 않으므로 provenance mode 를 COMPOSITE 로 표기.
    for f in ("building_qualifications", "regulated_facility_types"):
        if provenance.get(f, {}).get("mode") == "TRANSFORM":
            provenance[f]["mode"] = "COMPOSITE"

    # ── material_profile (factory_materials active) ──
    mat_res = (
        supabase.table("factory_materials")
        .select("material_name, material_category_code, handling_mode_codes, is_active")
        .eq("factory_id", factory_id)
        .eq("is_active", True)
        .execute()
    )
    mat_rows = _rows(mat_res)
    if not mat_rows:
        _resolve("material_profile", None, "COMPOSITE", "factory_materials")
    else:
        rows_out = []
        ok = True
        for m in mat_rows:
            if m.get("material_category_code") is None:  # Marketing row 로 정확 표현 불가
                ok = False
                break
            rows_out.append({
                "material_category": m.get("material_category_code"),
                "handling_modes": m.get("handling_mode_codes"),   # None/[] 보존
            })
        if ok:
            _resolve("material_profile", rows_out, "COMPOSITE", "factory_materials")
        else:
            _unresolved("material_profile", "factory_materials(category 결측 row)")

    # ── process_list (factory_process active) ──
    proc_res = (
        supabase.table("factory_process")
        .select("process_name_manual, process_lv1, process_lv2, process_lv3, process_lv4, "
                "hazard_codes, worker_count, is_primary, activity_types, is_active")
        .eq("factory_id", factory_id)
        .eq("is_active", True)
        .execute()
    )
    proc_rows = _rows(proc_res)
    if not proc_rows:
        _resolve("process_list", None, "COMPOSITE", "factory_process")
    else:
        rows_out = []
        ok = True
        for p in proc_rows:
            name = (p.get("process_name_manual") or p.get("process_lv4") or p.get("process_lv3")
                    or p.get("process_lv2") or p.get("process_lv1"))
            if not name:   # 이름 없는 active row → 전체 불완전
                ok = False
                break
            rows_out.append({
                "process_name": name,
                "hazard_codes": p.get("hazard_codes"),
                "worker_count": p.get("worker_count"),
                "is_primary": p.get("is_primary"),
                "activity_type": p.get("activity_types"),   # key singular, value multi(array)
            })
        if ok:
            _resolve("process_list", rows_out, "COMPOSITE", "factory_process")
        else:
            _unresolved("process_list", "factory_process(이름 결측 row)")

    # ── equipment_list (equipment_assets operating) ──
    eq_res = (
        supabase.table("equipment_assets")
        .select("equipment_type_code, asset_name, quantity, capacity_value, capacity_unit, "
                "is_legal_target, usage_types, relation_types, is_operating")
        .eq("factory_id", factory_id)
        .eq("is_operating", True)
        .execute()
    )
    eq_rows = _rows(eq_res)
    if not eq_rows:
        _resolve("equipment_list", None, "COMPOSITE", "equipment_assets")
    else:
        rows_out = []
        for e in eq_rows:
            rows_out.append({
                "equipment_type": e.get("equipment_type_code"),
                "asset_name": e.get("asset_name"),
                "quantity": e.get("quantity"),
                "capacity_value": e.get("capacity_value"),
                "capacity_unit": e.get("capacity_unit"),
                "is_legal_target": e.get("is_legal_target"),
                "usage_type": e.get("usage_types"),
                "relation_type": e.get("relation_types"),
                # factory_process_id 는 transport field 아님 → 미출력
            })
        _resolve("equipment_list", rows_out, "COMPOSITE", "equipment_assets")

    # 29 정합성(안전망)
    for f in TARGET_FIELDS:
        if f not in values:
            _unresolved(f, "MISSING")

    return {
        "contract_version": CONTRACT_VERSION,
        "sector": SECTOR,
        "factory_id": factory_id,
        "values": {f: values[f] for f in TARGET_FIELDS},   # 정확히 29, 순서 고정
        "unresolved_fields": sorted(unresolved),
        "provenance": provenance,
    }
