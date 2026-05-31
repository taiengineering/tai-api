"""
verification/reverse_input_generator.py
Rule → 통과 입력 생성. 추론 없음. Rule 데이터만 사용.
"""
from __future__ import annotations
from typing import Any, Dict, Optional

OPERATOR_MAP = {
    ">=": lambda v: float(v) + 1 if float(v) == int(float(v)) else float(v) + 0.1,
    ">":  lambda v: float(v) + 1,
    "<=": lambda v: float(v) - 1 if float(v) > 0 else 0,
    "<":  lambda v: float(v) - 1 if float(v) > 0 else 0,
    "=":  lambda v: float(v),
    "==": lambda v: float(v),
}

BOOLEAN_CODES = {
    "is_hazardous_material", "has_high_pressure_gas", "has_chemical_substance",
    "is_factory_registered", "is_multi_use", "has_boiler", "has_pressure_chamber",
    "is_construction_site", "manufacturing_business", "power_plant_monitoring",
    "is_mechanical_inspector_business", "has_noise_facility", "has_boiler",
}

SECTOR_BASE = {
    "BUILDING":      {"sector": "BUILDING", "employee_count": 10, "building_area": 500},
    "MANUFACTURING": {"sector": "MANUFACTURING", "employee_count": 10, "building_area": 500, "is_factory_registered": 1},
    "CONSTRUCTION":  {"sector": "CONSTRUCTION", "employee_count": 10, "contract_amount": 5000000000},
    "COMMON":        {"sector": "BUILDING", "employee_count": 10, "building_area": 500},
}

ALIAS_TO_INPUT = {
    "building_area": "floor_area",
    "electrical_capacity_kw": "electric_capacity",
    "electric_capacity": "electric_capacity",
    "contract_amount": "contract_amount_eok",
}

def _parse_value(raw) -> Optional[float]:
    try: return float(str(raw).strip())
    except: return None

def generate_input(rule: dict) -> dict:
    sector = (rule.get("sector") or "COMMON").upper()
    base = dict(SECTOR_BASE.get(sector, SECTOR_BASE["COMMON"]))
    base["sector"] = sector if sector != "COMMON" else "BUILDING"

    ccode = (rule.get("condition_code") or "").strip()
    cval  = rule.get("condition_value")
    cop   = (rule.get("condition_operator_code") or ">=").strip()

    if not ccode:
        return {"input_payload": base, "expected_rule_id": rule.get("rule_id",""), "generated": False, "reason": "no_condition"}

    # boolean flag
    if ccode in BOOLEAN_CODES:
        field = ALIAS_TO_INPUT.get(ccode, ccode)
        base[field] = 1
        return {"input_payload": base, "expected_rule_id": rule.get("rule_id",""), "generated": True, "reason": "boolean"}

    # numeric
    val = _parse_value(cval)
    if val is None:
        return {"input_payload": base, "expected_rule_id": rule.get("rule_id",""), "generated": False, "reason": f"unparseable_value:{cval}"}

    fn = OPERATOR_MAP.get(cop)
    if fn is None:
        return {"input_payload": base, "expected_rule_id": rule.get("rule_id",""), "generated": False, "reason": f"unknown_op:{cop}"}

    target = fn(val)
    field = ALIAS_TO_INPUT.get(ccode, ccode)
    base[field] = max(0, target)

    # special unit conversion
    if ccode == "contract_amount":
        base["contract_amount_eok"] = max(0, target / 100_000_000)
        base.pop("contract_amount", None)

    return {"input_payload": base, "expected_rule_id": rule.get("rule_id",""), "generated": True, "reason": "numeric"}
