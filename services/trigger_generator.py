"""Trigger Code Set 생성기 (CURSOR-TASK-001).

factory_id → factories + equipment_assets 조회 → Trigger Code Set 반환.

원칙:
  - 항상 BUSINESS:REGISTERED 포함
  - factories.has_* == True 인 필드만 WORK:* 코드 생성
  - equipment_assets.equipment_type_code 별 EQUIPMENT:* / EQUIPMENT_ACT:* 생성
  - DB 쓰기 없음. 기존 obligation_adapter 경로 무수정.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

# factories boolean → WORK trigger
WORK_FIELD_MAP: Dict[str, str] = {
    "has_confined_space": "WORK:CONFINED_SPACE",
    "has_tower_crane": "WORK:TOWER_CRANE",
    "has_asbestos_demo": "WORK:ASBESTOS",
    "has_blasting": "WORK:BLASTING",
    "has_diving": "WORK:DIVING",
    "has_excavation_work": "WORK:EXCAVATION",
    "has_high_place_work": "WORK:HIGH_PLACE",
    "has_lifting_work": "WORK:LIFTING",
    "has_demolition_work": "WORK:DEMOLITION",
    "has_scaffold_work": "WORK:SCAFFOLD",
    "has_formwork_work": "WORK:FORMWORK",
    "has_welding_work": "WORK:WELDING",
    "has_electrical_work": "WORK:ELECTRICAL",
    "has_hot_work": "WORK:HOT_WORK",
    "has_boiler": "WORK:BOILER",
    "has_high_pressure_gas": "WORK:HIGH_PRESSURE_GAS",
    "has_chemical_substance": "WORK:CHEMICAL_SUBSTANCE",
    "has_safety_manager": "WORK:SAFETY_MANAGER",
    "is_hazardous_material": "WORK:HAZARDOUS_MATERIAL",
    "hazardous_material": "WORK:HAZARDOUS_MATERIAL",
}


# (predicate(factory_row) → code) — 수치 임계
def _threshold_codes(row: Dict[str, Any]) -> List[str]:
    codes: List[str] = []
    emp = row.get("employee_count")
    if emp is not None:
        try:
            if int(emp) >= 50:
                codes.append("THRESHOLD:EMPLOYEE_50_PLUS")
            if int(emp) >= 100:
                codes.append("THRESHOLD:EMPLOYEE_100_PLUS")
        except (TypeError, ValueError):
            pass
    return codes


# equipment_type_code → canonical token
EQUIPMENT_CODE_CANON: Dict[str, str] = {
    "001": "TRANSFORMER",
    "010": "GENERATOR",
    "014": "BOILER",
    "019": "REFRIGERATION",
    "021": "CRANE",
    "023": "PRESS",
    "025": "ELEVATOR",
    "027": "HIGH_PRESSURE_GAS",
    "028": "LPG_STORAGE",
    "029": "HAZARDOUS_MATERIAL_FACILITY",
    "030": "HAZARDOUS_STORAGE",
    "031": "SPRINKLER",
    "CONVEYOR": "CONVEYOR",
    "CRANE": "CRANE",
    "PRESS": "PRESS",
    "PRESSURE_VESSEL": "PRESSURE_VESSEL",
}

BASE_TRIGGER = "BUSINESS:REGISTERED"


def _canon_equipment_code(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    key = str(raw).strip().upper()
    if not key:
        return None
    return EQUIPMENT_CODE_CANON.get(key, key)


def _work_codes_from_factory(row: Dict[str, Any]) -> List[str]:
    codes: List[str] = []
    for field, code in WORK_FIELD_MAP.items():
        if row.get(field) is True:
            codes.append(code)
    return codes


def _equipment_codes_from_assets(assets: List[Dict[str, Any]]) -> List[str]:
    codes: List[str] = []
    seen: Set[str] = set()
    for asset in assets:
        if asset.get("is_operating") is False:
            continue
        canon = _canon_equipment_code(asset.get("equipment_type_code"))
        if not canon or canon in seen:
            continue
        seen.add(canon)
        codes.append(f"EQUIPMENT:{canon}")
        codes.append(f"EQUIPMENT_ACT:{canon}_USE")
    return codes


def _fetch_factory(supabase, factory_id: str) -> Dict[str, Any]:
    res = (
        supabase.table("factories")
        .select("*")
        .eq("id", factory_id)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    if not rows:
        raise ValueError(f"factory not found: {factory_id}")
    return rows[0]


def _fetch_equipment_assets(supabase, factory_id: str) -> List[Dict[str, Any]]:
    res = (
        supabase.table("equipment_assets")
        .select("id, equipment_type_code, is_operating, operation_status")
        .eq("factory_id", factory_id)
        .execute()
    )
    assets: List[Dict[str, Any]] = []
    for row in res.data or []:
        if row.get("operation_status") == "INACTIVE":
            continue
        assets.append(row)
    return assets


def generate_trigger_codes(factory_id: str, supabase) -> List[str]:
    """factory_id → 정렬된 Trigger Code Set."""
    factory = _fetch_factory(supabase, factory_id)
    assets = _fetch_equipment_assets(supabase, factory_id)

    codes: List[str] = [BASE_TRIGGER]
    codes.extend(_threshold_codes(factory))
    codes.extend(_work_codes_from_factory(factory))
    codes.extend(_equipment_codes_from_assets(assets))

    # stable unique order
    out: List[str] = []
    seen: Set[str] = set()
    for c in codes:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def generate_trigger_codes_from_row(
    factory_row: Dict[str, Any],
    equipment_rows: Optional[List[Dict[str, Any]]] = None,
) -> List[str]:
    """테스트/오프라인용: DB 없이 row dict만으로 Trigger Code Set 생성."""
    codes: List[str] = [BASE_TRIGGER]
    codes.extend(_threshold_codes(factory_row))
    codes.extend(_work_codes_from_factory(factory_row))
    codes.extend(_equipment_codes_from_assets(equipment_rows or []))
    out: List[str] = []
    seen: Set[str] = set()
    for c in codes:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out
