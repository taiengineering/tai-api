from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List

from services.legal_helpers import _to_float, get_construction_amount_threshold

CONSTRUCTION_RELEVANT_LAW_PREFIXES = [
    "산업안전보건",
    "중대재해",
    "건설산업",
    "건설기술",
    "근로기준",
    "산업재해보상",
    "전기안전",
]

CONDITION_CODE_TO_CONTEXT_KEY: Dict[str, str] = {
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


def normalize_sector_db(sector: str) -> str:
    if not sector:
        return ""
    u = sector.strip().upper()
    if u == "INDUSTRY":
        return "INDUSTRIAL"
    if u == "SPECIAL":
        return "SPECIAL_FACILITY"
    return u


def risk_level(applicable_count: int, appointment_n: int) -> str:
    if applicable_count >= 12 or appointment_n >= 4:
        return "HIGH"
    if applicable_count >= 5 or appointment_n >= 1:
        return "MEDIUM"
    return "LOW"


def _risk_level(applicable_count: int, appointment_n: int) -> str:
    return risk_level(applicable_count, appointment_n)


def _check_rule_conditions(rule: dict, context: dict) -> bool:
    cc = rule.get("condition_code", "")
    operator = rule.get("condition_operator_code", "gte")
    value_str = rule.get("condition_value")
    if not cc:
        return True
    actual = context.get(cc)
    if actual is None:
        return False
    if cc.startswith("is_") and actual == 0:
        return False
    if value_str is None:
        try:
            return float(actual) > 0
        except (TypeError, ValueError):
            return bool(actual)
    try:
        an, vn = float(actual), float(value_str)
        if operator in ("gte", ">="):
            return an >= vn
        if operator in ("lte", "<="):
            return an <= vn
        if operator in ("gt", ">"):
            return an > vn
        if operator in ("lt", "<"):
            return an < vn
        if operator in ("eq", "=", "=="):
            return an == vn
        if operator in ("neq", "!=", "<>"):
            return an != vn
        return an >= vn
    except (TypeError, ValueError):
        if operator in ("eq", "=", "=="):
            return str(actual).strip() == str(value_str).strip()
        if operator in ("in", "contains"):
            return str(value_str) in str(actual)
        return False


def _resolve_obligation_type(rule: dict) -> str:
    ot = (rule.get("obligation_type") or "").strip().upper()
    if ot:
        return ot
    if rule.get("appointment_required"):
        return "APPOINT"
    if rule.get("notify_required"):
        return "NOTIFY"
    if rule.get("report_required"):
        return "REPORT"
    if rule.get("inspection_required"):
        return "INSPECT"
    if rule.get("action_required"):
        return "ACTION"
    return "OTHER"


def _is_notify(rule: dict) -> bool:
    return (rule.get("obligation_type") or "").strip().upper() == "NOTIFY" or bool(rule.get("notify_required"))


def _is_report(rule: dict) -> bool:
    ot = (rule.get("obligation_type") or "").strip().upper()
    if ot == "REPORT":
        return True
    return bool(rule.get("report_required")) and not _is_notify(rule)


def _numeric_compare(actual: float, operator: str, value: float) -> bool:
    op = (operator or "gte").lower()
    try:
        if op in ("gte", ">="):
            return actual >= value
        if op in ("lte", "<="):
            return actual <= value
        if op in ("gt", ">"):
            return actual > value
        if op in ("lt", "<"):
            return actual < value
        if op in ("eq", "=", "=="):
            return actual == value
    except (TypeError, ValueError):
        return False
    return False


def _db_rule_matches_facility(rule: Dict[str, Any], context: Dict[str, Any]) -> bool:
    cc = rule.get("condition_code")
    cv = rule.get("condition_value")
    if not cc or cv is None:
        return False
    ctx_key = CONDITION_CODE_TO_CONTEXT_KEY.get(cc, cc)
    actual = context.get(ctx_key)
    if actual is None:
        actual = context.get(cc)
    if actual is None:
        return False
    try:
        an, vn = float(actual), float(cv)
    except (TypeError, ValueError):
        return str(actual) == str(cv) and (rule.get("condition_operator_code") or "eq").lower() in ("eq", "=", "==")
    return _numeric_compare(an, rule.get("condition_operator_code") or "gte", vn)


def evaluate_facility_conditions_db(facility_ctx: Dict[str, Any], rules: List[Dict[str, Any]], sector: str = "") -> tuple:
    applicable: List[Dict[str, Any]] = []
    not_applicable: List[Dict[str, Any]] = []
    for rule in rules:
        rule_sector = (rule.get("sector") or "").upper()
        cc = rule.get("condition_code")
        cv = rule.get("condition_value")
        if not cc or cv is None:
            if rule_sector in ("COMMON", "CONSTRUCTION_MANUFACTURING", "BUILDING_CONSTRUCTION", "BUILDING_MANUFACTURING"):
                applicable.append(rule)
            elif sector == "CONSTRUCTION":
                law = rule.get("law_name") or ""
                ot = (rule.get("obligation_type") or "").upper()
                article = rule.get("law_article") or ""
                if ot in ("APPOINT", "NOTIFY") and "산업안전보건법" in law and "16조" in article:
                    if float(facility_ctx.get("worker_count") or 0) >= 50:
                        applicable.append(rule)
                    else:
                        not_applicable.append(rule)
                elif any(prefix in law for prefix in CONSTRUCTION_RELEVANT_LAW_PREFIXES):
                    applicable.append(rule)
                else:
                    not_applicable.append(rule)
            else:
                applicable.append(rule)
        elif _db_rule_matches_facility(rule, facility_ctx):
            applicable.append(rule)
        else:
            not_applicable.append(rule)
    return applicable, not_applicable


def get_construction_summary(facility_ctx: Dict[str, Any]) -> Dict[str, Any]:
    amount = float(facility_ctx.get("construction_amount") or 0)
    workers = int(facility_ctx.get("worker_count") or 0)
    site_type = str(facility_ctx.get("construction_type") or facility_ctx.get("building_use_code") or "건축")
    subcon = int(facility_ctx.get("subcon_workers") or facility_ctx.get("subcontractor_worker_count") or 0)
    direct = int(facility_ctx.get("direct_workers") or (workers - subcon))
    threshold = get_construction_amount_threshold({"construction_type": site_type})
    sm_required = (amount >= threshold) or (workers >= 50)
    site_label = {"건축": "건축", "토목": "토목", "공통": "공통", "기타": "기타", "BUILDING": "건축", "CIVIL": "토목", "SPECIALTY": "공통"}.get(site_type, site_type)
    threshold_eok = int(threshold / 100_000_000)
    basis_parts = [f"{site_label} {threshold_eok}억원 {'이상' if amount >= threshold else '미만'}"]
    if workers >= 50:
        basis_parts.append(f"근로자(하도급 포함) {workers}명 >= 50명")
    return {
        "site_type": site_type,
        "contract_amount": amount,
        "contract_amount_eok": round(amount / 100_000_000, 2) if amount else 0,
        "total_workers": workers,
        "direct_workers": direct,
        "subcon_workers": subcon,
        "safety_manager_required": sm_required,
        "safety_manager_basis": ", ".join(basis_parts),
        "threshold_used": threshold,
        "key_thresholds_met": {
            "1억_산업안전보건관리비": amount >= 100_000_000,
            "50억_유해위험방지계획서": amount >= 5_000_000_000,
            "50억_기초안전보건교육": amount >= 5_000_000_000,
            "100억_안전관리계획서": amount >= 10_000_000_000,
            "120억_안전관리자선임_토목": site_type in ("토목", "CIVIL") and amount >= 12_000_000_000,
            "150억_안전관리자선임_건축": site_type in ("건축", "BUILDING") and amount >= 15_000_000_000,
            "200억_안전보건관리책임자": amount >= 20_000_000_000,
            "1000억_건설안전판정사": amount >= 100_000_000_000,
            "50명이상_안전관리자선임": workers >= 50,
            "300명이상_안전관리자선임": workers >= 300,
        },
    }


def _evaluate_condition(rule: dict, input_data: dict) -> bool:
    def check(field, operator, value, data):
        if not field or field not in data:
            return True
        actual = data[field]
        if actual is None:
            return False
        try:
            if operator == ">=":
                return float(actual) >= float(value)
            if operator == "<=":
                return float(actual) <= float(value)
            if operator == ">":
                return float(actual) > float(value)
            if operator == "<":
                return float(actual) < float(value)
            if operator == "==":
                return str(actual) == str(value)
            if operator == "IN":
                return str(actual) in [v.strip() for v in str(value).split(",")]
            if operator == "NOT_IN":
                return str(actual) not in [v.strip() for v in str(value).split(",")]
            if operator == "==true":
                return actual is True or str(actual).lower() == "true"
            if operator == "==false":
                return actual is False or str(actual).lower() == "false"
        except Exception:
            return False
        return True

    c1_ok = check(rule.get("condition_1_field"), rule.get("condition_1_operator"), rule.get("condition_1_value"), input_data)
    if not c1_ok:
        return False
    c2_field = rule.get("condition_2_field")
    if c2_field:
        c2_ok = check(c2_field, rule.get("condition_2_operator"), rule.get("condition_2_value"), input_data)
        mode = rule.get("condition_mode", "AND")
        if mode == "AND" and not c2_ok:
            return False
        if mode == "OR" and not (c1_ok or c2_ok):
            return False
    return True


def _determine_risk_level(rule_count: int) -> str:
    if rule_count >= 10:
        return "HIGH"
    if rule_count >= 5:
        return "MEDIUM"
    return "LOW"


def _evaluate_conditions(context: dict, rules: list) -> tuple:
    applicable, not_applicable = [], []
    for rule in rules:
        (applicable if _check_rule_conditions(rule, context) else not_applicable).append(rule)
    return applicable, not_applicable


def finalize_step1_storage(supabase, diag: Dict[str, Any]):
    result_data = diag["result_data"]
    factory_id = diag["factory_id"]
    sector_raw = diag["sector_raw"]
    inp = diag["inp"]
    applicable = diag["applicable"]
    fac_company_id = diag["fac_company_id"]
    diagnosis_id = None
    if factory_id:
        try:
            supabase.table("factory_diagnosis_results").update({"is_latest": False}).eq("factory_id", factory_id).eq("sector", sector_raw).eq("is_latest", True).execute()
        except Exception:
            pass
        try:
            save_res = (
                supabase.table("factory_diagnosis_results")
                .insert(
                    {
                        "factory_id": factory_id,
                        "sector": sector_raw,
                        "diagnosis_stage": 1,
                        "input_data": inp,
                        "result_data": result_data,
                        "rule_count": result_data.get("applicable_count", len(applicable)),
                        "is_latest": True,
                    }
                )
                .execute()
            )
            if save_res.data:
                diagnosis_id = save_res.data[0].get("id")
        except Exception as e:
            print(f"[DIAGNOSE STEP1] factory_diagnosis_results 저장 실패: {e}")
        if diagnosis_id and applicable:
            try:
                rule_rows = [
                    {
                        "diagnosis_id": diagnosis_id,
                        "rule_code": r.get("rule_id") or r.get("rule_code") or "",
                        "rule_name": (r.get("remarks") or r.get("obligation_summary") or "").strip(),
                        "law_name": r.get("law_name") or "",
                        "law_article": r.get("law_article") or "",
                        "obligation": (r.get("remarks") or r.get("obligation_summary") or "").strip(),
                        "obligation_type": r.get("obligation_type") or "",
                        "due_date": None,
                        "status": "PENDING",
                        "form_code": r.get("form_code") or None,
                    }
                    for r in applicable
                ]
                for i in range(0, len(rule_rows), 50):
                    supabase.table("diagnosis_rule_results").insert(rule_rows[i : i + 50]).execute()
            except Exception as e:
                print(f"[DIAGNOSE STEP1] diagnosis_rule_results 저장 실패: {e}")
    result_data["diagnosis_id"] = diagnosis_id
    return {"result_data": result_data, "factory_id": factory_id, "sector_raw": sector_raw, "diagnosis_id": diagnosis_id, "fac_company_id": fac_company_id, "applicable": applicable}
