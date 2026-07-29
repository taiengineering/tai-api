from __future__ import annotations

from datetime import date, timedelta
from typing import List, Optional

from dateutil.relativedelta import relativedelta

VERSION = "2.1.0"

# v2.1.0 (2026-07-30, Goal G-ms6az4y8-b88c4a)
#   다음 점검일 휴무 보정 추가 — adjust_planned_for_holiday.
#   inspection_sets.holiday_process_type 은 종전부터 있었으나 참조하는 휴무 데이터가
#   없어 동작하지 않는 설정이었다. 공용 휴무 캘린더(services/holiday_svc, org_holiday)가
#   생기면서 실제로 동작한다. 값이 BEFORE/AFTER 가 아니면 보정하지 않으므로
#   기존 세트의 동작은 바뀌지 않는다.

DELTA_MAP = {
    "day":       lambda v: relativedelta(days=v),
    "week":      lambda v: relativedelta(weeks=v),
    "month":     lambda v: relativedelta(months=v),
    "quarter":   lambda v: relativedelta(months=3 * v),
    "half_year": lambda v: relativedelta(months=6 * v),
    "year":      lambda v: relativedelta(years=v),
}
REPEAT_TYPE_MAP = {
    "day": "daily", "week": "weekly", "month": "monthly",
    "quarter": "quarterly", "half_year": "half_yearly", "year": "yearly",
}
UNIT_KO = {"year": "년", "month": "개월", "quarter": "분기", "half_year": "반기"}
CHECK_TYPE_MAP = {
    "INSPECT": "PASS_FAIL", "APPOINT": "CHECK", "REPORT": "DATE",
    "ACTION": "PASS_FAIL", "NOTIFY": "DATE", "DOCUMENT": "CHECK",
    "BEFORE_WORK": "PASS_FAIL", "OTHER": "PASS_FAIL",
}


def _get_delta(cycle_unit: str, cycle_value: int):
    fn = DELTA_MAP.get(cycle_unit.lower())
    return fn(cycle_value) if fn else relativedelta(years=cycle_value)


def _next_planned_from(base: date, cycle_unit: str, cycle_value: int) -> date:
    delta  = _get_delta(cycle_unit, cycle_value)
    cursor = base + delta
    today  = date.today()
    while cursor < today:
        cursor += delta
    return cursor


# public alias — inspection_schedule.py 등 외부에서 import 가능
next_planned_from = _next_planned_from


def adjust_planned_for_holiday(
    planned: Optional[date],
    company_id: Optional[str],
    factory_id: Optional[str],
    holiday_process_type: Optional[str],
) -> Optional[date]:
    """산출된 예정일이 휴무일(주말·법정공휴일·사업장 휴무)이면 작업일로 옮긴다.

    holiday_process_type:
      BEFORE → 직전 작업일로 앞당김
      AFTER  → 직후 작업일로 미룸
      그 외(None 포함) → 보정하지 않음(종전 동작 그대로)

    휴무 데이터는 공용 모듈 services/holiday_svc(org_holiday)에서 읽는다.
    조회 실패(테이블 미적용 등) 시 주말만 회피한다.
    """
    if planned is None:
        return None
    step = {"BEFORE": -1, "AFTER": 1}.get((holiday_process_type or "").upper())
    if step is None:
        return planned

    from services.holiday_svc import holiday_map, is_workday   # 지연 임포트 — 순환 참조 방지

    window_from = (planned - timedelta(days=45)).isoformat()
    window_to = (planned + timedelta(days=45)).isoformat()
    try:
        hdays = set(holiday_map(company_id, factory_id, window_from, window_to).keys())
    except Exception:
        hdays = set()

    cursor = planned
    guard = 0
    while not is_workday(cursor, hdays) and guard < 60:
        cursor += timedelta(days=step)
        guard += 1
    return cursor


def _build_next_schedule_row(iset: dict, base: date):
    cycle_unit  = (iset.get("cycle_unit") or "year").lower()
    cycle_value = int(iset.get("cycle_value") or 1)
    planned     = _next_planned_from(base, cycle_unit, cycle_value)
    planned     = adjust_planned_for_holiday(
        planned, iset.get("company_id"), iset.get("factory_id"),
        iset.get("holiday_process_type"))
    repeat_type = REPEAT_TYPE_MAP.get(cycle_unit, "yearly")
    source_type = "LEGAL" if iset.get("source") == "LEGAL_ENGINE" else "MANUAL"
    return {
        "factory_id":        iset["factory_id"],
        "company_id":        iset.get("company_id"),
        "inspection_set_id": iset["id"],
        "planned_date":      planned.isoformat(),
        "start_date":        planned.isoformat(),
        "end_date":          planned.isoformat(),
        "repeat_type":       repeat_type,
        "repeat_interval":   cycle_value,
        "status_code":       "SCHEDULED",
        "source_type":       source_type,
        "obligation_type":   iset.get("inspection_category") or "GENERAL",
        "summary":           iset.get("inspection_set_name") or "",
        "active_yn":         True,
        "assigned_user_id":  None,
    }, planned


def _build_items_for_set(iset: dict, rule: dict) -> List[dict]:
    obligation_type = (rule.get("obligation_type") or "INSPECT").upper()
    check_type  = CHECK_TYPE_MAP.get(obligation_type, "PASS_FAIL")
    summary     = (rule.get("obligation_summary") or rule.get("remarks") or "").strip()
    law_name    = (rule.get("law_name") or "").strip()
    law_article = (rule.get("law_article") or "").strip()
    return [{
        "inspection_set_id": iset["id"],
        "item_seq":   1,
        "item_name":  summary or f"{law_name} {law_article}".strip() or "점검 항목",
        "description": f"[{check_type}] {law_name} {law_article}".strip(),
        "is_required": True,
        "is_active":   True,
    }]


def _meets_4_conditions(iset: dict) -> bool:
    """
    LAW_ENGINE 스케줄 생성 4조건:
    1. schedule_anchor_date (기준일)
    2. cycle_unit (주기)
    3. assignee_user_id (담당자)
    4. description 또는 legal_rule_code/legal_rule_id (의무내용)
    """
    has_anchor   = bool(iset.get("schedule_anchor_date"))
    has_cycle    = bool(iset.get("cycle_unit"))
    has_assignee = bool(iset.get("assignee_user_id"))
    has_content  = (
        bool((iset.get("description") or "").strip())
        or bool(iset.get("legal_rule_code"))
        or bool(iset.get("legal_rule_id"))
    )
    return has_anchor and has_cycle and has_assignee and has_content


def _build_law_engine_row(iset: dict) -> dict:
    """4조건 충족 inspection_set → LAW_ENGINE work_schedule 행"""
    anchor  = date.fromisoformat(iset["schedule_anchor_date"])
    planned = _next_planned_from(anchor, iset["cycle_unit"], int(iset.get("cycle_value") or 1))
    planned = adjust_planned_for_holiday(
        planned, iset.get("company_id"), iset.get("factory_id"),
        iset.get("holiday_process_type"))
    return {
        "factory_id":        iset["factory_id"],
        "company_id":        iset.get("company_id"),
        "inspection_set_id": iset["id"],
        "assigned_user_id":  iset["assignee_user_id"],
        "source_type":       "LAW_ENGINE",
        "description":       (iset.get("description") or iset.get("law_name") or "").strip(),
        "obligation_type":   iset.get("inspection_category") or "INSPECT",
        "law_name":          iset.get("law_name") or "",
        "law_article":       iset.get("law_article") or "",
        "planned_date":      planned.isoformat(),
        "status_code":       "PENDING",
        "active_yn":         True,
        "rule_code":         iset.get("legal_rule_code") or iset.get("legal_rule_id") or "",
    }
