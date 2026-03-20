# routers/ksic_engine.py
# KSIC → 공정 → 설비 → 법령 자동 판정 엔진
# - GET  /ksic-engine/recommend-equipment/{factory_id}  KSIC 기반 설비 추천
# - POST /ksic-engine/apply/{factory_id}                KSIC 기반 법령 판정
# - GET  /ksic-engine/ksic-search                       KSIC 코드 검색

from fastapi import APIRouter, HTTPException, Query
from db.supabase_client import get_supabase
from datetime import datetime
from typing import Optional, List
import traceback

router = APIRouter(tags=["ksic_engine"])

ENGINE_VERSION = "1.0.0"

# ============================================================
# facility_name_std → equipment_type_code 매핑 테이블
# process_equipment_map.facility_name_std 기준
# ============================================================

FACILITY_TO_EQUIPMENT_TYPE = {
    # 전기 설비 (001~010)
    "변압기":           "001",
    "수변전반":         "001",
    "수배전반":         "006",
    "배전반":           "006",
    "분전반":           "007",
    "전동기":           "008",
    "모터":             "008",
    "UPS":             "009",
    "무정전전원장치":   "009",
    "비상발전기":       "010",
    "발전기":           "010",
    "차단기":           "002",
    "기중차단기":       "002",
    "진공차단기":       "003",
    "배선용차단기":     "004",
    "누전차단기":       "005",

    # 기계 설비 (011~020)
    "펌프":             "011",
    "압축기":           "012",
    "컴프레서":         "012",
    "열교환기":         "013",
    "보일러":           "014",
    "증기보일러":       "014",
    "온수보일러":       "014",
    "탱크":             "015",
    "저장탱크":         "015",
    "밸브":             "016",
    "배관":             "017",
    "팬":               "018",
    "송풍기":           "018",
    "냉동기":           "019",
    "냉장기":           "019",
    "칠러":             "020",

    # 중장비 (021~026)
    "크레인":           "021",
    "천장크레인":       "021",
    "이동식크레인":     "021",
    "호이스트":         "022",
    "프레스":           "023",
    "유압프레스":       "023",
    "컨베이어":         "024",
    "컨베이어벨트":     "024",
    "승강기":           "025",
    "엘리베이터":       "025",
    "에스컬레이터":     "026",

    # 저장탱크 (027~030)
    "가스탱크":         "027",
    "고압가스탱크":     "027",
    "LPG탱크":         "028",
    "액화석유가스탱크": "028",
    "화학물질탱크":     "029",
    "유해화학물질탱크": "029",
    "유류탱크":         "030",
    "경유탱크":         "030",
    "기름탱크":         "030",

    # 소방 설비 (031~034)
    "스프링클러":       "031",
    "자동소화장치":     "031",
    "자동화재탐지":     "032",
    "화재감지기":       "032",
    "소화기":           "033",
    "소화전":           "034",
    "옥내소화전":       "034",

    # 환경 설비 (035~040)
    "배기시설":         "035",
    "배기장치":         "035",
    "집진기":           "036",
    "집진장치":         "036",
    "오수처리시설":     "037",
    "하수처리시설":     "037",
    "압력용기":         "038",
    "냉동냉각기":       "039",
    "냉각탑":           "039",
    "공조기":           "039",  # 공조기는 냉동기(039)로 매핑
    "공조장치":         "039",
}


def map_facility_to_equipment_type(facility_name: str) -> Optional[str]:
    """설비 표준명 → equipment_type_code 매핑"""
    if not facility_name:
        return None

    # 완전 일치
    if facility_name in FACILITY_TO_EQUIPMENT_TYPE:
        return FACILITY_TO_EQUIPMENT_TYPE[facility_name]

    # 부분 일치 (키가 설비명에 포함되는 경우)
    for key, code in FACILITY_TO_EQUIPMENT_TYPE.items():
        if key in facility_name or facility_name in key:
            return code

    return None


# ============================================================
# KSIC → 공정 → 설비 조회
# ============================================================

def get_equipment_by_ksic(ksic_code: str, supabase, match_bands: list = None) -> list:
    """
    KSIC 코드 기반으로 예상 설비 목록 반환
    match_band: MUST > CORE > CORE_PLUS > OPTIONAL
    """
    if not ksic_code:
        return []

    if match_bands is None:
        match_bands = ["MUST", "CORE", "CORE_PLUS"]

    # process_equipment_map에서 직접 조회
    equip_res = supabase.table("process_equipment_map")\
        .select("facility_name_std, match_band, match_score, match_rank, category_path, equipment_role")\
        .eq("industry_code_full", ksic_code)\
        .in_("match_band", match_bands)\
        .order("match_score", desc=True)\
        .limit(100)\
        .execute()

    if not equip_res.data:
        # 4자리 → 3자리로 축소해서 재시도
        ksic_3 = ksic_code[:3]
        equip_res = supabase.table("process_equipment_map")\
            .select("facility_name_std, match_band, match_score, match_rank, category_path, equipment_role")\
            .like("industry_code_full", f"{ksic_3}%")\
            .in_("match_band", match_bands)\
            .order("match_score", desc=True)\
            .limit(100)\
            .execute()

    # 중복 설비 제거 (facility_name_std 기준, 가장 높은 match_score 유지)
    seen = {}
    for e in equip_res.data or []:
        name = e.get("facility_name_std", "")
        if name and name not in seen:
            seen[name] = e
        elif name and e.get("match_score", 0) > seen[name].get("match_score", 0):
            seen[name] = e

    return list(seen.values())


# ============================================================
# 설비 → 법령 룰 조회
# ============================================================

def get_rules_by_equipment_types(equipment_type_codes: list, supabase) -> list:
    """equipment_type_code 목록 기반 법령 룰 조회"""
    if not equipment_type_codes:
        return []

    rules_res = supabase.table("master_building_legal_rules")\
        .select("*")\
        .in_("equipment_type_code", equipment_type_codes)\
        .eq("is_active", True)\
        .order("priority_no")\
        .execute()

    return rules_res.data or []


# ============================================================
# 엔드포인트 1: KSIC 기반 설비 추천
# ============================================================

@router.get("/recommend-equipment/{factory_id}")
def recommend_equipment(
    factory_id: str,
    include_optional: bool = Query(False, description="OPTIONAL 설비도 포함")
):
    """
    KSIC 코드 기반으로 시설에 필요한 설비 목록 추천
    """
    supabase = get_supabase()

    # factory 조회
    factory_res = supabase.table("factories")\
        .select("id, name, ksic_code, ksic_name, industry_type_code")\
        .eq("id", factory_id)\
        .single().execute()

    if not factory_res.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다")

    factory = factory_res.data
    ksic_code = factory.get("ksic_code")

    if not ksic_code:
        return {
            "status": "warning",
            "message": "KSIC 코드가 등록되지 않았습니다. 시설 정보에서 업종코드를 입력해주세요.",
            "factory_id": factory_id,
            "factory_name": factory.get("name"),
        }

    # match_band 설정
    match_bands = ["MUST", "CORE", "CORE_PLUS"]
    if include_optional:
        match_bands.append("OPTIONAL")

    # 설비 조회
    equipments = get_equipment_by_ksic(ksic_code, supabase, match_bands)

    # equipment_type_code 매핑
    result_equipments = []
    for e in equipments:
        facility_name = e.get("facility_name_std", "")
        eq_type_code = map_facility_to_equipment_type(facility_name)
        result_equipments.append({
            "facility_name_std":  facility_name,
            "equipment_type_code": eq_type_code,
            "match_band":         e.get("match_band"),
            "match_score":        e.get("match_score"),
            "category_path":      e.get("category_path"),
            "is_mapped":          eq_type_code is not None,
        })

    # 현재 등록된 설비와 비교
    existing_res = supabase.table("equipment_assets")\
        .select("asset_name, equipment_type_code")\
        .eq("factory_id", factory_id)\
        .execute()
    existing_types = set(
        e.get("equipment_type_code")
        for e in (existing_res.data or [])
        if e.get("equipment_type_code")
    )

    # 미등록 설비 표시
    for eq in result_equipments:
        eq["is_registered"] = eq.get("equipment_type_code") in existing_types

    # 통계
    total       = len(result_equipments)
    mapped      = sum(1 for e in result_equipments if e["is_mapped"])
    registered  = sum(1 for e in result_equipments if e["is_registered"])
    must_count  = sum(1 for e in result_equipments if e["match_band"] == "MUST")
    core_count  = sum(1 for e in result_equipments if e["match_band"] in ["CORE", "CORE_PLUS"])

    return {
        "status":       "success",
        "factory_id":   factory_id,
        "factory_name": factory.get("name"),
        "ksic_code":    ksic_code,
        "ksic_name":    factory.get("ksic_name"),
        "summary": {
            "total_recommended": total,
            "must_equipment":    must_count,
            "core_equipment":    core_count,
            "mapped_to_type":    mapped,
            "already_registered": registered,
            "not_registered":    mapped - registered,
        },
        "equipments":   result_equipments,
    }


# ============================================================
# 엔드포인트 2: KSIC 기반 법령 자동 판정 (설비 추천 + 법령 적용)
# ============================================================

@router.post("/apply/{factory_id}")
def apply_ksic_rules(factory_id: str):
    """
    KSIC 코드 기반으로:
    1. 예상 설비 목록 추출 (MUST+CORE)
    2. 해당 설비의 법령 룰 판정
    3. 현재 등록된 설비 + KSIC 추천 설비 통합 판정
    """
    supabase = get_supabase()

    # factory 조회
    factory_res = supabase.table("factories")\
        .select("*")\
        .eq("id", factory_id)\
        .single().execute()

    if not factory_res.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다")

    factory   = factory_res.data
    ksic_code = factory.get("ksic_code")

    result = {
        "factory_id":    factory_id,
        "factory_name":  factory.get("name"),
        "ksic_code":     ksic_code,
        "ksic_name":     factory.get("ksic_name"),
        "evaluated_at":  datetime.now().isoformat(),
        "engine_version": ENGINE_VERSION,
    }

    if not ksic_code:
        result["warning"] = "KSIC 코드 미등록 — 설비 추천 불가"
        result["recommended_equipments"] = []
        result["ksic_based_rules"] = []
        return {"status": "warning", "data": result}

    # KSIC → 설비 추천
    recommended = get_equipment_by_ksic(ksic_code, supabase, ["MUST", "CORE", "CORE_PLUS"])
    recommended_type_codes = list(set(filter(None, [
        map_facility_to_equipment_type(e.get("facility_name_std", ""))
        for e in recommended
    ])))

    # 현재 등록된 설비
    existing_res = supabase.table("equipment_assets")\
        .select("equipment_type_code, asset_name")\
        .eq("factory_id", factory_id)\
        .execute()
    existing_type_codes = list(set(filter(None, [
        e.get("equipment_type_code")
        for e in (existing_res.data or [])
    ])))

    # 통합 (등록 + 추천)
    all_type_codes = list(set(recommended_type_codes + existing_type_codes))

    # 법령 룰 조회
    rules = get_rules_by_equipment_types(all_type_codes, supabase)

    # 룰 분류
    appointment_rules = []
    inspection_rules  = []
    action_rules      = []
    report_rules      = []

    for rule in rules:
        eq_code = rule.get("equipment_type_code")
        source  = "registered" if eq_code in existing_type_codes else "recommended"

        base = {
            "rule_id":            rule.get("rule_id"),
            "law_name":           rule.get("law_name"),
            "law_article":        rule.get("law_article"),
            "equipment_type":     eq_code,
            "source":             source,  # registered | recommended
        }

        if rule.get("appointment_required"):
            appointment_rules.append({**base,
                "appointment_target": rule.get("appointment_target_code"),
                "qualification":      rule.get("appointment_qualification_code"),
            })
        if rule.get("inspection_required"):
            inspection_rules.append({**base,
                "cycle_unit":  rule.get("inspection_cycle_unit_code"),
                "cycle_value": rule.get("inspection_cycle_value"),
            })
        if rule.get("action_required"):
            action_rules.append({**base,
                "action_type": rule.get("action_type_code"),
            })
        if rule.get("report_required"):
            report_rules.append({**base})

    result.update({
        "recommended_equipments": [
            {
                "facility_name": e.get("facility_name_std"),
                "equipment_type_code": map_facility_to_equipment_type(e.get("facility_name_std", "")),
                "match_band": e.get("match_band"),
                "is_registered": map_facility_to_equipment_type(e.get("facility_name_std", "")) in existing_type_codes,
            }
            for e in recommended[:30]
        ],
        "summary": {
            "recommended_equipment_count": len(recommended),
            "mapped_type_codes":           len(recommended_type_codes),
            "registered_type_codes":       len(existing_type_codes),
            "total_rules_triggered":       len(rules),
            "appointment_required":        len(appointment_rules),
            "inspection_required":         len(inspection_rules),
            "action_required":             len(action_rules),
            "report_required":             len(report_rules),
        },
        "appointment_required": appointment_rules,
        "inspection_required":  inspection_rules,
        "action_required":      action_rules,
        "report_required":      report_rules,
    })

    return {"status": "success", "data": result}


# ============================================================
# 엔드포인트 3: KSIC 코드 검색
# ============================================================

@router.get("/ksic-search")
def ksic_search(
    query: str = Query(..., description="업종명 또는 코드 검색"),
    limit: int = Query(20, le=100)
):
    """KSIC 코드 검색"""
    supabase = get_supabase()

    # 코드 검색
    if query.isdigit():
        res = supabase.table("industry_master")\
            .select("lv4_code, lv4_name, industry_path_ko, lv1_code, lv1_name")\
            .like("lv4_code", f"{query}%")\
            .eq("is_active", True)\
            .limit(limit).execute()
    else:
        # 업종명 검색
        res = supabase.table("industry_master")\
            .select("lv4_code, lv4_name, industry_path_ko, lv1_code, lv1_name")\
            .ilike("lv4_name", f"%{query}%")\
            .eq("is_active", True)\
            .limit(limit).execute()

    return {
        "status": "success",
        "query":  query,
        "count":  len(res.data or []),
        "data":   res.data or [],
    }


# ============================================================
# 엔드포인트 4: KSIC 업종별 설비 통계
# ============================================================

@router.get("/ksic-equipment-stats/{ksic_code}")
def ksic_equipment_stats(ksic_code: str):
    """특정 KSIC 코드의 설비 통계"""
    supabase = get_supabase()

    # 설비 조회
    equipments = get_equipment_by_ksic(
        ksic_code, supabase,
        ["MUST", "CORE", "CORE_PLUS", "OPTIONAL"]
    )

    # match_band별 분류
    by_band = {}
    for e in equipments:
        band = e.get("match_band", "UNKNOWN")
        if band not in by_band:
            by_band[band] = []
        by_band[band].append({
            "facility_name": e.get("facility_name_std"),
            "equipment_type_code": map_facility_to_equipment_type(e.get("facility_name_std", "")),
            "match_score": e.get("match_score"),
        })

    # 법령 룰 수 계산
    all_type_codes = list(set(filter(None, [
        map_facility_to_equipment_type(e.get("facility_name_std", ""))
        for e in equipments
    ])))
    rules = get_rules_by_equipment_types(all_type_codes, supabase)

    # KSIC 정보
    industry_res = supabase.table("industry_master")\
        .select("lv4_code, lv4_name, industry_path_ko")\
        .eq("lv4_code", ksic_code)\
        .limit(1).execute()

    return {
        "status":       "success",
        "ksic_code":    ksic_code,
        "industry":     industry_res.data[0] if industry_res.data else None,
        "equipment_summary": {
            "total":      len(equipments),
            "must":       len(by_band.get("MUST", [])),
            "core":       len(by_band.get("CORE", [])),
            "core_plus":  len(by_band.get("CORE_PLUS", [])),
            "optional":   len(by_band.get("OPTIONAL", [])),
        },
        "law_rules_count": len(rules),
        "by_band": by_band,
    }


@router.get("/test")
def test():
    return {"message": "KSIC engine alive", "version": ENGINE_VERSION}
