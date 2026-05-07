"""
services/roi_calculator.py — v1.0.0

BE-07: ROI 계산 서비스

로직:
  penalty_max_krw  = result_data.exposure.penalty_max_krw
                     OR obligations의 penalty.krw 합산
                     OR rule_count × 3,000,000원 (보수적 추정, 명시)
  annual_cost_krw  = 권장플랜 monthly_base_fee × 12
  payback_days     = ceil(annual_cost / (penalty_max / 365))
  risk_reduction_% = obligations 중 action_url 있는 항목 / 전체 × 100

주의:
  실제 penalty 깰거 없는 숫자 생성 금지.
  obligations 목록 기반 쫬소만 사용.
"""
from __future__ import annotations
import math
from typing import Any, Optional

# ── 플랜별 월 요금 (현행 price_saas_plan DB 기준) ───────────────────────────
PLAN_MONTHLY_FEE = {
    # INDUSTRIAL
    "STARTER":    79_000,
    "BUSINESS":  149_000,
    "ENTERPRISE": 249_000,  # PRO 플랜 249K 사용
    # BUILDING
    "BUILDING_BASIC":     59_000,
    "BUILDING_STANDARD":  99_000,
    # CONSTRUCTION
    "CONSTRUCTION_STANDARD":  199_000,
    "CONSTRUCTION_PREMIUM":   399_000,
}

PLAN_FEATURES = {
    "STARTER":   ["자동일정", "D-3 알림", "점검 체크리스트"],
    "BUSINESS":  ["자동일정", "D-3 알림", "담당자 라우팅", "업무현황 대시보드"],
    "ENTERPRISE": ["자동일정", "D-3 알림", "담당자 라우팅", "업무현황 대시보드", "전사 대시보드", "API 연동"],
    "BUILDING_BASIC":    ["자동일정", "D-3 알림"],
    "BUILDING_STANDARD": ["자동일정", "D-3 알림", "담당자 라우팅", "대시보드"],
    "CONSTRUCTION_STANDARD": ["자동일정", "D-3 알림", "TBM 통합"],
    "CONSTRUCTION_PREMIUM":  ["자동일정", "D-3 알림", "TBM 통합", "담당자 라우팅", "대시보드"],
}

# 평균 안전법 과태료 (조항당 보수적 상한, obligations 쫐리 시 사용)
_DEFAULT_PENALTY_PER_OBLIGATION = 3_000_000  # 300만원/건


def infer_plan(
    sector: str,
    employee_count: Optional[int],
    construction_amount_krw: Optional[float],
    total_floor_area: Optional[float] = None,
) -> str:
    """
    시설 정보를 기반으로 권장 플랜을 추론.

    권장 로직 (workorder-be07 확정값):
      BUILDING:
        3,000㎡ 미만 + 10명 미만 → BUILDING_BASIC
        그 외            → BUILDING_STANDARD
      INDUSTRIAL:
        <100명        → STARTER
        100~300명    → BUSINESS
        300명+        → ENTERPRISE
      CONSTRUCTION:
        <50억원      → CONSTRUCTION_STANDARD
        50억+          → CONSTRUCTION_PREMIUM
    """
    s = (sector or "").upper()
    emp = employee_count or 0
    amt = construction_amount_krw or 0.0
    area = total_floor_area or 0.0

    if s == "BUILDING":
        if area < 3000 and emp < 10:
            return "BUILDING_BASIC"
        return "BUILDING_STANDARD"

    if s == "INDUSTRIAL" or s == "INDUSTRY":
        if emp < 100:
            return "STARTER"
        if emp < 300:
            return "BUSINESS"
        return "ENTERPRISE"

    if s == "CONSTRUCTION":
        fifty_eok = 5_000_000_000  # 50억원
        if amt < fifty_eok:
            return "CONSTRUCTION_STANDARD"
        return "CONSTRUCTION_PREMIUM"

    # fallback
    return "STARTER"


def _extract_penalty_max(result_data: dict, rule_count: int) -> tuple[int, str]:
    """
    제공된 result_data에서 penalty_max_krw 추출.

    Returns:
        (penalty_max_krw, source)  — source: 'exposure' | 'obligations_sum' | 'rule_count_estimate'
    """
    # 1순위: exposure.penalty_max_krw 직접 있으면 사용
    exposure = result_data.get("exposure") or {}
    if isinstance(exposure, dict) and exposure.get("penalty_max_krw"):
        try:
            return int(exposure["penalty_max_krw"]), "exposure"
        except (TypeError, ValueError):
            pass

    # 2순위: obligations[].penalty.krw 합산
    obligations = result_data.get("obligations") or []
    if isinstance(obligations, list) and obligations:
        total = 0
        for obl in obligations:
            if not isinstance(obl, dict):
                continue
            penalty = obl.get("penalty") or {}
            if isinstance(penalty, dict):
                try:
                    krw = int(penalty.get("krw") or 0)
                    total += krw
                except (TypeError, ValueError):
                    pass
        if total > 0:
            return total, "obligations_sum"

    # 3순위: rule_count × _DEFAULT_PENALTY_PER_OBLIGATION (보수적 추정)
    estimate = (rule_count or 1) * _DEFAULT_PENALTY_PER_OBLIGATION
    return estimate, "rule_count_estimate"


def _count_critical_items(obligations: list) -> int:
    return sum(
        1 for o in (obligations or [])
        if isinstance(o, dict) and (o.get("risk_level") or "").upper() == "CRITICAL"
    )


def _count_actionable(obligations: list) -> int:
    """action_url 또는 쫼소적 주의가 있는 항목 수."""
    if not obligations:
        return 0
    actionable = sum(
        1 for o in obligations
        if isinstance(o, dict) and (
            o.get("action_url") or
            (o.get("risk_level") or "").upper() in ("CRITICAL", "HIGH")
        )
    )
    return actionable


def calculate_roi(
    sector: str,
    employee_count: Optional[int],
    construction_amount_krw: Optional[float],
    result_data: dict,
    rule_count: int,
    total_floor_area: Optional[float] = None,
) -> dict:
    """
    단일 진단 결과를 받아 ROI dict를 반환.
    이 함수는 result_data.roi에 저장되고, FN-04가 에 읽어감.
    """
    plan_code = infer_plan(sector, employee_count, construction_amount_krw, total_floor_area)
    monthly_fee = PLAN_MONTHLY_FEE.get(plan_code, 79_000)
    annual_cost = monthly_fee * 12

    penalty_max, penalty_source = _extract_penalty_max(result_data, rule_count)

    obligations: list[Any] = result_data.get("obligations") or []
    total_obls   = len(obligations)
    actionable   = _count_actionable(obligations)
    critical_cnt = _count_critical_items(obligations)

    # risk_reduction_percent: actionable / total × 100 (obligations 없으면 레거시 rule_count 비례)
    if total_obls > 0:
        risk_reduction = round(actionable / total_obls * 100, 1)
    elif rule_count > 0:
        # legacy: obligations 없으나 rule_count 존재 → 보수적 70%
        risk_reduction = 70.0
    else:
        risk_reduction = 0.0

    # residual_risk: 저감되지 않는 리스크 (단순 차이)
    residual = int(penalty_max * (1 - risk_reduction / 100))

    # payback_days
    if penalty_max > 0:
        payback = math.ceil(annual_cost / (penalty_max / 365))
        payback = min(payback, 365)  # 최대 1년
    else:
        payback = 365

    saved = penalty_max - annual_cost
    multiplier = round(penalty_max / annual_cost, 1) if annual_cost > 0 else 0

    return {
        "plan_code":               plan_code,
        "plan_monthly_fee":        monthly_fee,
        "annual_penalty_risk_krw": penalty_max,
        "penalty_source":          penalty_source,  # 사용된 추정 방식 명시
        "tai_safe_annual_cost_krw": annual_cost,
        "payback_days":            payback,
        "risk_reduction_percent":  risk_reduction,
        "residual_risk_krw":       max(0, residual),
        "saved_value_krw":         max(0, saved),
        "multiplier":              multiplier,
        "included_features":       PLAN_FEATURES.get(plan_code, []),
    }


def build_full_roi_response(
    factory: dict,
    diagnosis: dict,
    result_data: dict,
) -> dict:
    """
    GET /diagnosis/{id}/roi 응답 전체 dict 구성.
    factory, diagnosis 레코드와 result_data를 받아 완성된 응답 반환.
    """
    sector     = factory.get("sector") or "BUILDING"
    emp_count  = factory.get("employee_count")
    const_amt  = factory.get("construction_amount")
    const_krw  = None
    if const_amt is not None:
        try: const_krw = float(const_amt)
        except (TypeError, ValueError): pass

    # factories에 도면적 필드가 없을 수 있으니 result_data에서 시도
    floor_area = None
    fc = result_data.get("facility_context") or {}
    if isinstance(fc, dict):
        floor_area = fc.get("total_floor_area") or fc.get("building_area")
        try: floor_area = float(floor_area) if floor_area is not None else None
        except (TypeError, ValueError): floor_area = None

    rule_count = diagnosis.get("rule_count") or 0
    roi = calculate_roi(sector, emp_count, const_krw, result_data, rule_count, floor_area)

    obligations = result_data.get("obligations") or []
    critical_cnt = _count_critical_items(obligations)

    penalty_max = roi["annual_penalty_risk_krw"]
    plan_code   = roi["plan_code"]
    monthly_fee = roi["plan_monthly_fee"]
    annual_cost = roi["tai_safe_annual_cost_krw"]

    return {
        "diagnosis_id": str(diagnosis.get("id", "")),
        "factory": {
            "id":             str(factory.get("id", "")),
            "name":           factory.get("name") or "",
            "sector":         sector,
            "employee_count": emp_count,
        },
        "current_exposure": {
            "penalty_max_krw": penalty_max,
            "penalty_source":  roi["penalty_source"],
            "critical_items":  critical_cnt,
            "missed_items":    len(obligations),
        },
        "tai_safe_plan": {
            "recommended_plan":  plan_code,
            "monthly_fee_krw":   monthly_fee,
            "annual_cost_krw":   annual_cost,
            "included_features": roi["included_features"],
        },
        "comparison": {
            "risk_reduction_percent": roi["risk_reduction_percent"],
            "payback_days":           roi["payback_days"],
            "implementation_weeks":   2,
            "residual_risk_krw":      roi["residual_risk_krw"],
        },
        "visual_hint": {
            "before_value":  penalty_max,
            "after_value":   annual_cost,
            "saved_value":   roi["saved_value_krw"],
            "multiplier":    roi["multiplier"],
        },
    }
