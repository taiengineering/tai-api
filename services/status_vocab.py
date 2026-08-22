"""C-2 값어퐈 정본화 (2026-08-22).

정본 + 전환기 구값 관용 읽기. DB 정규화(②) 전에도 안전하게 동작해야 한다.
"""
from __future__ import annotations

from typing import Iterable, List, Optional, Set


# ── §65 work_schedules.status_code (소문자) ─────────────────────────
WS_CANONICAL = frozenset({"planned", "scheduled", "completed", "in_progress"})

_WS_COMPLETED_READ: Set[str] = {"completed", "done", "DONE"}
_WS_SCHEDULED_READ: Set[str] = {"scheduled", "SCHEDULED"}
_WS_PLANNED_READ: Set[str] = {"planned", "PENDING", "PLANNED"}


def is_ws_completed(status_code: Optional[str]) -> bool:
    s = (status_code or "").strip()
    return s in _WS_COMPLETED_READ or s.lower() in ("completed", "done")


def ws_completed_query_values() -> List[str]:
    return ["completed", "DONE", "done"]


def ws_scheduled_query_values() -> List[str]:
    return ["scheduled", "SCHEDULED"]


def ws_planned_query_values() -> List[str]:
    return ["planned", "PENDING"]


def ws_write_completed() -> str:
    return "completed"


def ws_write_scheduled() -> str:
    return "scheduled"


def ws_write_planned() -> str:
    return "planned"


def normalize_ws_status_read(status_code: Optional[str]) -> Optional[str]:
    """구값 → 정본(비교·표시용). 알 수 없으면 원문 유지."""
    if status_code is None:
        return None
    s = status_code.strip()
    low = s.lower()
    if low in ("completed", "done") or s == "DONE":
        return "completed"
    if low == "scheduled" or s == "SCHEDULED":
        return "scheduled"
    if low == "planned" or s == "PENDING":
        return "planned"
    if low == "in_progress":
        return "in_progress"
    return s


# ── ㊸ construction_works.ptw_status ───────────────────────────────
PTW_CANONICAL = frozenset({"REQUESTED", "APPROVED"})


def is_ptw_pending_approval(ptw_status: Optional[str]) -> bool:
    return (ptw_status or "") in ("REQUESTED", "PENDING")


def ptw_pending_query_values() -> List[str]:
    return ["REQUESTED", "PENDING"]


def normalize_ptw_status_read(ptw_status: Optional[str]) -> Optional[str]:
    if ptw_status == "PENDING":
        return "REQUESTED"
    return ptw_status


def normalize_ptw_filter(filter_value: Optional[str]) -> Optional[str]:
    """쿼리 파라미터: PENDING → REQUESTED."""
    if filter_value == "PENDING":
        return "REQUESTED"
    return filter_value


def ptw_filter_query_values(filter_value: Optional[str]) -> Optional[List[str]]:
    if filter_value is None:
        return None
    if filter_value in ("REQUESTED", "PENDING"):
        return ptw_pending_query_values()
    return [filter_value]


# ── ㊹ construction_sites.status_code ──────────────────────────────
SITE_CANONICAL = frozenset({"PLANNED", "IN_PROGRESS", "COMPLETED"})


def normalize_site_status_read(status_code: Optional[str]) -> Optional[str]:
    if status_code == "ACTIVE":
        return "IN_PROGRESS"
    return status_code


def site_status_filter_query_values(filter_value: Optional[str]) -> Optional[List[str]]:
    if filter_value is None:
        return None
    if filter_value == "IN_PROGRESS":
        return ["IN_PROGRESS", "ACTIVE"]
    return [filter_value]


# ── ⑧ safety_inspection_results.result_code ────────────────────────
INSP_RESULT_CANONICAL = frozenset({"NORMAL", "ABNORMAL", "HOLD"})


def normalize_inspection_result_write(raw: Optional[str]) -> str:
    """기록 시 정본으로 저장. hold→HOLD(ABNORMAL 오기록 교정)."""
    if raw is None:
        return "ABNORMAL"
    s = str(raw).strip()
    low = s.lower()
    if low in ("ok", "pass", "normal"):
        return "NORMAL"
    if low in ("hold",):
        return "HOLD"
    if low in ("bad", "fail", "abnormal", "issue", "ng"):
        return "ABNORMAL"
    if s in INSP_RESULT_CANONICAL:
        return s
    return "ABNORMAL"


def normalize_inspection_result_read(code: Optional[str]) -> Optional[str]:
    if code is None:
        return None
    s = str(code).strip()
    low = s.lower()
    if low in ("ok", "pass"):
        return "NORMAL"
    if low == "hold":
        return "HOLD"
    if low in ("bad", "fail", "abnormal"):
        return "ABNORMAL"
    if s in INSP_RESULT_CANONICAL:
        return s
    return s


# ── ⑨ work_assignments.status_code ─────────────────────────────────
WA_CANONICAL = frozenset({"READY", "IN_PROGRESS", "DONE"})

_WA_DONE_READ: Set[str] = {"DONE", "done", "COMPLETED", "RESOLVED"}


def is_wa_done(status_code: Optional[str]) -> bool:
    s = (status_code or "").strip()
    return s in _WA_DONE_READ or s.upper() in ("DONE", "COMPLETED", "RESOLVED")


def wa_write_ready() -> str:
    return "READY"


def wa_write_done() -> str:
    return "DONE"


def wa_write_in_progress() -> str:
    return "IN_PROGRESS"


def wa_active_query_values() -> List[str]:
    """미완료·진행 중 배정 조회(구 PENDING 포함)."""
    return ["READY", "PENDING", "IN_PROGRESS"]
