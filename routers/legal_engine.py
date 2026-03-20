# routers/legal_engine.py
# 법령 적용 판정 엔진
# - POST /legal-engine/apply/{factory_id}  법령 적용 판정 실행
# - GET  /legal-engine/result/{factory_id} 판정 결과 조회
# - GET  /legal-engine/summary/{factory_id} 판정 요약

from fastapi import APIRouter, HTTPException
from db.supabase_client import get_supabase
from datetime import datetime
import traceback

router = APIRouter(tags=["legal_engine"])

ENGINE_VERSION = "1.0.0"

# ============================================================
# 조건 비교 헬퍼
# ============================================================

def compare(factory_value, operator: str, rule_value) -> bool:
    """조건 비교 함수 (gte/gt/lte/lt/eq/neq)"""
    if factory_value is None:
        return False
    try:
        fv = float(factory_value)
        rv = float(rule_value)
    except (TypeError, ValueError):
        # 문자열 비교 (eq/neq)
        if operator == "eq":
            return str(factory_value) == str(rule_value)
        if operator == "neq":
            return str(factory_value) != str(rule_value)
        return False

    if operator == "gte": return fv >= rv
    if operator == "gt":  return fv > rv
    if operator == "lte": return fv <= rv
    if operator == "lt":  return fv < rv
    if operator == "eq":  return fv == rv
    if operator == "neq": return fv != rv
    return False


# ============================================================
# 시설 조건값 추출
# ============================================================

def extract_factory_conditions(factory: dict, facility_condition: list) -> dict:
    """
    factory 테이블 + facility_condition 테이블에서
    법령 판단에 필요한 조건값을 추출
    """
    conditions = {}

    # factories 테이블 직접 필드
    field_map = {
        "employee_count":        factory.get("employee_count"),
        "contractor_count":      factory.get("contractor_count"),
        "building_area":         factory.get("building_area"),
        "floor_count":           factory.get("floor_count"),
        "underground_floor_count": factory.get("underground_floor_count"),
        "electrical_capacity_kw":  factory.get("electrical_capacity_kw"),
        "transformer_capacity_kva": factory.get("transformer_capacity_kva"),
        "gas_capacity_kg":         factory.get("gas_capacity_kg"),
        "gas_capacity_m3":         factory.get("gas_capacity_m3"),
        "boiler_capacity_kw":      factory.get("boiler_capacity_kw"),
        "boiler_capacity_th":      factory.get("boiler_capacity_th"),
        "elevator_count":          factory.get("elevator_count"),
        "annual_energy_toe":       factory.get("annual_energy_toe"),
        "construction_amount":     factory.get("construction_amount"),
        "is_factory_registered":   factory.get("is_factory_registered"),
        "is_hazardous_material":   factory.get("is_hazardous_material"),
        "is_multi_use":            factory.get("is_multi_use"),
    }
    conditions.update(field_map)

    # facility_condition 테이블 (추가 조건값)
    for fc in facility_condition:
        code = fc.get("condition_code")
        val  = fc.get("condition_value")
        if code and val is not None:
            conditions[code] = val

    return conditions


# ============================================================
# 핵심 엔진 함수
# ============================================================

def apply_legal_rules(factory_id: str, supabase) -> dict:
    """
    factory_id 기반으로 법령 적용 판정
    Returns: 판정 결과 딕셔너리
    """

    # 1) factory 데이터 로드
    factory_res = supabase.table("factories")\
        .select("*")\
        .eq("id", factory_id)\
        .single()\
        .execute()

    if not factory_res.data:
        raise HTTPException(status_code=404, detail="사업장을 찾을 수 없습니다")

    factory = factory_res.data

    # 2) facility_condition 로드 (추가 조건값)
    fc_res = supabase.table("facility_condition")\
        .select("*")\
        .eq("factory_id", factory_id)\
        .execute()
    facility_condition = fc_res.data or []

    # 3) 조건값 추출
    conditions = extract_factory_conditions(factory, facility_condition)

    # 4) 전체 법령 룰 로드
    rules_res = supabase.table("master_building_legal_rules")\
        .select("*")\
        .eq("is_active", True)\
        .order("priority_no")\
        .execute()
    rules = rules_res.data or []

    # 5) 기존 legal_applications 삭제 (재판정)
    supabase.table("legal_applications")\
        .delete()\
        .eq("factory_id", factory_id)\
        .execute()

    # 6) 각 룰 판정
    results = {
        "factory_id":           factory_id,
        "factory_name":         factory.get("name", ""),
        "evaluated_at":         datetime.now().isoformat(),
        "engine_version":       ENGINE_VERSION,
        "total_rules":          len(rules),
        "applicable_count":     0,
        "appointment_required": [],
        "inspection_required":  [],
        "report_required":      [],
        "penalty_required":     [],
        "not_applicable":       [],
    }

    apply_logs = []

    for rule in rules:
        # 건물용도 필터
        building_use_type_code = rule.get("building_use_type_code")
        if building_use_type_code:
            factory_building_use = factory.get("building_use_type_code")
            if factory_building_use != building_use_type_code:
                continue

        # 업종 필터
        business_type_code = rule.get("business_type_code")
        if business_type_code:
            factory_business = factory.get("business_type_code") or factory.get("industry_type_code")
            if factory_business != business_type_code:
                continue

        # 조건 비교
        condition_code     = rule.get("condition_code")
        condition_operator = rule.get("condition_operator_code")
        condition_value    = rule.get("condition_value")

        factory_value = conditions.get(condition_code)
        is_applicable = compare(factory_value, condition_operator, condition_value)

        # 매칭 조건 기록
        matched_conditions = {
            "condition_code":     condition_code,
            "condition_operator": condition_operator,
            "condition_value":    str(condition_value),
            "factory_value":      str(factory_value),
            "matched":            is_applicable,
        }

        # legal_applications 저장
        log_data = {
            "factory_id":              factory_id,
            "rule_id":                 rule.get("id"),
            "rule_code":               rule.get("rule_id"),
            "law_name":                rule.get("law_name"),
            "law_article":             rule.get("law_article"),
            "rule_type_code":          rule.get("rule_type_code"),
            "is_applicable":           is_applicable,
            "matched_conditions":      matched_conditions,
            "appointment_required":    rule.get("appointment_required", False),
            "appointment_target_code": rule.get("appointment_target_code"),
            "inspection_type_code":    rule.get("inspection_type_code"),
            "inspection_cycle_unit":   rule.get("inspection_cycle_unit_code"),
            "inspection_cycle_value":  rule.get("inspection_cycle_value"),
            "action_required":         rule.get("action_type_code"),
            "evaluated_at":            datetime.now().isoformat(),
            "evaluated_by":            "engine",
            "engine_version":          ENGINE_VERSION,
        }
        apply_logs.append(log_data)

        if not is_applicable:
            results["not_applicable"].append({
                "rule_id":    rule.get("rule_id"),
                "law_name":   rule.get("law_name"),
                "law_article": rule.get("law_article"),
                "reason":     f"{condition_code} = {factory_value} (조건 미충족: {condition_operator} {condition_value})",
            })
            continue

        results["applicable_count"] += 1

        # 선임 필요
        if rule.get("appointment_required"):
            results["appointment_required"].append({
                "rule_id":                      rule.get("rule_id"),
                "law_name":                     rule.get("law_name"),
                "law_article":                  rule.get("law_article"),
                "appointment_target":           rule.get("appointment_target_code"),
                "qualification_type":           rule.get("qualification_type"),
                "qualification_code":           rule.get("appointment_qualification_code"),
                "national_grade_code":          rule.get("national_grade_code"),
                "career_level_code":            rule.get("career_level_code"),
                "qualification_level":          rule.get("appointment_qualification_level_code"),
                "qualification_level_operator": rule.get("appointment_qualification_level_operator_code"),
                "count_value":                  rule.get("appointment_count_value"),
                "count_unit":                   rule.get("appointment_count_unit"),
                "count_operator":               rule.get("appointment_count_operator"),
            })

        # 점검 필요
        if rule.get("inspection_required"):
            results["inspection_required"].append({
                "rule_id":          rule.get("rule_id"),
                "law_name":         rule.get("law_name"),
                "law_article":      rule.get("law_article"),
                "inspection_type":  rule.get("inspection_type_code"),
                "cycle_unit":       rule.get("inspection_cycle_unit_code"),
                "cycle_value":      rule.get("inspection_cycle_value"),
                "actor_code":       rule.get("inspection_actor_code"),
            })

        # 보고 필요
        if rule.get("report_required"):
            results["report_required"].append({
                "rule_id":       rule.get("rule_id"),
                "law_name":      rule.get("law_name"),
                "law_article":   rule.get("law_article"),
                "report_method": rule.get("report_method_code"),
            })

        # 처벌 정보
        if rule.get("penalty_required"):
            results["penalty_required"].append({
                "rule_id":      rule.get("rule_id"),
                "law_name":     rule.get("law_name"),
                "law_article":  rule.get("law_article"),
                "penalty_type": rule.get("penalty_type_code"),
                "penalty_value": rule.get("penalty_value"),
                "penalty_unit": rule.get("penalty_unit_code"),
            })

    # 7) legal_applications 일괄 저장
    if apply_logs:
        supabase.table("legal_applications").insert(apply_logs).execute()

    return results


# ============================================================
# 엔드포인트
# ============================================================

@router.post("/apply/{factory_id}")
def apply_rules(factory_id: str):
    """법령 적용 판정 실행"""
    supabase = get_supabase()
    try:
        result = apply_legal_rules(factory_id, supabase)
        return {
            "status": "success",
            "data":   result,
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/result/{factory_id}")
def get_result(factory_id: str):
    """판정 결과 전체 조회"""
    supabase = get_supabase()
    result = supabase.table("legal_applications")\
        .select("*")\
        .eq("factory_id", factory_id)\
        .eq("is_applicable", True)\
        .order("rule_type_code")\
        .execute()
    return result.data


@router.get("/summary/{factory_id}")
def get_summary(factory_id: str):
    """판정 결과 요약"""
    supabase = get_supabase()

    all_results = supabase.table("legal_applications")\
        .select("*")\
        .eq("factory_id", factory_id)\
        .execute()

    if not all_results.data:
        return {"message": "판정 결과가 없습니다. POST /legal-engine/apply/{factory_id} 먼저 실행하세요."}

    applicable = [r for r in all_results.data if r.get("is_applicable")]

    return {
        "factory_id":            factory_id,
        "evaluated_at":          all_results.data[0].get("evaluated_at"),
        "total_rules_evaluated": len(all_results.data),
        "applicable_count":      len(applicable),
        "appointment_required":  [r for r in applicable if r.get("appointment_required")],
        "inspection_required":   [r for r in applicable if r.get("inspection_type_code")],
        "report_required":       [r for r in applicable if r.get("rule_type_code") == "003"],
        "penalty_required":      [r for r in applicable if r.get("rule_type_code") == "006"],
    }


@router.get("/test")
def test():
    return {"message": "legal engine alive", "version": ENGINE_VERSION}
