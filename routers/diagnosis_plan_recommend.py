"""
routers/diagnosis_plan_recommend.py — v1.1.0

v1.1.0 (TASK 7):
  추천 응답에서 가격 제거, 필요성만 표시.
  - recommended: monthly_krw / pricing_note / is_custom 제거 → necessity 추가
  - comparison: TAI Safe 연간비용 제거, 과태료 위험만 유지
  - alternatives: monthly 제거
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException

from db.supabase_client import get_supabase

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/diagnosis", tags=["플랜추천"])

VERSION = "1.1.0"


_PLANS: dict[str, dict[str, Any]] = {
    "INDUSTRY_STARTER_V2":    {"name": "산업 STARTER",    "monthly": 79000,  "sector": "INDUSTRY",     "tier": 1, "is_custom": False},
    "INDUSTRY_BUSINESS_V2":   {"name": "산업 BUSINESS",   "monthly": 149000, "sector": "INDUSTRY",     "tier": 2, "is_custom": False},
    "INDUSTRY_PRO":           {"name": "산업 PRO",          "monthly": 249000, "sector": "INDUSTRY",     "tier": 3, "is_custom": False},
    "INDUSTRY_CUSTOM_V2":     {"name": "산업 CUSTOM",      "monthly": 0,      "sector": "INDUSTRY",     "tier": 4, "is_custom": True},
    "BUILDING_BASIC":         {"name": "건물 BASIC",          "monthly": 59000,  "sector": "BUILDING",     "tier": 1, "is_custom": False},
    "BUILDING_STANDARD":      {"name": "건물 STANDARD",     "monthly": 145000, "sector": "BUILDING",     "tier": 2, "is_custom": False},
    "BUILDING_CUSTOM":        {"name": "건물 CUSTOM",        "monthly": 249000, "sector": "BUILDING",     "tier": 3, "is_custom": False},
    "CONSTRUCTION_STANDARD_V2": {"name": "건설 STANDARD",  "monthly": 145000, "sector": "CONSTRUCTION", "tier": 1, "is_custom": False},
    "CONSTRUCTION_PREMIUM_V2":  {"name": "건설 PREMIUM",   "monthly": 385000, "sector": "CONSTRUCTION", "tier": 2, "is_custom": False},
    "CONSTRUCTION_CUSTOM_V2":   {"name": "건설 CUSTOM",     "monthly": 0,      "sector": "CONSTRUCTION", "tier": 3, "is_custom": True},
}

_SECTOR_PLANS: dict[str, list[str]] = {
    "INDUSTRY":     ["INDUSTRY_STARTER_V2", "INDUSTRY_BUSINESS_V2", "INDUSTRY_PRO", "INDUSTRY_CUSTOM_V2"],
    "BUILDING":     ["BUILDING_BASIC", "BUILDING_STANDARD", "BUILDING_CUSTOM"],
    "CONSTRUCTION": ["CONSTRUCTION_STANDARD_V2", "CONSTRUCTION_PREMIUM_V2", "CONSTRUCTION_CUSTOM_V2"],
}

# TASK 7: 플랜별 필요성 텍스트 (가격 미포함)
_NECESSITY: dict[str, str] = {
    "INDUSTRY_STARTER_V2":    "소규모 사업장 핵심 법적 의무 수행에 필요한 기본 플랜입니다",
    "INDUSTRY_BUSINESS_V2":   "중규모 사업장 체계적 점검 일정 자동화와 분산 배치에 필요합니다",
    "INDUSTRY_PRO":           "고위험·대규모 사업장 전수 설비 관리와 API 연동에 필요합니다",
    "INDUSTRY_CUSTOM_V2":     "500명 이상 대규모 사업장에 맞춤 구성이 필요합니다",
    "BUILDING_BASIC":         "소규모 건물 핵심 점검 항목 관리에 필요한 기본 플랜입니다",
    "BUILDING_STANDARD":      "중규모 건물 정기 점검 자동화와 작업 배분에 필요합니다",
    "BUILDING_CUSTOM":        "대형 복합 건물 소방·전기·승강기 통합 관리에 필요합니다",
    "CONSTRUCTION_STANDARD_V2": "건설 현장 기본 안전 관리와 기상 연동에 필요한 플랜입니다",
    "CONSTRUCTION_PREMIUM_V2":  "고위험 건설 현장 PTW·TBM·위험성평가 자동화에 필요합니다",
    "CONSTRUCTION_CUSTOM_V2":   "대형 건설 현장 다현장 통합 관리에 필요합니다",
}


def _effective_obligation_count(rd: dict, rule_count: int) -> int:
    obl = rd.get("obligations") or []
    if isinstance(obl, list) and len(obl) > 0:
        return len(obl)
    return rule_count or 0


def _recommend_industry(severity: str, obl_cnt: int, workers: int) -> tuple[str, list[str]]:
    if workers > 500:
        return "INDUSTRY_CUSTOM_V2", [
            f"작업자 {workers}명 — 대규모 사업장으로 맞춤 구성이 필요합니다",
            "전담 TAI 컨설턴트가 최적 구성을 안내드립니다",
        ]
    if severity == "CRITICAL" or obl_cnt > 150 or workers > 200:
        reasons = []
        if severity == "CRITICAL":
            reasons.append("위험도 CRITICAL — 중대재해처벌법 대응을 위한 전사적 관리가 필요합니다")
        if obl_cnt > 150:
            reasons.append(f"법적 의무 {obl_cnt}건 — 150건 초과로 전수 관리가 필요합니다")
        if workers > 200:
            reasons.append(f"작업자 {workers}명 — 200인 초과 사업장 전담 기능이 필요합니다")
        reasons.append("무제한 설비 등록 + API 연동 + 전담 지원 포함")
        return "INDUSTRY_PRO", reasons[:4]
    if severity in ("MEDIUM", "HIGH") or 50 <= obl_cnt <= 150:
        reasons = []
        if severity in ("MEDIUM", "HIGH"):
            reasons.append(f"위험도 {severity} — 체계적인 점검 일정 자동화가 필요합니다")
        if obl_cnt >= 50:
            reasons.append(f"법적 의무 {obl_cnt}건 — 자동 일정 생성으로 누락 방지가 필요합니다")
        reasons.append("작업 분산 배치 + 지연 알림 + 월간 리포트 포함")
        return "INDUSTRY_BUSINESS_V2", reasons[:4]
    reasons = ["위험도 LOW — 기본 점검 관리로 법적 의무를 충족할 수 있습니다"]
    if obl_cnt < 50:
        reasons.append(f"법적 의무 {obl_cnt}건 — 기본 플랜으로 충분히 관리 가능합니다")
    if workers < 50:
        reasons.append(f"작업자 {workers}명 — 소규모 사업장에 적합합니다")
    return "INDUSTRY_STARTER_V2", reasons[:4]


def _recommend_building(severity: str, obl_cnt: int, workers: int) -> tuple[str, list[str]]:
    if severity == "CRITICAL" or obl_cnt > 100:
        reasons = []
        if severity == "CRITICAL":
            reasons.append("위험도 CRITICAL — 복합 건물 전수 점검 관리가 필요합니다")
        if obl_cnt > 100:
            reasons.append(f"법적 의무 {obl_cnt}건 — 무제한 점검 설정이 필요합니다")
        reasons.append("소방·전기·승강기 통합 관리 + 전담 지원 포함")
        return "BUILDING_CUSTOM", reasons[:4]
    if severity in ("MEDIUM", "HIGH") or 30 <= obl_cnt <= 100:
        reasons = []
        if severity in ("MEDIUM", "HIGH"):
            reasons.append(f"위험도 {severity} — 정기 점검 자동화로 누락을 방지해야 합니다")
        if obl_cnt >= 30:
            reasons.append(f"법적 의무 {obl_cnt}건 — 체계적 관리가 필요합니다")
        reasons.append("점검 일정 자동 생성 + 작업 배분 + 리포트 포함")
        return "BUILDING_STANDARD", reasons[:4]
    reasons = ["위험도 LOW — 기본 점검 관리로 법적 의무를 충족할 수 있습니다"]
    if workers < 30:
        reasons.append(f"관리 인원 {workers}명 — 소규모 시설에 적합합니다")
    reasons.append("핵심 점검 항목 관리 + 법령 변경 알림 포함")
    return "BUILDING_BASIC", reasons[:4]


def _recommend_construction(severity: str, obl_cnt: int, workers: int) -> tuple[str, list[str]]:
    if workers > 300:
        return "CONSTRUCTION_CUSTOM_V2", [
            f"현장 작업자 {workers}명 — 대형 현장 맞춤 구성이 필요합니다",
            "다현장 통합 관리 + 전담 TAI 컨설턴트 지원",
        ]
    if severity in ("CRITICAL", "HIGH") or obl_cnt > 80:
        reasons = []
        if severity in ("CRITICAL", "HIGH"):
            reasons.append(f"위험도 {severity} — PTW·TBM 자동화가 필요합니다")
        if obl_cnt > 80:
            reasons.append(f"법적 의무 {obl_cnt}건 — 전수 관리를 위한 PREMIUM이 필요합니다")
        reasons.append("위험성평가 + PTW + TBM 자동생성 포함")
        return "CONSTRUCTION_PREMIUM_V2", reasons[:4]
    reasons = ["기본 안전 관리로 건설 현장 법적 의무를 충족할 수 있습니다"]
    if severity == "MEDIUM":
        reasons.append("위험도 MEDIUM — 점검 일정 자동화가 필요합니다")
    reasons.append("공종별 점검 + 작업중지 기상 연동 포함")
    return "CONSTRUCTION_STANDARD_V2", reasons[:4]


def _build_alternatives(sector: str, recommended_code: str) -> dict:
    """TASK 7: 대안 플랜에서 monthly 제거."""
    plan_list = _SECTOR_PLANS.get(sector, [])
    idx = plan_list.index(recommended_code) if recommended_code in plan_list else -1
    lower = upper = None
    if idx > 0:
        code = plan_list[idx - 1]
        lower = {
            "plan_code": code,
            "plan_name": _PLANS[code]["name"],
            "note":      "기본 기능 위주로 전환하고 싶다면",
        }
    if idx >= 0 and idx < len(plan_list) - 1:
        code = plan_list[idx + 1]
        upper = {
            "plan_code": code,
            "plan_name": _PLANS[code]["name"],
            "note":      "더 많은 기능과 지원이 필요하다면",
        }
    return {"lower": lower, "upper": upper}


def _build_comparison(recommended_code: str, penalty_risk_krw: int) -> dict:
    """TASK 7: 과태료 위험만 유지, TAI Safe 가격 제거."""
    return {
        "annual_penalty_risk_krw": penalty_risk_krw,
        "note": (
            f"연간 최대 {penalty_risk_krw:,}원의 과태료 위험을 관리할 수 있습니다"
            if penalty_risk_krw > 0
            else "법령 진단 완료 후 정확한 비교가 가능합니다"
        ),
    }


@router.get("/{diagnosis_id}/recommend-plan")
def recommend_plan(diagnosis_id: str):
    """
    v1.1.0 TASK 7: 추천 응답에서 가격 제거, 필요성만 표시.
    """
    sb = get_supabase()
    diag_res = (sb.table("factory_diagnosis_results")
                .select("id, factory_id, sector, diagnosis_stage, rule_count, result_data")
                .eq("id", diagnosis_id).limit(1).execute())
    if not diag_res.data:
        raise HTTPException(status_code=404, detail="진단 레코드를 찾을 수 없습니다.")

    diag = diag_res.data[0]
    rd: dict       = diag.get("result_data") or {}
    sector: str    = (diag.get("sector") or "").upper()
    rule_count: int = diag.get("rule_count") or 0

    factory: dict = {}
    if diag.get("factory_id"):
        fac_res = (sb.table("factories")
                   .select("id, name, sector, employee_count, total_worker_count_calc")
                   .eq("id", diag["factory_id"]).limit(1).execute())
        factory = fac_res.data[0] if fac_res.data else {}
        if factory.get("sector"):
            sector = str(factory["sector"]).upper()

    headline     = rd.get("headline") or {}
    severity     = str(headline.get("severity") or "LOW").upper()
    obl_cnt      = _effective_obligation_count(rd, rule_count)
    workers      = int(factory.get("total_worker_count_calc") or factory.get("employee_count") or 0)
    penalty_risk = int((rd.get("roi") or {}).get("annual_penalty_risk_krw") or 0)

    if sector == "INDUSTRY":
        plan_code, reasons = _recommend_industry(severity, obl_cnt, workers)
    elif sector == "BUILDING":
        plan_code, reasons = _recommend_building(severity, obl_cnt, workers)
    elif sector == "CONSTRUCTION":
        plan_code, reasons = _recommend_construction(severity, obl_cnt, workers)
    else:
        raise HTTPException(status_code=422,
            detail=f"지원하지 않는 섹터: '{sector}'")

    plan_info = _PLANS[plan_code]

    # TASK 7: 가격 제거, necessity 추가
    return {
        "status":  "success",
        "version": VERSION,
        "diagnosis_id": diagnosis_id,
        "sector":       sector,
        "input_summary": {
            "severity":  severity,
            "obl_count": obl_cnt,
            "workers":   workers,
            "stage":     diag.get("diagnosis_stage"),
        },
        "recommended": {
            "plan_code": plan_code,
            "plan_name": plan_info["name"],
            "necessity": _NECESSITY.get(plan_code, ""),
        },
        "reasons":      reasons,
        "alternatives": _build_alternatives(sector, plan_code),
        "comparison":   _build_comparison(plan_code, penalty_risk),
        "factory": {
            "id":   factory.get("id"),
            "name": factory.get("name"),
        },
        "cta": {
            "primary":   {"label": "지금 시작하기",       "action": "go_pricing", "plan_code": plan_code},
            "secondary": {"label": "전체 요금제 비교하기", "action": "go_pricing_all"},
        },
    }
