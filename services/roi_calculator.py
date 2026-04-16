"""
services/roi_calculator.py — v1.0.0

BE-07: ROI 계산 서비스

로직 원칙:
  - 군거 없는 숫자 생성 금지 (반드시 result_data.obligations 기반)
  - exposure.penalty_max_krw 없으면 obligations.penalty.krw 합산
  - obligations 없으면 rule_count xd7 3,000,000원 (3백만/건 산안법 과태료 기준)
  - 비용: 권장 플랜의 monthly_base_fee xd7 12
  - 소개비/크레딧 용어 일체 금지
"""
from __future__ import annotations
import math
from typing import Any, Optional

# ── 플랜별 월 요금 (실제 DB 값 기준, 단위: 원/월) ──
PLAN_MONTHLY_FEE = {
    # BUILDING
    "BUILDING_BASIC":    59_000,
    "BUILDING_STANDARD": 99_000,
    # INDUSTRY
    "INDUSTRY_STARTER":  79_000,
    "INDUSTRY_BUSINESS": 149_000,
    "INDUSTRY_PRO":      249_000,
    # CONSTRUCTION
    "CONSTRUCTION_STANDARD": 199_000,
    "CONSTRUCTION_PREMIUM":  399_000,
}

PLAN_FEATURES = {
    "BUILDING_BASIC":         ["자동일정", "D-3 알림", "점검 체크리스트"],
    "BUILDING_STANDARD":      ["자동일정", "D-3 알림", "점검 체크리스트", "서류서식 자동생성"],
    "INDUSTRY_STARTER":       ["자동일정", "D-3 알림", "점검 체크리스트"],
    "INDUSTRY_BUSINESS":      ["자동일정", "D-3 알림", "점검 체크리스트", "담당자 자동배정", "서류서식 자동생성"],
    "INDUSTRY_PRO":           ["자동일정", "D-3 알림", "점검 체크리스트", "담당자 자동배정", "서류서식 자동생성", "운영 지표 분석"],
    "CONSTRUCTION_STANDARD":  ["자동일정", "D-3 알림", "점검 체크리스트", "TBM 관리"],
    "CONSTRUCTION_PREMIUM":   ["자동일정", "D-3 알림", "점검 체크리스트", "TBM 관리", "담당자 자동배정", "서류서식 자동생성"],
}

# 꿀액 가정치 (오뱤드 없는 경우): 산안법 과태료 3백만원/건
FALLBACK_PENALTY_PER_RULE = 3_000_000


def infer_plan(sector: str, employee_count: int, construction_amount: Optional[float] = None,
               total_floor_area: Optional[float] = None) -> str:
    """
    시설 정보 기반 권장 플랜 추론.

    BUILDING:
      3,000㎡ 미만 + 10명 미만  → BUILDING_BASIC
      그 외                       → BUILDING_STANDARD

    INDUSTRY:
      100명 미만 → INDUSTRY_STARTER
      100~299명 → INDUSTRY_BUSINESS
      300명 이상 → INDUSTRY_PRO

    CONSTRUCTION:
      50억원 미만 → CONSTRUCTION_STANDARD
      50억원 이상 → CONSTRUCTION_PREMIUM
    """
    s = (sector or "").upper()

    if s == "BUILDING":
        area = total_floor_area or 0
        emp  = employee_count or 0
        if area < 3000 and emp < 10:
            return "BUILDING_BASIC"
        return "BUILDING_STANDARD"

    elif s == "INDUSTRY":
        emp = employee_count or 0
        if emp < 100:
            return "INDUSTRY_STARTER"
        elif emp < 300:
            return "INDUSTRY_BUSINESS"
        return "INDUSTRY_PRO"

    elif s == "CONSTRUCTION":
        # construction_amount 단위: 원 (factories.construction_amount)
        amount_eok = (construction_amount or 0) / 100_000_000
        if amount_eok < 50:
            return "CONSTRUCTION_STANDARD"
        return "CONSTRUCTION_PREMIUM"

    # fallback
    return "INDUSTRY_STARTER"


def estimate_penalty_max(result_data: dict, rule_count: int) -> int:
    """
    최대 과태료 노출 추정.

    1순위: result_data.exposure.penalty_max_krw
    2순위: obligations 내 penalty.krw 합산
    3순위: rule_count xd7 FALLBACK_PENALTY_PER_RULE
    """
    # 1순위
    exposure = result_data.get("exposure") or {}
    if exposure.get("penalty_max_krw"):
        try:
            return int(exposure["penalty_max_krw"])
        except (TypeError, ValueError):
            pass

    # 2순위: obligations도 함쳐 여러 legacy 키 탄색
    total = 0
    for key in ("obligations", "key_obligations", "inspection_required",
                "action_required", "appointment_required", "report_required"):
        for obl in (result_data.get(key) or []):
            if isinstance(obl, dict):
                pen = obl.get("penalty") or {}
                if isinstance(pen, dict):
                    try:
                        total += int(pen.get("krw") or 0)
                    except (TypeError, ValueError):
                        pass
                elif isinstance(pen, (int, float)):
                    total += int(pen)
    if total > 0:
        return total

    # 3순위: 산안법 추정
    return (rule_count or 0) * FALLBACK_PENALTY_PER_RULE


def count_actionable(result_data: dict) -> int:
    """
    action_url 있는 obligation 수 (동작 가능한 항목 수)
    """
    count = 0
    for key in ("obligations", "key_obligations"):
        for obl in (result_data.get(key) or []):
            if isinstance(obl, dict) and obl.get("action_url"):
                count += 1
    return count


def calculate_roi(sector: str, employee_count: int,
                  result_data: dict, rule_count: int,
                  construction_amount: Optional[float] = None,
                  total_floor_area: Optional[float] = None) -> dict:
    """
    ROI 단일 진입점 계산.

    Returns: result_data.roi 햤더에 저장할 dict
    """
    plan_code   = infer_plan(sector, employee_count, construction_amount, total_floor_area)
    monthly_fee = PLAN_MONTHLY_FEE.get(plan_code, 79_000)
    annual_cost = monthly_fee * 12

    penalty_max = estimate_penalty_max(result_data, rule_count)

    # 리스크 감축률: obligations 중 action_url 있는 비율
    total_obls      = sum(
        len(result_data.get(k) or [])
        for k in ("obligations", "key_obligations", "inspection_required",
                  "action_required", "appointment_required")
    )
    actionable      = count_actionable(result_data)
    # action_url 미정의 legacy는 rule_count 기준 80% 감축 가정
    if total_obls > 0:
        risk_reduction = round(actionable / total_obls * 100)
    elif rule_count > 0:
        risk_reduction = 80  # 레거시 산안법 기준
    else:
        risk_reduction = 0

    residual_risk   = int(penalty_max * (1 - risk_reduction / 100))

    # 회수기간: ceil(annual_cost / (penalty_max / 365))
    if penalty_max > 0:
        payback_days = math.ceil(annual_cost / (penalty_max / 365))
        payback_days = min(payback_days, 365)  # 1년 상한
    else:
        payback_days = 365

    return {
        "annual_penalty_risk_krw":  penalty_max,
        "tai_safe_annual_cost_krw": annual_cost,
        "payback_days":            payback_days,
        "risk_reduction_percent":  risk_reduction,
        "recommended_plan":        plan_code,
        "residual_risk_krw":       residual_risk,
        "_calc_basis":             (
            "exposure_field" if (result_data.get("exposure") or {}).get("penalty_max_krw")
            else "obligations_penalty" if total_obls > 0
            else "rule_count_fallback"
        ),
    }


def build_roi_response(factory: dict, diag: dict) -> dict:
    """
    API 응답 전체 구조 조립.

    factory: factories 테이블 레코드
    diag:    factory_diagnosis_results 테이블 레코드
    """
    result_data = diag.get("result_data") or {}
    rule_count  = diag.get("rule_count") or 0
    sector      = factory.get("sector") or "BUILDING"
    emp_count   = int(factory.get("employee_count") or 0)

    construction_amount = None
    try:
        ca = factory.get("construction_amount")
        if ca: construction_amount = float(ca)
    except (TypeError, ValueError):
        pass

    roi = calculate_roi(
        sector=sector,
        employee_count=emp_count,
        result_data=result_data,
        rule_count=rule_count,
        construction_amount=construction_amount,
    )

    plan_code   = roi["recommended_plan"]
    monthly_fee = PLAN_MONTHLY_FEE.get(plan_code, 79_000)
    annual_cost = roi["tai_safe_annual_cost_krw"]
    penalty_max = roi["annual_penalty_risk_krw"]

    # critical_items: result_data.risk_summary.critical 또는 obligations CRITICAL 수
    risk_sum    = result_data.get("risk_summary") or {}
    crit_count  = int(
        risk_sum.get("critical") or risk_sum.get("CRITICAL") or
        sum(1 for k in ("obligations", "key_obligations")
            for o in (result_data.get(k) or [])
            if isinstance(o, dict) and (o.get("risk_level") or "").upper() == "CRITICAL")
    )

    return {
        "factory": {
            "name":           factory.get("name"),
            "sector":         sector,
            "employee_count": emp_count,
        },
        "current_exposure": {
            "penalty_max_krw": penalty_max,
            "critical_items":  crit_count,
            "missed_items":    rule_count,
            "calc_basis":      roi["_calc_basis"],
        },
        "tai_safe_plan": {
            "recommended_plan":  plan_code,
            "monthly_cost_krw":  monthly_fee,
            "annual_cost_krw":   annual_cost,
            "included_features": PLAN_FEATURES.get(plan_code, ["자동일정", "D-3 알림"]),
        },
        "comparison": {
            "risk_reduction_percent": roi["risk_reduction_percent"],
            "payback_days":           roi["payback_days"],
            "implementation_weeks":   2,
            "residual_risk_krw":      roi["residual_risk_krw"],
        },
        "visual_hint": {
            "before_value": penalty_max,
            "after_value":  annual_cost,
            "saved_value":  max(penalty_max - annual_cost, 0),
            "multiplier":   round(penalty_max / annual_cost, 1) if annual_cost > 0 else 0,
        },
    }
