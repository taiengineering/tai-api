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

ENGINE_VERSION = "1.1.0"

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

    field_map = {
        "employee_count":           factory.get("employee_count"),
        "contractor_count":         factory.get("contractor_count"),
        "building_area":            factory.get("building_area"),
        "floor_count":              factory.get("floor_count"),
        "underground_floor_count":  factory.get("underground_floor_count"),
        "electrical_capacity_kw":   factory.get("electrical_capacity_kw"),
        "transformer_capacity_kva": factory.get("transformer_capacity_kva"),
        "gas_capacity_kg":          factory.get("gas_capacity_kg"),
        "gas_capacity_m3":          factory.get("gas_capacity_m3"),
        "boiler_capacity_kw":       factory.get("boiler_capacity_kw"),
        "boiler_capacity_th":       factory.get("boiler_capacity_th"),
        "elevator_count":           factory.get("elevator_count"),
        "annual_energy_toe":        factory.get("annual_energy_toe"),
        "construction_amount":      factory.get("construction_amount"),
        "is_factory_registered":    factory.get("is_factory_registered"),
        "is_hazardous_material":    factory.get("is_hazardous_material"),
        "is_multi_use":             factory.get("is_multi_use"),
    }
    conditions.update(field_map)

    for fc in facility_condition:
        code = fc.get("condition_code")
        val  = fc.get("condition_value")
        if code and val is not None:
            conditions[code] = val

    return conditions


# ============================================================
# 설비 조건 판정 (equipment_assets 기반)
# ============================================================

def check_equipment_condition(rule: dict, equipment_map: dict) -> tuple[bool, dict]:
    """
    룰에 equipment_type_code가 있을 경우
    equipment_assets에서 해당 설비 존재 여부 + 용량 조건 비교

    Returns:
        (is_applicable, matched_info)
        matched_info: 어떤 설비가 매칭됐는지 정보
    """
    equip_type = rule.get("equipment_type_code")
    if not equip_type:
        return None, {}  # 설비 조건 없음 → factories 조건으로 판정

    # 해당 설비 유형의 equipment_assets 목록
    assets = equipment_map.get(equip_type, [])
    if not assets:
        return False, {"reason": f"설비 유형 {equip_type} 미등록"}

    # 설비 용량 조건 확인
    equip_cond_code  = rule.get("equipment_condition_code")
    equip_cond_op    = rule.get("equipment_condition_operator")
    equip_cond_value = rule.get("equipment_condition_value")

    if not equip_cond_code or equip_cond_op is None or equip_cond_value is None:
        # 용량 조건 없음 → 설비 존재 자체로 적용
        matched = assets[0]
        return True, {
            "asset_id":   matched.get("id"),
            "asset_name": matched.get("asset_name"),
            "match_type": "existence",
        }

    # 용량 조건 비교 — 가장 큰 용량의 설비로 판정
    best_match = None
    for asset in assets:
        if not asset.get("is_operating", True):
            continue
        asset_value = asset.get(equip_cond_code) or asset.get("capacity_value")
        if compare(asset_value, equip_cond_op, equip_cond_value):
            if best_match is None:
                best_match = asset
            else:
                # 더 큰 용량 우선
                try:
                    if float(asset_value or 0) > float(
                        best_match.get(equip_cond_code) or best_match.get("capacity_value") or 0
                    ):
                        best_match = asset
                except (TypeError, ValueError):
                    pass

    if best_match:
        return True, {
            "asset_id":     best_match.get("id"),
            "asset_name":   best_match.get("asset_name"),
            "asset_value":  best_match.get(equip_cond_code) or best_match.get("capacity_value"),
            "match_type":   "capacity",
        }

    return False, {
        "reason": f"설비 {equip_type} 존재하나 조건 미충족 ({equip_cond_op} {equip_cond_value})"
    }


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

    # 2) facility_condition 로드
    fc_res = supabase.table("facility_condition")\
        .select("*")\
        .eq("factory_id", factory_id)\
        .execute()
    facility_condition = fc_res.data or []

    # 3) equipment_assets 로드 — 설비 유형별 그룹화
    equip_res = supabase.table("equipment_assets")\
        .select("*")\
        .eq("factory_id", factory_id)\
        .execute()
    equipment_assets = equip_res.data or []

    # equipment_type_code 기준으로 그룹화
    equipment_map: dict[str, list] = {}
    for asset in equipment_assets:
        etype = asset.get("equipment_type_code")
        if etype:
            equipment_map.setdefault(etype, []).append(asset)

    # 4) 조건값 추출
    conditions = extract_factory_conditions(factory, facility_condition)

    # 5) 전체 법령 룰 로드
    rules_res = supabase.table("master_building_legal_rules")\
        .select("*")\
        .eq("is_active", True)\
        .order("priority_no")\
        .execute()
    rules = rules_res.data or []

    # 6) 기존 legal_applications 삭제 (재판정)
    supabase.table("legal_applications")\
        .delete()\
        .eq("factory_id", factory_id)\
        .execute()

    # 7) 각 룰 판정
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
            if factory.get("building_use_type_code") != building_use_type_code:
                continue

        # 업종 필터
        business_type_code = rule.get("business_type_code")
        if business_type_code:
            factory_business = factory.get("business_type_code") or factory.get("industry_type_code")
            if factory_business != business_type_code:
                continue

        # ── 판정 로직 ──────────────────────────────────────────
        equip_type = rule.get("equipment_type_code")

        if equip_type:
            # [설비 기반 판정]
            # 설비 조건 체크 → 맞으면 적용, 틀리면 미적용
            is_applicable, equip_match = check_equipment_condition(rule, equipment_map)

            if is_applicable:
                condition_code     = rule.get("condition_code")
                condition_operator = rule.get("condition_operator_code")
                condition_value    = rule.get("condition_value")
                factory_value      = conditions.get(condition_code)

                # factories 조건도 함께 있으면 AND 조건으로 추가 검증
                if condition_code and condition_value is not None:
                    is_applicable = compare(factory_value, condition_operator, condition_value)

            matched_conditions = {
                "match_source":       "equipment",
                "equipment_type":     equip_type,
                "equipment_match":    equip_match,
                "matched":            is_applicable,
            }
        else:
            # [시설 기반 판정]
            condition_code     = rule.get("condition_code")
            condition_operator = rule.get("condition_operator_code")
            condition_value    = rule.get("condition_value")
            factory_value      = conditions.get(condition_code)
            is_applicable      = compare(factory_value, condition_operator, condition_value)

            matched_conditions = {
                "match_source":       "factory",
                "condition_code":     condition_code,
                "condition_operator": condition_operator,
                "condition_value":    str(condition_value),
                "factory_value":      str(factory_value),
                "matched":            is_applicable,
            }
        # ────────────────────────────────────────────────────────

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
            if equip_type:
                reason = equip_match.get("reason", f"설비 {equip_type} 조건 미충족")
            else:
                reason = f"{condition_code} = {factory_value} (조건 미충족: {condition_operator} {condition_value})"

            results["not_applicable"].append({
                "rule_id":     rule.get("rule_id"),
                "law_name":    rule.get("law_name"),
                "law_article": rule.get("law_article"),
                "reason":      reason,
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
                # 설비 기반인 경우 어떤 설비가 트리거 됐는지
                "triggered_by_equipment":       equip_type if equip_type else None,
            })

        # 점검 필요
        if rule.get("inspection_required"):
            results["inspection_required"].append({
                "rule_id":                  rule.get("rule_id"),
                "law_name":                 rule.get("law_name"),
                "law_article":              rule.get("law_article"),
                "inspection_type":          rule.get("inspection_type_code"),
                "cycle_unit":               rule.get("inspection_cycle_unit_code"),
                "cycle_value":              rule.get("inspection_cycle_value"),
                "actor_code":               rule.get("inspection_actor_code"),
                "triggered_by_equipment":   equip_type if equip_type else None,
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
                "rule_id":       rule.get("rule_id"),
                "law_name":      rule.get("law_name"),
                "law_article":   rule.get("law_article"),
                "penalty_type":  rule.get("penalty_type_code"),
                "penalty_value": rule.get("penalty_value"),
                "penalty_unit":  rule.get("penalty_unit_code"),
            })

    # 8) legal_applications 일괄 저장
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
        return {"status": "success", "data": result}
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
