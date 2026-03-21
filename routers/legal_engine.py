# routers/legal_engine.py  v2.0.0
# legal_engine + ksic_engine 통합 판정
#
# 판정 순서:
#   1. factories 조건 기반 룰 판정 (building_area, employee_count 등)
#   2. 등록된 equipment_assets 기반 룰 판정
#   3. KSIC → 공정 → 설비 추천 기반 룰 판정 (미등록 설비 포함)
#   4. 결과 통합 (중복 제거, 출처 표시)

from fastapi import APIRouter, HTTPException
from db.supabase_client import get_supabase
from datetime import datetime
from typing import Optional, List, Dict, Any

router = APIRouter(tags=["legal_engine"])

ENGINE_VERSION = "2.0.0"

# ============================================================
# facility_name_std → equipment_type_code 매핑
# ============================================================
FACILITY_TO_EQUIPMENT_TYPE: Dict[str, str] = {
    "변압기":"001","수변전반":"001","수배전반":"006","배전반":"006",
    "분전반":"007","전동기":"008","모터":"008","UPS":"009",
    "무정전전원장치":"009","비상발전기":"010","발전기":"010",
    "차단기":"002","기중차단기":"002","진공차단기":"003",
    "배선용차단기":"004","누전차단기":"005",
    "펌프":"011","압축기":"012","컴프레서":"012","열교환기":"013",
    "보일러":"014","증기보일러":"014","온수보일러":"014",
    "탱크":"015","저장탱크":"015","밸브":"016","배관":"017",
    "팬":"018","송풍기":"018","냉동기":"019","냉장기":"019","칠러":"020",
    "크레인":"021","천장크레인":"021","이동식크레인":"021",
    "호이스트":"022","프레스":"023","유압프레스":"023",
    "컨베이어":"024","컨베이어벨트":"024",
    "승강기":"025","엘리베이터":"025","에스컬레이터":"026",
    "가스탱크":"027","고압가스탱크":"027","LPG탱크":"028",
    "화학물질탱크":"029","유류탱크":"030","경유탱크":"030",
    "스프링클러":"031","자동화재탐지":"032","화재감지기":"032",
    "소화기":"033","소화전":"034","옥내소화전":"034",
    "배기시설":"035","집진기":"036","집진장치":"036",
    "오수처리시설":"037","하수처리시설":"037","압력용기":"038",
    "냉동냉각기":"039","냉각탑":"039","공조기":"039","공조장치":"039",
    # 추가 매핑
    "프레스설비":"023","절단기":"023","절곡기":"023","노칭기":"023",
    "슬리터":"023","권취기":"023","적층기":"023","실링설비":"023",
    "물류자동화설비":"024","물류설비":"024",
    "건조설비":"014","건조기":"014","가열설비":"014","에이징 설비":"014",
    "제품저장탱크":"015","버퍼탱크":"015","혼합탱크":"015","원료저장탱크":"015",
    "위험물 옥외탱크저장소":"015","고압가스 저장탱크":"027",
    "고압가스 저장시설":"027","산업용배관망":"017","위험물 이송배관":"017",
    "위험물 밸브":"016","공정펌프":"011","이송펌프":"011","급수펌프":"011",
    "공정압축기":"012","압축공기공급설비":"012",
    "접지설비":"001","전력계측장치":"001","전력감시장치":"001",
    "가스감지설비":"032","화재감지설비":"032","가스누출감지기":"032",
    "위험물 방유제":"030","연료저장탱크":"030",
    "위험물 이송설비":"029","위험물 간이저장소":"029",
    "도장부스":"036","흡입설비":"036","국소배기장치":"036",
    "산업용배수설비":"037","폐수처리설비":"037",
    "냉각수공급설비":"039","질소공급설비":"012","진공공급설비":"012",
    "산업용로봇":"023","사출성형기":"023","분쇄설비":"012",
    "혼합설비":"011","교반기":"011","원심분리기":"011",
    "반응기":"015","증류탑":"015","흡수탑":"015",
    "생산라인설비":"024","전극 코팅기":"023","전극 압연기":"023",
    "용접전원장치":"008","산업안전설비":"034",
    "유틸리티모니터링설비":"001","유틸리티제어설비":"001",
    "용수공급설비":"011","산업용크레인":"021","갠트리크레인":"021",
    "전동호이스트":"022","산세설비":"015","샌드블라스트 설비":"036",
}

def get_equipment_type(name: str) -> Optional[str]:
    if not name:
        return None
    if name in FACILITY_TO_EQUIPMENT_TYPE:
        return FACILITY_TO_EQUIPMENT_TYPE[name]
    for key, code in FACILITY_TO_EQUIPMENT_TYPE.items():
        if key in name or name in key:
            return code
    return None


# ============================================================
# 조건 비교 헬퍼
# ============================================================
def compare(value: Any, operator: str, threshold: Any) -> bool:
    try:
        v = float(value)
        t = float(threshold)
    except (TypeError, ValueError):
        v = value
        t = threshold
    op_map = {
        "gte": v >= t, "gt": v > t,
        "lte": v <= t, "lt": v < t,
        "eq":  v == t, "neq": v != t,
    }
    return op_map.get(operator, False)


def check_factory_condition(rule: dict, factory: dict) -> bool:
    """factories 컬럼 기반 조건 판정"""
    code = rule.get("condition_code")
    op   = rule.get("condition_operator_code")
    val  = rule.get("condition_value")
    if not code or not op or val is None:
        return True
    factory_val = factory.get(code)
    if factory_val is None:
        return False
    return compare(factory_val, op, val)


def check_equipment_condition(rule: dict, equipment_type_codes: set) -> bool:
    """설비 유형 기반 조건 판정"""
    eq_code = rule.get("equipment_type_code")
    if not eq_code:
        return True  # 설비 조건 없음 → 통과
    return eq_code in equipment_type_codes


# ============================================================
# KSIC → 설비 추천 (process_equipment_map 기반)
# ============================================================
KSIC_MATCH_BANDS = ["MUST", "CORE", "CORE_PLUS"]

def get_ksic_equipment_types(factory: dict, supabase) -> Dict[str, str]:
    """
    KSIC 코드 기반 추천 설비 → equipment_type_code 딕셔너리 반환
    {facility_name: equipment_type_code}
    """
    ksic_code = factory.get("ksic_code")
    if not ksic_code:
        return {}

    # 등록된 공정 확인
    proc_res = supabase.table("factory_process")\
        .select("process_id")\
        .eq("factory_id", factory["id"])\
        .eq("is_active", True)\
        .execute()
    process_ids = [p["process_id"] for p in (proc_res.data or [])]

    # 공정 기반 설비 조회
    if process_ids:
        equip_res = supabase.table("process_equipment_map")\
            .select("facility_name_std, match_band, match_score")\
            .in_("process_id", process_ids)\
            .in_("match_band", KSIC_MATCH_BANDS)\
            .order("match_score", desc=True)\
            .limit(200).execute()
    else:
        # KSIC 직접 조회 (공정 미등록 시 fallback)
        equip_res = supabase.table("process_equipment_map")\
            .select("facility_name_std, match_band, match_score")\
            .eq("industry_code_full", ksic_code)\
            .in_("match_band", KSIC_MATCH_BANDS)\
            .order("match_score", desc=True)\
            .limit(200).execute()

        if not equip_res.data:
            # 3자리 코드로 재시도
            equip_res = supabase.table("process_equipment_map")\
                .select("facility_name_std, match_band, match_score")\
                .like("industry_code_full", f"{ksic_code[:3]}%")\
                .in_("match_band", KSIC_MATCH_BANDS)\
                .order("match_score", desc=True)\
                .limit(200).execute()

    # 중복 제거 후 equipment_type_code 매핑
    result = {}
    seen_names = set()
    for e in equip_res.data or []:
        name = e.get("facility_name_std", "")
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        eq_type = get_equipment_type(name)
        if eq_type:
            result[name] = eq_type

    return result


# ============================================================
# 메인 판정 함수
# ============================================================
def apply_rules(factory: dict, supabase) -> dict:
    factory_id = factory["id"]
    now = datetime.now().isoformat()

    # 1. 전체 활성 룰 로드
    rules_res = supabase.table("master_building_legal_rules")\
        .select("*")\
        .eq("is_active", True)\
        .execute()
    all_rules = rules_res.data or []

    # 2. 등록된 설비 유형 조회
    eq_res = supabase.table("equipment_assets")\
        .select("equipment_type_code, asset_name")\
        .eq("factory_id", factory_id)\
        .execute()
    registered_type_codes = set(
        e["equipment_type_code"] for e in (eq_res.data or [])
        if e.get("equipment_type_code")
    )

    # 3. KSIC 기반 추천 설비
    ksic_equipment = get_ksic_equipment_types(factory, supabase)
    ksic_type_codes = set(ksic_equipment.values())

    # 4. 통합 설비 유형 (등록 + KSIC 추천)
    all_type_codes = registered_type_codes | ksic_type_codes

    # 5. 룰별 판정
    applicable      = []
    not_applicable  = []

    for rule in all_rules:
        rule_id  = rule.get("rule_id")
        eq_code  = rule.get("equipment_type_code")

        # 조건 판정
        factory_ok   = check_factory_condition(rule, factory)
        equipment_ok = check_equipment_condition(rule, all_type_codes)

        if not factory_ok or not equipment_ok:
            not_applicable.append({
                "rule_id":    rule_id,
                "law_name":   rule.get("law_name"),
                "reason":     "factory_condition" if not factory_ok else "equipment_not_found",
            })
            continue

        # 출처 결정
        if eq_code:
            if eq_code in registered_type_codes:
                triggered_by = "registered_equipment"
            else:
                triggered_by = "ksic_recommended"
        else:
            triggered_by = "factory_condition"

        applicable.append({
            "rule_id":      rule_id,
            "law_name":     rule.get("law_name"),
            "law_article":  rule.get("law_article"),
            "rule_type":    rule.get("rule_type_code"),
            "triggered_by": triggered_by,
            "appointment_required": rule.get("appointment_required"),
            "appointment_target":   rule.get("appointment_target_code"),
            "appointment_qualification": rule.get("appointment_qualification_code"),
            "appointment_count":    rule.get("appointment_count_value"),
            "inspection_required":  rule.get("inspection_required"),
            "inspection_cycle_unit": rule.get("inspection_cycle_unit_code"),
            "inspection_cycle_value": rule.get("inspection_cycle_value"),
            "action_required":      rule.get("action_required"),
            "action_type":          rule.get("action_type_code"),
            "report_required":      rule.get("report_required"),
            "remarks":              rule.get("remarks"),
        })

    # 6. 유형별 분류
    appointment_rules = [r for r in applicable if r["appointment_required"]]
    inspection_rules  = [r for r in applicable if r["inspection_required"]]
    action_rules      = [r for r in applicable if r["action_required"]]
    report_rules      = [r for r in applicable if r["report_required"]]

    # 7. 출처별 통계
    by_source = {
        "factory_condition":    sum(1 for r in applicable if r["triggered_by"] == "factory_condition"),
        "registered_equipment": sum(1 for r in applicable if r["triggered_by"] == "registered_equipment"),
        "ksic_recommended":     sum(1 for r in applicable if r["triggered_by"] == "ksic_recommended"),
    }

    # 8. KSIC 설비 요약
    ksic_summary = [
        {"facility_name": name, "equipment_type_code": code,
         "is_registered": code in registered_type_codes}
        for name, code in ksic_equipment.items()
    ]

    return {
        "factory_id":           factory_id,
        "factory_name":         factory.get("name"),
        "ksic_code":            factory.get("ksic_code"),
        "ksic_name":            factory.get("ksic_name"),
        "evaluated_at":         now,
        "engine_version":       ENGINE_VERSION,
        "total_rules":          len(all_rules),
        "applicable_count":     len(applicable),
        "not_applicable_count": len(not_applicable),
        "summary": {
            "appointment_required": len(appointment_rules),
            "inspection_required":  len(inspection_rules),
            "action_required":      len(action_rules),
            "report_required":      len(report_rules),
        },
        "triggered_by_source": by_source,
        "ksic_equipment_count": len(ksic_equipment),
        "registered_equipment_count": len(registered_type_codes),
        "appointment_required": appointment_rules,
        "inspection_required":  inspection_rules,
        "action_required":      action_rules,
        "report_required":      report_rules,
        "not_applicable":       not_applicable,
        "ksic_equipment":       ksic_summary,
    }


# ============================================================
# 엔드포인트
# ============================================================

@router.post("/apply/{factory_id}")
def apply_legal_rules(factory_id: str):
    """
    통합 법령 판정 (v2.0.0)
    - factories 조건 기반 판정
    - 등록된 equipment_assets 기반 판정
    - KSIC → 공정 → 설비 추천 기반 판정 (미등록 포함)
    """
    supabase = get_supabase()

    factory_res = supabase.table("factories")\
        .select("*")\
        .eq("id", factory_id)\
        .single().execute()

    if not factory_res.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다")

    result = apply_rules(factory_res.data, supabase)
    return {"status": "success", "data": result}


@router.get("/result/{factory_id}")
def get_legal_result(factory_id: str):
    """마지막 판정 결과 조회 (캐시)"""
    supabase = get_supabase()

    res = supabase.table("legal_applications")\
        .select("*")\
        .eq("factory_id", factory_id)\
        .order("evaluated_at", desc=True)\
        .limit(1).execute()

    if not res.data:
        return {"status": "not_found", "message": "판정 결과 없음. /apply/{id} 먼저 실행하세요."}

    return {"status": "success", "data": res.data[0]}


@router.get("/summary/{factory_id}")
def get_legal_summary(factory_id: str):
    """판정 요약만 빠르게 반환"""
    supabase = get_supabase()

    factory_res = supabase.table("factories")\
        .select("id, name, ksic_code, ksic_name, building_area, employee_count, is_factory_registered")\
        .eq("id", factory_id)\
        .single().execute()

    if not factory_res.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다")

    result = apply_rules(factory_res.data, supabase)

    return {
        "status": "success",
        "data": {
            "factory_id":       result["factory_id"],
            "factory_name":     result["factory_name"],
            "ksic_code":        result["ksic_code"],
            "total_rules":      result["total_rules"],
            "applicable_count": result["applicable_count"],
            "summary":          result["summary"],
            "triggered_by_source": result["triggered_by_source"],
            "engine_version":   result["engine_version"],
        }
    }


@router.get("/test")
def test():
    return {"message": "TAI Legal Engine", "version": ENGINE_VERSION}
