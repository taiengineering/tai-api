from typing import Any, Dict, List

from services.legal_context import _truthy


CONSTRUCTION_RELEVANT_LAW_PREFIXES = [
    "산업안전보건",
    "중대재해",
    "건설산업",
    "건설기술",
    "근로기준",
    "산업재해보상",
    "전기안전",
]


CONDITION_CODE_TO_CONTEXT_KEY_V510: Dict[str, str] = {
    "employee_count": "worker_count",
    "building_area": "total_floor_area",
    "electrical_capacity_kw": "electric_capacity",
    "floor_count": "floor_count",
    "elevator_count": "elevator_count",
    "boiler_capacity_kw": "boiler_capacity_kw",
    "boiler_capacity_th": "boiler_capacity_th",
    "gas_capacity_kg": "gas_capacity_kg",
    "gas_capacity_m3": "gas_capacity_m3",
    "transformer_capacity_kva": "transformer_capacity_kva",
    "annual_energy_toe": "annual_energy_toe",
    "construction_amount": "construction_amount",
    "contract_amount": "construction_amount",
    "contractor_count": "contractor_count",
    "is_hazardous_material": "is_hazardous_material",
    "is_multi_use": "is_multi_use",
    "is_factory_registered": "is_factory_registered",
    "electric_capacity": "electric_capacity",
    "worker_count": "worker_count",
}


def _input_to_facility_context_v510(sector: str, inp: Dict[str, Any]) -> Dict[str, Any]:
    sec = sector.strip().upper()
    # 입력표준(INDUSTRIAL) → 엔진/룰표준(MANUFACTURING) 경계 변환.
    if sec == "INDUSTRIAL":
        sec = "MANUFACTURING"
    ctx: Dict[str, Any] = {
        "worker_count": 0,
        "total_floor_area": 0.0,
        "electric_capacity": 0.0,
        "building_use_code": "",
        "ksic_code": "",
        "floor_count": 0,
        "construction_amount": 0.0,
        "contract_amount": 0.0,
        "is_hazardous_material": 0,
        "is_multi_use": 0,
        "is_factory_registered": 0,
        "has_high_pressure_gas": 0,
        "has_hazardous_material": 0,
        "has_chemical_substance": 0,
        "has_boiler": 0,
        "has_tunnel_bridge": 0,
        "hospital_beds": 0,
        "student_count": 0,
    }
    if sec == "BUILDING":
        ctx["building_use_code"] = str(inp.get("building_use") or inp.get("building_use_type") or inp.get("building_use_code") or "")
        ctx["total_floor_area"] = float(inp.get("total_floor_area") or inp.get("floor_area") or 0)
        ctx["floor_count"] = int(inp.get("floor_count") or 0)
        ctx["worker_count"] = int(inp.get("worker_count") or inp.get("employee_count") or 0)
        ctx["electric_capacity"] = float(inp.get("electric_capacity") or 0)
        ctx["has_high_pressure_gas"] = 1 if _truthy(inp.get("has_high_pressure_gas")) else 0
        ctx["has_hazardous_material"] = 1 if _truthy(inp.get("has_hazardous_material")) else 0
        ctx["is_hazardous_material"] = ctx["has_hazardous_material"]
    elif sec == "MANUFACTURING":
        ctx["ksic_code"] = str(inp.get("ksic_major") or inp.get("ksic_code") or "")
        ctx["worker_count"] = int(inp.get("worker_count") or inp.get("employee_count") or 0)
        ctx["electric_capacity"] = float(inp.get("electric_capacity") or 0)
        ctx["has_hazardous_material"] = 1 if _truthy(inp.get("has_hazardous_material")) else 0
        ctx["is_hazardous_material"] = ctx["has_hazardous_material"]
        ctx["has_high_pressure_gas"] = 1 if _truthy(inp.get("has_high_pressure_gas")) else 0
        ctx["has_chemical_substance"] = 1 if _truthy(inp.get("has_chemical_substance")) else 0
        ctx["has_boiler"] = 1 if _truthy(inp.get("has_boiler")) else 0
    elif sec == "CONSTRUCTION":
        eok = float(inp.get("contract_amount_eok") or 0)
        amount = eok * 100_000_000.0
        ctx["construction_amount"] = amount
        ctx["contract_amount"] = amount

        site_type = str(inp.get("construction_type") or inp.get("site_type") or "BUILDING")
        ctx["construction_type"] = site_type
        ctx["building_use_code"] = site_type
        ctx["is_building"] = 1 if site_type == "BUILDING" else 0
        ctx["is_civil"] = 1 if site_type == "CIVIL" else 0

        direct = int(inp.get("direct_workers") or inp.get("worker_count") or inp.get("employee_count") or 0)
        subcon = int(inp.get("subcon_workers") or 0)
        total = direct + subcon
        ctx["worker_count"] = total
        ctx["employee_count"] = total
        ctx["direct_workers"] = direct
        ctx["subcon_workers"] = subcon
        ctx["has_tunnel_bridge"] = 1 if _truthy(inp.get("has_tunnel_bridge")) else 0

        threshold = 15_000_000_000 if site_type in ("BUILDING", "SPECIALTY") else 12_000_000_000
        ctx["safety_manager_threshold"] = threshold
    elif sec in ("SPECIAL_FACILITY", "SPECIAL"):
        ctx["building_use_code"] = str(inp.get("facility_type") or "")
        ctx["total_floor_area"] = float(inp.get("total_floor_area") or inp.get("floor_area") or 0)
        ctx["hospital_beds"] = int(inp.get("hospital_beds") or 0)
        ctx["student_count"] = int(inp.get("student_count") or 0)
        ctx["worker_count"] = int(inp.get("worker_count") or inp.get("employee_count") or 0)
    return ctx


def _db_rule_matches_facility_v510(rule: Dict[str, Any], context: Dict[str, Any]) -> bool:
    cc = rule.get("condition_code")
    cv = rule.get("condition_value")
    if not cc or cv is None:
        return False
    ctx_key = CONDITION_CODE_TO_CONTEXT_KEY_V510.get(cc, cc)
    actual = context.get(ctx_key)
    if actual is None:
        actual = context.get(cc)
    if actual is None:
        return False
    try:
        actual_num = float(actual)
        value_num = float(cv)
    except (TypeError, ValueError):
        op = (rule.get("condition_operator_code") or "eq").lower()
        return str(actual) == str(cv) and op in ("eq", "=", "==")
    op = (rule.get("condition_operator_code") or "gte").lower()
    if op in ("gte", ">="):
        return actual_num >= value_num
    if op in ("lte", "<="):
        return actual_num <= value_num
    if op in ("gt", ">"):
        return actual_num > value_num
    if op in ("lt", "<"):
        return actual_num < value_num
    if op in ("eq", "=", "=="):
        return actual_num == value_num
    return actual_num >= value_num


def _evaluate_facility_conditions_db_v510(
    facility_ctx: Dict[str, Any], rules: List[Dict[str, Any]], sector: str
) -> tuple:
    applicable: List[Dict[str, Any]] = []
    not_applicable: List[Dict[str, Any]] = []

    for rule in rules:
        cc = rule.get("condition_code")
        cv = rule.get("condition_value")
        if not cc or cv is None:
            if sector == "CONSTRUCTION":
                law = rule.get("law_name") or ""
                if any(prefix in law for prefix in CONSTRUCTION_RELEVANT_LAW_PREFIXES):
                    applicable.append(rule)
                else:
                    not_applicable.append(rule)
            else:
                applicable.append(rule)
        elif _db_rule_matches_facility_v510(rule, facility_ctx):
            applicable.append(rule)
        else:
            not_applicable.append(rule)

    return applicable, not_applicable


def _get_construction_summary(facility_ctx: Dict[str, Any]) -> Dict[str, Any]:
    amount = float(facility_ctx.get("construction_amount") or 0)
    workers = int(facility_ctx.get("worker_count") or 0)
    site_type = str(facility_ctx.get("construction_type") or facility_ctx.get("building_use_code") or "BUILDING")

    threshold = 15_000_000_000 if site_type in ("BUILDING", "SPECIALTY") else 12_000_000_000
    sm_required = (amount >= threshold) or (workers >= 50)

    site_label = "건축" if site_type == "BUILDING" else ("토목" if site_type == "CIVIL" else "전문")
    basis_parts = [f"{site_label} {int(threshold/100_000_000)}억원 {'이상' if amount >= threshold else '미만'}"]
    if workers >= 50:
        basis_parts.append("근로자 50명 이상")

    return {
        "site_type": site_type,
        "contract_amount": amount,
        "contract_amount_eok": round(amount / 100_000_000, 2) if amount else 0,
        "total_workers": workers,
        "direct_workers": int(facility_ctx.get("direct_workers") or 0),
        "subcon_workers": int(facility_ctx.get("subcon_workers") or 0),
        "safety_manager_required": sm_required,
        "safety_manager_basis": ", ".join(basis_parts),
        "key_thresholds_met": {
            "1억_산업안전보건관리비": amount >= 100_000_000,
            "50억_유해위험방지계획서": amount >= 5_000_000_000,
            "50억_기초안전보건교육": amount >= 5_000_000_000,
            "100억_안전관리계획서": amount >= 10_000_000_000,
            "120억_안전관리자선임_토목": site_type == "CIVIL" and amount >= 12_000_000_000,
            "150억_안전관리자선임_건축": site_type == "BUILDING" and amount >= 15_000_000_000,
            "200억_안전보건관리책임자": amount >= 20_000_000_000,
            "1000억_건설안전판정사": amount >= 100_000_000_000,
        },
    }
