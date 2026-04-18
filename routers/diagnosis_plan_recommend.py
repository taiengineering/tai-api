"""
routers/diagnosis_plan_recommend.py — v1.0.0

BE-08: 진단 기반 SaaS 플랜 자동 추천 API

엔드포인트:
  GET /diagnosis/{diagnosis_id}/recommend-plan

추천 로직: AI 없음. 조건 분기만.
  우선순위: severity > obligations 수 > 작업자 수

입력:
  factory_diagnosis_results.result_data → headline.severity, obligations[]
  factories.sector, total_worker_count_calc (없으면 employee_count)
  factory_diagnosis_results.rule_count (obligations 비어있을 때 대체)

출력:
  recommended   — 추천 플랜 코드 + 이름 + 월 요금
  reasons[]     — 추천 이유 2~4개
  alternatives  — 상위/하위 대안 플랜
  comparison    — 과태료 vs TAI Safe 비용 비교

플랜 코드 (price_saas_plan.plan_code):
  INDUSTRY: INDUSTRY_STARTER_V2(79K) / INDUSTRY_BUSINESS_V2(149K)
            INDUSTRY_PRO(249K) / INDUSTRY_CUSTOM_V2(협의)
  BUILDING: BUILDING_BASIC(59K) / BUILDING_STANDARD(145K)
            BUILDING_CUSTOM(249K)
  CONSTRUCTION: CONSTRUCTION_STANDARD_V2(145K) / CONSTRUCTION_PREMIUM_V2(385K)
                CONSTRUCTION_CUSTOM_V2(협의)
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException

from db.supabase_client import get_supabase

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/diagnosis", tags=["플랜추천"])

VERSION = "1.0.0"


# ─────────────────────────────────────────────────────────────────────────────
# 플랜 정의 (price_saas_plan.plan_code 기반)
# ─────────────────────────────────────────────────────────────────────────────

_PLANS: dict[str, dict[str, Any]] = {
    # INDUSTRY
    "INDUSTRY_STARTER_V2": {
        "name": "산업 STARTER", "monthly": 79000,
        "sector": "INDUSTRY", "tier": 1, "is_custom": False,
    },
    "INDUSTRY_BUSINESS_V2": {
        "name": "산업 BUSINESS", "monthly": 149000,
        "sector": "INDUSTRY", "tier": 2, "is_custom": False,
    },
    "INDUSTRY_PRO": {
        "name": "산업 PRO", "monthly": 249000,
        "sector": "INDUSTRY", "tier": 3, "is_custom": False,
    },
    "INDUSTRY_CUSTOM_V2": {
        "name": "산업 CUSTOM", "monthly": 0,
        "sector": "INDUSTRY", "tier": 4, "is_custom": True,
    },
    # BUILDING
    "BUILDING_BASIC": {
        "name": "건물 BASIC", "monthly": 59000,
        "sector": "BUILDING", "tier": 1, "is_custom": False,
    },
    "BUILDING_STANDARD": {
        "name": "건물 STANDARD", "monthly": 145000,
        "sector": "BUILDING", "tier": 2, "is_custom": False,
    },
    "BUILDING_CUSTOM": {
        "name": "건물 CUSTOM", "monthly": 249000,
        "sector": "BUILDING", "tier": 3, "is_custom": False,
    },
    # CONSTRUCTION
    "CONSTRUCTION_STANDARD_V2": {
        "name": "건설 STANDARD", "monthly": 145000,
        "sector": "CONSTRUCTION", "tier": 1, "is_custom": False,
    },
    "CONSTRUCTION_PREMIUM_V2": {
        "name": "건설 PREMIUM", "monthly": 385000,
        "sector": "CONSTRUCTION", "tier": 2, "is_custom": False,
    },
    "CONSTRUCTION_CUSTOM_V2": {
        "name": "건설 CUSTOM", "monthly": 0,
        "sector": "CONSTRUCTION", "tier": 3, "is_custom": True,
    },
}

# 섹터별 플랜 코드 순서 (tier 오름차순)
_SECTOR_PLANS: dict[str, list[str]] = {
    "INDUSTRY":     ["INDUSTRY_STARTER_V2", "INDUSTRY_BUSINESS_V2", "INDUSTRY_PRO", "INDUSTRY_CUSTOM_V2"],
    "BUILDING":     ["BUILDING_BASIC", "BUILDING_STANDARD", "BUILDING_CUSTOM"],
    "CONSTRUCTION": ["CONSTRUCTION_STANDARD_V2", "CONSTRUCTION_PREMIUM_V2", "CONSTRUCTION_CUSTOM_V2"],
}


# ─────────────────────────────────────────────────────────────────────────────
# 추천 로직
# ─────────────────────────────────────────────────────────────────────────────

def _effective_obligation_count(rd: dict, rule_count: int) -> int:
    """
    의무 수 추출.
    obligations 배열 우선, 비어있으면 rule_count로 대체.
    """
    obl = rd.get("obligations") or []
    if isinstance(obl, list) and len(obl) > 0:
        return len(obl)
    # rule_count fallback (obligations 미생성 stage 1/4 대응)
    return rule_count or 0


def _recommend_industry(
    severity: str, obl_cnt: int, workers: int
) -> tuple[str, list[str]]:
    """
    INDUSTRY 추천 로직.
    반환: (plan_code, reasons[])
    우선순위: severity > obl_cnt > workers
    """
    # CUSTOM: 작업자 500명 초과
    if workers > 500:
        return "INDUSTRY_CUSTOM_V2", [
            f"작업자 {workers}명 — 대규모 사업장으로 맞춤 견적이 필요합니다",
            "전담 TAI 컨설턴트가 최적 구성을 안내드립니다",
        ]

    # PRO: CRITICAL 또는 의무 150건 초과 또는 작업자 200명 초과
    if severity == "CRITICAL" or obl_cnt > 150 or workers > 200:
        reasons = []
        if severity == "CRITICAL":
            reasons.append("위험도 CRITICAL — 중대재해처벌법 대응을 위한 전사적 관리가 필요합니다")
        if obl_cnt > 150:
            reasons.append(f"법적 의무 {obl_cnt}건 — 150건 초과로 PRO 플랜의 전수 관리가 필요합니다")
        if workers > 200:
            reasons.append(f"작업자 {workers}명 — 200인 초과 사업장 전담 기능이 포함됩니다")
        reasons.append("무제한 설비 등록 + API 연동 + 전담 지원 포함")
        return "INDUSTRY_PRO", reasons[:4]

    # BUSINESS: MEDIUM/HIGH 또는 의무 50~150건
    if severity in ("MEDIUM", "HIGH") or 50 <= obl_cnt <= 150:
        reasons = []
        if severity in ("MEDIUM", "HIGH"):
            reasons.append(f"위험도 {severity} — 체계적인 점검 일정 자동화가 효과적입니다")
        if obl_cnt >= 50:
            reasons.append(f"법적 의무 {obl_cnt}건 — BUSINESS 플랜의 자동 일정 생성으로 누락 방지")
        reasons.append("작업 분산 배치 + 지연 알림 + 월간 리포트 포함")
        return "INDUSTRY_BUSINESS_V2", reasons[:4]

    # STARTER: LOW + 의무 50건 미만 + 작업자 50명 미만
    reasons = ["위험도 LOW — 기본 점검 관리로 법적 의무를 충족할 수 있습니다"]
    if obl_cnt < 50:
        reasons.append(f"법적 의무 {obl_cnt}건 — STARTER로 충분히 관리 가능합니다")
    if workers < 50:
        reasons.append(f"작업자 {workers}명 — 소규모 사업장에 최적화된 요금제입니다")
    return "INDUSTRY_STARTER_V2", reasons[:4]


def _recommend_building(
    severity: str, obl_cnt: int, workers: int
) -> tuple[str, list[str]]:
    """BUILDING 추천 로직."""
    # CUSTOM: CRITICAL 또는 의무 100건 초과
    if severity == "CRITICAL" or obl_cnt > 100:
        reasons = []
        if severity == "CRITICAL":
            reasons.append("위험도 CRITICAL — 복합 건물 전수 점검 관리가 필요합니다")
        if obl_cnt > 100:
            reasons.append(f"법적 의무 {obl_cnt}건 — CUSTOM 플랜의 무제한 점검 설정이 필요합니다")
        reasons.append("소방·전기·승강기 통합 관리 + 전담 지원 포함")
        return "BUILDING_CUSTOM", reasons[:4]

    # STANDARD: MEDIUM/HIGH 또는 의무 30~100건
    if severity in ("MEDIUM", "HIGH") or 30 <= obl_cnt <= 100:
        reasons = []
        if severity in ("MEDIUM", "HIGH"):
            reasons.append(f"위험도 {severity} — 정기 점검 자동화로 관리 누락을 방지합니다")
        if obl_cnt >= 30:
            reasons.append(f"법적 의무 {obl_cnt}건 — STANDARD 플랜으로 체계적 관리 가능")
        reasons.append("점검 일정 자동 생성 + 작업 배분 + 리포트 포함")
        return "BUILDING_STANDARD", reasons[:4]

    # BASIC
    reasons = ["위험도 LOW — 기본 점검 관리로 법적 의무를 충족할 수 있습니다"]
    if workers < 30:
        reasons.append(f"관리 인원 {workers}명 — 소규모 시설에 최적화된 요금제입니다")
    reasons.append("핵심 점검 항목 관리 + 법령 변경 알림 포함")
    return "BUILDING_BASIC", reasons[:4]


def _recommend_construction(
    severity: str, obl_cnt: int, workers: int
) -> tuple[str, list[str]]:
    """CONSTRUCTION 추천 로직."""
    # CUSTOM: 작업자 300명 초과
    if workers > 300:
        return "CONSTRUCTION_CUSTOM_V2", [
            f"현장 작업자 {workers}명 — 대형 현장 맞춤 구성이 필요합니다",
            "다현장 통합 관리 + 전담 TAI 컨설턴트 지원",
        ]

    # PREMIUM: CRITICAL/HIGH 또는 의무 80건 초과
    if severity in ("CRITICAL", "HIGH") or obl_cnt > 80:
        reasons = []
        if severity in ("CRITICAL", "HIGH"):
            reasons.append(f"위험도 {severity} — 중대재해처벌법 대응 PTW·TBM 자동화가 필요합니다")
        if obl_cnt > 80:
            reasons.append(f"법적 의무 {obl_cnt}건 — 전수 관리를 위한 PREMIUM 플랜이 필요합니다")
        reasons.append("위험성평가 + PTW + TBM 자동생성 포함")
        return "CONSTRUCTION_PREMIUM_V2", reasons[:4]

    # STANDARD
    reasons = ["기본 안전 관리로 건설 현장 법적 의무를 충족할 수 있습니다"]
    if severity == "MEDIUM":
        reasons.append("위험도 MEDIUM — 점검 일정 자동화로 관리 효율을 높입니다")
    reasons.append("공종별 점검 + 작업중지 기상 연동 포함")
    return "CONSTRUCTION_STANDARD_V2", reasons[:4]


def _build_alternatives(sector: str, recommended_code: str) -> dict:
    """추천 플랜의 상위/하위 대안 반환."""
    plan_list = _SECTOR_PLANS.get(sector, [])
    idx = plan_list.index(recommended_code) if recommended_code in plan_list else -1

    lower = upper = None
    if idx > 0:
        code = plan_list[idx - 1]
        p = _PLANS[code]
        lower = {
            "plan_code": code,
            "plan_name": p["name"],
            "monthly":   p["monthly"],
            "note":      "기본 기능 위주로 비용을 줄이고 싶다면",
        }
    if idx >= 0 and idx < len(plan_list) - 1:
        code = plan_list[idx + 1]
        p = _PLANS[code]
        upper = {
            "plan_code": code,
            "plan_name": p["name"],
            "monthly":   p["monthly"] if not p["is_custom"] else None,
            "note":      "더 많은 기능과 지원이 필요하다면",
        }
    return {"lower": lower, "upper": upper}


def _build_comparison(recommended_code: str, penalty_risk_krw: int) -> dict:
    """
    과태료 위험 vs TAI Safe 연간 비용 비교.
    """
    plan = _PLANS.get(recommended_code, {})
    monthly = plan.get("monthly", 0)
    annual  = monthly * 12

    if penalty_risk_krw > 0 and annual > 0:
        ratio = round(penalty_risk_krw / annual, 1)
        savings = penalty_risk_krw - annual
    else:
        ratio   = None
        savings = None

    return {
        "annual_penalty_risk_krw": penalty_risk_krw,
        "tai_safe_annual_krw":     annual,
        "tai_safe_monthly_krw":    monthly,
        "risk_reduction_ratio":    ratio,          # 과태료/연간비용 = X배
        "estimated_savings_krw":   savings,
        "note": (
            f"TAI Safe 연간 {annual:,}원으로 최대 {penalty_risk_krw:,}원 과태료 위험을 관리합니다"
            if annual > 0 and penalty_risk_krw > 0
            else "법령 진단 완료 후 정확한 비교가 가능합니다"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 엔드포인트 (콘크리트 경로 → legal_engine의 /{diagnosis_id} 보다 먼저 선언)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{diagnosis_id}/recommend-plan")
def recommend_plan(diagnosis_id: str):
    """
    진단 결과 기반 SaaS 플랜 자동 추천.

    AI 없이 severity / obligations 수 / 작업자 수 조건 분기만으로 추천.
    TAI 철학: 데이터 → 엔진 판단 → 자동 실행.
    """
    sb = get_supabase()

    # 1. 진단 레코드 조회
    diag_res = (
        sb.table("factory_diagnosis_results")
        .select("id, factory_id, sector, diagnosis_stage, rule_count, result_data")
        .eq("id", diagnosis_id)
        .limit(1)
        .execute()
    )
    if not diag_res.data:
        raise HTTPException(status_code=404, detail="진단 레코드를 찾을 수 없습니다.")

    diag = diag_res.data[0]
    rd: dict = diag.get("result_data") or {}
    sector: str = (diag.get("sector") or "").upper()
    rule_count: int = diag.get("rule_count") or 0

    # 2. 공장 정보 조회 (작업자 수)
    factory: dict = {}
    if diag.get("factory_id"):
        fac_res = (
            sb.table("factories")
            .select("id, name, sector, employee_count, total_worker_count_calc")
            .eq("id", diag["factory_id"])
            .limit(1)
            .execute()
        )
        factory = fac_res.data[0] if fac_res.data else {}
        # sector 보정: factories.sector 우선
        if factory.get("sector"):
            sector = str(factory["sector"]).upper()

    # 3. 입력 변수 추출
    headline = rd.get("headline") or {}
    severity: str = str(headline.get("severity") or "LOW").upper()
    obl_cnt: int  = _effective_obligation_count(rd, rule_count)
    workers: int  = int(
        factory.get("total_worker_count_calc")
        or factory.get("employee_count")
        or 0
    )
    penalty_risk_krw: int = int(
        (rd.get("roi") or {}).get("annual_penalty_risk_krw") or 0
    )

    # 4. 섹터별 추천
    if sector == "INDUSTRY":
        plan_code, reasons = _recommend_industry(severity, obl_cnt, workers)
    elif sector == "BUILDING":
        plan_code, reasons = _recommend_building(severity, obl_cnt, workers)
    elif sector == "CONSTRUCTION":
        plan_code, reasons = _recommend_construction(severity, obl_cnt, workers)
    else:
        # 알 수 없는 섹터 — 중간 플랜 기본 반환
        raise HTTPException(
            status_code=422,
            detail=f"지원하지 않는 섹터입니다: '{sector}'. INDUSTRY / BUILDING / CONSTRUCTION 중 하나여야 합니다.",
        )

    plan_info = _PLANS[plan_code]

    # 5. 응답 조립
    return {
        "status": "success",
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
            "plan_code":  plan_code,
            "plan_name":  plan_info["name"],
            "monthly_krw": plan_info["monthly"] if not plan_info["is_custom"] else None,
            "is_custom":  plan_info["is_custom"],
            "pricing_note": "맞춤 견적 문의" if plan_info["is_custom"] else f"월 {plan_info['monthly']:,}원 (부가세 별도)",
        },
        "reasons":      reasons,
        "alternatives": _build_alternatives(sector, plan_code),
        "comparison":   _build_comparison(plan_code, penalty_risk_krw),
        "factory": {
            "id":   factory.get("id"),
            "name": factory.get("name"),
        },
        "cta": {
            "primary":   {"label": "지금 시작하기",       "action": "go_pricing", "plan_code": plan_code},
            "secondary": {"label": "전체 요금제 비교하기", "action": "go_pricing_all"},
        },
    }
