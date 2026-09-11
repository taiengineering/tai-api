"""services/inspection_sets_svc/operation_time_rule.py

WO-SAFE-OPERATION-TIME-BACKEND-V1-001 / PATCH-R1.

LEGAL_NORMALIZED_TIME ≠ OPERATION_TIME_RULE ≠ SCHEDULE.

- dedicated PATCH …/operation-time-rule = PERSIST OPERATION TRUTH ONLY.
- work_schedules mutation = 0 (daily generator owns materialization).
- EVERY → cycle_unit/value compatibility projection.
- WITHIN/BEFORE/UNTIL → cycle_* fake recurrence projection 금지.
- UNTIL → persist candidate · annual inference 0 · v1 NOT READY.
- event basis_date → last_inspection_date 자동 기록 0.
- schedule-start lock = 0 (세트는 수정 가능).
"""
from __future__ import annotations

import calendar
import re
from datetime import date
from typing import Any, Dict, Optional

from db.supabase_client import get_supabase
from schemas.inspection_sets import OperationTimeRuleBody
from services.inspection_sets_helpers import DELTA_MAP
from services.time import serialize_business_datetime, now_kst
from .errors import InspectionSetsSvcError

ALLOWED_SOURCES = frozenset({"LEGAL_DEFAULT", "USER_EDITED"})
ALLOWED_OPERATORS = frozenset({"EVERY", "WITHIN", "BEFORE", "UNTIL"})
ALLOWED_UNITS = frozenset(DELTA_MAP.keys())
_EXACT_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse_iso_date(raw: Optional[str], *, field: str) -> date:
    """Exact YYYY-MM-DD only. Reject datetime suffixes / slash / invalid calendar days."""
    if not isinstance(raw, str):
        raise InspectionSetsSvcError(422, f"{field} 는 YYYY-MM-DD 형식이어야 합니다.")
    s = raw.strip()
    if not _EXACT_ISO_DATE.fullmatch(s):
        raise InspectionSetsSvcError(422, f"{field} 는 YYYY-MM-DD 형식이어야 합니다.")
    try:
        return date.fromisoformat(s)
    except ValueError as e:
        raise InspectionSetsSvcError(422, f"{field} 는 YYYY-MM-DD 형식이어야 합니다.") from e


def _valid_month_day(month: int, day: int) -> bool:
    # leap-year ceiling so Feb 29 pattern is admissible as MD (year comes later).
    return 1 <= month <= 12 and 1 <= day <= calendar.monthrange(2024, month)[1]


def normalize_operation_time_rule(body: OperationTimeRuleBody) -> Dict[str, Any]:
    """Validate + return JSONB-ready rule dict (schedule side-effects 없음)."""
    if (body.version or "").strip() != "v1":
        raise InspectionSetsSvcError(422, "version 은 v1 이어야 합니다.")
    source = (body.source or "").strip().upper()
    if source not in ALLOWED_SOURCES:
        raise InspectionSetsSvcError(422, "source 는 LEGAL_DEFAULT 또는 USER_EDITED 여야 합니다.")
    op = (body.operator or "").strip().upper()
    if op not in ALLOWED_OPERATORS:
        raise InspectionSetsSvcError(422, "operator 는 EVERY/WITHIN/BEFORE/UNTIL 중 하나여야 합니다.")

    rule: Dict[str, Any] = {"version": "v1", "source": source, "operator": op}

    if op in ("EVERY", "WITHIN", "BEFORE"):
        unit_raw = body.unit
        unit = (unit_raw or "").strip().lower() if unit_raw is not None else ""
        val = body.value

        if op in ("EVERY", "WITHIN"):
            if val is None or isinstance(val, bool) or not isinstance(val, int) or val < 1:
                raise InspectionSetsSvcError(422, "value 는 1 이상의 정수여야 합니다.")
            if unit not in ALLOWED_UNITS:
                raise InspectionSetsSvcError(
                    422, "unit 은 day/week/month/quarter/half_year/year 중 하나여야 합니다."
                )
            if body.basis_date is None:
                raise InspectionSetsSvcError(422, "basis_date 는 YYYY-MM-DD 형식이어야 합니다.")
            basis = _parse_iso_date(body.basis_date, field="basis_date")
            rule["value"] = val
            rule["unit"] = unit
            rule["basis_date"] = basis.isoformat()
        else:  # BEFORE — draft may omit offset; daily generator waits until ready
            if val is not None:
                if isinstance(val, bool) or not isinstance(val, int) or val < 1:
                    raise InspectionSetsSvcError(422, "value 는 1 이상의 정수여야 합니다.")
                rule["value"] = val
            if unit_raw is not None and unit:
                if unit not in ALLOWED_UNITS:
                    raise InspectionSetsSvcError(
                        422, "unit 은 day/week/month/quarter/half_year/year 중 하나여야 합니다."
                    )
                rule["unit"] = unit
            if body.basis_date is not None:
                basis = _parse_iso_date(body.basis_date, field="basis_date")
                rule["basis_date"] = basis.isoformat()
        if isinstance(body.basis_text, str) and body.basis_text.strip():
            rule["basis_text"] = body.basis_text.strip()

    elif op == "UNTIL":
        if body.month is None or body.day is None:
            raise InspectionSetsSvcError(422, "UNTIL 은 month 와 day 가 필요합니다.")
        if isinstance(body.month, bool) or isinstance(body.day, bool):
            raise InspectionSetsSvcError(422, "month/day 는 정수여야 합니다.")
        if not _valid_month_day(int(body.month), int(body.day)):
            raise InspectionSetsSvcError(422, "유효하지 않은 month/day 조합입니다.")
        rule["month"] = int(body.month)
        rule["day"] = int(body.day)
        if body.basis_date is not None:
            basis = _parse_iso_date(body.basis_date, field="basis_date")
            rule["basis_date"] = basis.isoformat()
        # annual recurrence fields: NEVER invent

    return rule


def is_operation_time_ready(rule: Optional[dict], assignee_user_id: Any) -> bool:
    """Server readiness signal for future daily generator gate. UNTIL v1 always False."""
    if not isinstance(rule, dict):
        return False
    if not assignee_user_id:
        return False
    op = rule.get("operator")
    if op == "UNTIL":
        return False  # v1: persist ok · schedule execution incomplete · annual inference 0
    if op in ("EVERY", "WITHIN", "BEFORE"):
        if rule.get("value") is None or not rule.get("unit") or not rule.get("basis_date"):
            return False
        return True
    return False


def set_operation_time_rule(inspection_set_id: str, body: OperationTimeRuleBody) -> Dict[str, Any]:
    """Persist operation_time_rule only. No work_schedules INSERT/UPDATE/DELETE."""
    rule = normalize_operation_time_rule(body)
    supabase = get_supabase()
    res = (
        supabase.table("inspection_sets")
        .select(
            "id, factory_id, company_id, source, legal_obligation_atom_id, "
            "assignee_user_id, cycle_unit, cycle_value, schedule_anchor_date, "
            "last_inspection_date, next_planned_date, anchor_confirmed, "
            "status_code, inspection_set_name, inspection_category, "
            "holiday_process_type, operation_time_rule"
        )
        .eq("id", inspection_set_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise InspectionSetsSvcError(404, "점검 세트를 찾을 수 없습니다.")
    iset = res.data[0]
    if iset.get("source") != "LEGAL_ENGINE":
        raise InspectionSetsSvcError(409, "운영시간 규칙은 법령엔진 점검 세트에만 설정할 수 있습니다.")
    if not (isinstance(iset.get("legal_obligation_atom_id"), str) and iset["legal_obligation_atom_id"].strip()):
        raise InspectionSetsSvcError(409, "기존(레거시) 점검 세트에는 이 방식으로 설정할 수 없습니다.")

    op = rule["operator"]
    upd: Dict[str, Any] = {
        "operation_time_rule": rule,
        "updated_at": serialize_business_datetime(now_kst()),
    }

    # EVERY compatibility projection; NON-EVERY must not fake cycle_* for recurrence.
    if op == "EVERY":
        upd["cycle_unit"] = rule["unit"]
        upd["cycle_value"] = rule["value"]
    else:
        upd["cycle_unit"] = None
        upd["cycle_value"] = None

    # event basis → last_inspection false-write = 0 (never touch last_inspection_date here)
    # existing schedules / anchor fields do not block save (mutable set contract)

    upd_res = (
        supabase.table("inspection_sets")
        .update(upd)
        .eq("id", inspection_set_id)
        .eq("source", "LEGAL_ENGINE")
        .execute()
    )
    if not upd_res.data:
        raise InspectionSetsSvcError(409, "운영시간 규칙 저장에 실패했습니다.")

    ready = is_operation_time_ready(rule, iset.get("assignee_user_id"))
    return {
        "status": "success",
        "message": "운영시간 규칙이 저장됐습니다.",
        "data": {
            "inspection_set_id": inspection_set_id,
            "operation_time_rule": rule,
            "readiness": ready,
            "cycle_unit": upd.get("cycle_unit"),
            "cycle_value": upd.get("cycle_value"),
        },
    }


__all__ = [
    "set_operation_time_rule",
    "normalize_operation_time_rule",
    "is_operation_time_ready",
    "ALLOWED_UNITS",
    "ALLOWED_OPERATORS",
]
