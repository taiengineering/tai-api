"""services/safe_building_canonical_assembler.py

WO-SAFE-LEGAL-BLD-CANONICAL-IMPLEMENT-001 / STEP4 — BUILDING factories → Marketing 36 assembler.

실제 건물 canonical root(factories) 단일 row 만 READ-ONLY 로 읽어 Marketing BUILDING PAID 누적계약
(MKT_BLD_PAID_CONTRACT_V1, 36 target)으로 조립한다. 저장모델/라우터/진단엔진/LEG 미접촉.
INDUSTRIAL assembler 와 동일 패턴(frozen target · provenance · unresolved · no-invention · DB WRITE 0)만 재사용한다.

원칙:
  - factories 단일 row 외 어떤 테이블도 조회하지 않는다(buildings/facility_profiles/system_codes/
    diagnosis_input_fields/equipment/process/materials 미조회). DB WRITE 0.
  - source NULL → output NULL. NULL→false/0/[] 승격 금지. 추정/현재연도/LLM/fuzzy 금지(no-invention).
  - false/0/[] 는 보존(truthy filter 금지). NULL = unknown.
  - E5(building_use_type·main_structure·is_multi_use·is_energy_intensive·building_grade)는 DB 값 유무와 무관하게 항상 NULL + UNRESOLVED.
  - has_chemical ← factories.has_chemical_substance (exact semantic rename). output 에 has_chemical_substance key 미생성.
  - address 는 road→jibun fallback + detail 결합의 고정 B transform(site_address/sido/sigungu/dong 미사용).
  - multi_use_type 은 structural(list·StrictStr·nonblank)만 검증; vocabulary 검증 0. capacity/required/multi_use_type 로 boolean 파생 0.
"""
from __future__ import annotations

from typing import Any, Dict, List

CONTRACT_VERSION = "MKT_BLD_PAID_CONTRACT_V1"
SECTOR = "BUILDING"

# frozen 36 target (순서 고정)
TARGET_FIELDS = [
    "address", "total_floor_area", "floor_count", "basement_count", "building_use_type",
    "built_year", "main_structure", "worker_count", "electric_capacity", "elevator_count",
    "has_safety_manager",
    "has_sprinkler", "has_fire_hydrant", "has_emergency_broadcast", "has_emergency_gen",
    "has_gas", "has_chemical",
    "work_height_m", "has_truck_loading_unloading", "truck_loading_height_m",
    "has_manual_heavy_handling", "manual_handling_weight_kg",
    "gas_capacity_kg", "gas_capacity_m3", "has_boiler", "boiler_capacity_kw",
    "transformer_capacity_kva", "annual_energy_toe",
    "has_hazmat_storage", "has_water_tank", "water_tank_ton",
    "is_multi_use", "multi_use_type", "is_energy_intensive", "has_smoke_control", "building_grade",
]

# DIRECT: target명 == factories 컬럼명 (source NULL→NULL, false/0/[] 보존)
DIRECT_MAP = {
    "floor_count": "floor_count",
    "elevator_count": "elevator_count",
    "has_safety_manager": "has_safety_manager",
    "has_sprinkler": "has_sprinkler",
    "has_fire_hydrant": "has_fire_hydrant",
    "has_emergency_broadcast": "has_emergency_broadcast",
    "has_emergency_gen": "has_emergency_gen",
    "has_gas": "has_gas",
    "work_height_m": "work_height_m",
    "has_truck_loading_unloading": "has_truck_loading_unloading",
    "truck_loading_height_m": "truck_loading_height_m",
    "has_manual_heavy_handling": "has_manual_heavy_handling",
    "manual_handling_weight_kg": "manual_handling_weight_kg",
    "gas_capacity_kg": "gas_capacity_kg",
    "gas_capacity_m3": "gas_capacity_m3",
    "has_boiler": "has_boiler",
    "boiler_capacity_kw": "boiler_capacity_kw",
    "transformer_capacity_kva": "transformer_capacity_kva",
    "annual_energy_toe": "annual_energy_toe",
    "has_hazmat_storage": "has_hazmat_storage",
    "has_water_tank": "has_water_tank",
    "water_tank_ton": "water_tank_ton",
    "has_smoke_control": "has_smoke_control",
}

# TRANSFORM(rename): target명 != factories 컬럼명 (값 보정 없이 이름만 상이)
TRANSFORM_MAP = {
    "total_floor_area": "building_area",
    "basement_count": "underground_floor_count",
    "built_year": "completion_year",
    "worker_count": "employee_count",
    "electric_capacity": "electrical_capacity_kw",
    "has_chemical": "has_chemical_substance",
}

# E5 — DB 값 유무와 무관하게 항상 NULL + UNRESOLVED (source 표기용 사유)
E5_UNRESOLVED = {
    "building_use_type": "factories.building_use_code(exact Marketing mapping 미확정)",
    "main_structure": "factories.building_structure_code/name(exact Marketing mapping 미확정)",
    "is_multi_use": "factories.is_multi_use(다중이용업소≠다중이용시설 semantic identity 미확정)",
    "is_energy_intensive": "미확정(에너지다소비 법적 분류; threshold 조사 금지)",
    "building_grade": "factories.building_grade(Marketing semantic/accepted domain 미확정)",
}


def _rows(res) -> List[dict]:
    return list(getattr(res, "data", None) or [])


def _nonblank(v: Any):
    """문자열이고 strip 후 비어있지 않으면 strip된 값, 아니면 None."""
    if isinstance(v, str):
        s = v.strip()
        return s if s else None
    return None


def assemble_building_marketing_contract(supabase, factory_id: str) -> Dict[str, Any]:
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

    # ── factories (single row) — DB READ EXACT 1 ──
    fac_res = supabase.table("factories").select("*").eq("id", factory_id).limit(1).execute()
    fac_rows = _rows(fac_res)
    fac = fac_rows[0] if fac_rows else {}

    # DIRECT (target==column)
    for field, col in DIRECT_MAP.items():
        _resolve(field, fac.get(col), "DIRECT", f"factories.{col}")  # None/false/0 보존

    # TRANSFORM (rename)
    for field, col in TRANSFORM_MAP.items():
        _resolve(field, fac.get(col), "TRANSFORM", f"factories.{col}")  # None/false/0 보존

    # address — 고정 B transform (road→jibun fallback + detail 결합; site_address/sido/sigungu/dong 미사용)
    base = _nonblank(fac.get("address_road")) or _nonblank(fac.get("address_jibun"))
    if base is None:
        _resolve("address", None, "TRANSFORM", "factories.address_road/address_jibun/address_detail")
    else:
        detail = _nonblank(fac.get("address_detail"))
        addr = f"{base} {detail}" if detail else base
        _resolve("address", addr, "TRANSFORM", "factories.address_road/address_jibun/address_detail")

    # multi_use_type — structural only(list·StrictStr·nonblank), vocabulary 검증 0
    mut = fac.get("multi_use_type")
    if mut is None:
        _resolve("multi_use_type", None, "DIRECT", "factories.multi_use_type")
    elif isinstance(mut, list) and all(isinstance(x, str) and x.strip() != "" for x in mut):
        _resolve("multi_use_type", mut, "DIRECT", "factories.multi_use_type")  # [] 포함 보존
    else:
        _unresolved("multi_use_type", "factories.multi_use_type(구조 오류: list/StrictStr/nonblank 위반)")

    # E5 — 항상 NULL + UNRESOLVED (DB 값 유무 무관)
    for field, src in E5_UNRESOLVED.items():
        _unresolved(field, src)

    # 36 정합성(안전망)
    for f in TARGET_FIELDS:
        if f not in values:
            _unresolved(f, "MISSING")

    return {
        "contract_version": CONTRACT_VERSION,
        "sector": SECTOR,
        "factory_id": factory_id,
        "values": {f: values[f] for f in TARGET_FIELDS},  # 정확히 36, 순서 고정
        "unresolved_fields": sorted(unresolved),
        "provenance": provenance,
    }
