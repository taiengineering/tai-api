"""Official LEGAL_ENGINE → work_schedules materializer (OTR-based).

WO-SAFE-DAILY-SCHEDULE-MATERIALIZER-STAGE2-PATCH-R3-001.

Stage2 disposition (Definition SoT):
  ENSURE EXPECTED_LATEST_EXECUTABLE
  → VERIFY active LEGAL latest
  → PRESERVE + INACTIVATE child-free eligible stale (active_yn=false)
  + INSERT / eligible REACTIVATE

Invariants:
  DELETE = 0
  planned_date / start_date / end_date rewrite = 0
  identity rewrite = 0
  non-LEGAL exact takeover = 0
"""
from __future__ import annotations

from typing import List, Optional

from services.inspection_rolling import CONFLICT_KEY
from services.inspection_sets_helpers import (
    _build_operation_schedule_row,
    _operation_planned_date,
    adjust_planned_for_holiday,
)
from services.inspection_sets_svc.operation_time_rule import is_operation_time_ready
from services.status_vocab import normalize_ws_status_read
from services.time import business_today

_SET_SELECT = (
    "id, factory_id, company_id, source, legal_obligation_atom_id, "
    "operation_time_rule, assignee_user_id, "
    "inspection_set_name, inspection_category, description, "
    "holiday_process_type"
)

_RECONCILE_STATUSES = frozenset({"planned", "scheduled"})
_PRESERVE_STATUSES = frozenset({"completed", "in_progress"})

_WS_SELECT = (
    "id, factory_id, inspection_set_id, planned_date, status_code, "
    "source_type, assigned_user_id, active_yn, is_excluded, excluded_reason"
)


def _has_atom(iset: dict) -> bool:
    atom = iset.get("legal_obligation_atom_id")
    return isinstance(atom, str) and bool(atom.strip())


def _child_linked(supabase, schedule_id: str, factory_id: str) -> bool:
    """True if any child references this schedule pair.

    FK evidence (production):
    - work_assignments.(schedule_id, factory_id) → work_schedules
    - safety_inspections.(assignment_id, factory_id) → work_schedules(id, factory_id)
      (column name says assignment_id; FK target is work_schedules — see worker_check)
    - equipment_checkins.(schedule_id, factory_id) → work_schedules

    Any query exception → fail-close preserve (True).
    """
    try:
        wa = (
            supabase.table("work_assignments")
            .select("id")
            .eq("schedule_id", schedule_id)
            .eq("factory_id", factory_id)
            .limit(1)
            .execute()
        )
        if wa.data:
            return True
        si = (
            supabase.table("safety_inspections")
            .select("id")
            .eq("assignment_id", schedule_id)
            .eq("factory_id", factory_id)
            .limit(1)
            .execute()
        )
        if si.data:
            return True
        ec = (
            supabase.table("equipment_checkins")
            .select("id")
            .eq("schedule_id", schedule_id)
            .eq("factory_id", factory_id)
            .limit(1)
            .execute()
        )
        return bool(ec.data)
    except Exception:
        return True


def _fetch_exact(
    supabase, factory_id: str, inspection_set_id: str, planned_date: str
) -> Optional[dict]:
    res = (
        supabase.table("work_schedules")
        .select(_WS_SELECT)
        .eq("factory_id", factory_id)
        .eq("inspection_set_id", inspection_set_id)
        .eq("planned_date", planned_date)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    return rows[0] if rows else None


def _is_exact_secured(row: Optional[dict]) -> bool:
    if not row:
        return False
    return row.get("source_type") == "LEGAL" and row.get("active_yn") is True


def _auto_reactivatable_exact(supabase, row: dict, factory_id: str) -> bool:
    """AUTO_REACTIVATABLE_EXACT — all guards required."""
    if row.get("source_type") != "LEGAL":
        return False
    if row.get("active_yn") is not False:
        return False
    norm = normalize_ws_status_read(row.get("status_code"))
    if norm not in _RECONCILE_STATUSES:
        return False
    if row.get("is_excluded") is True:
        return False
    if row.get("excluded_reason") is not None:
        return False
    if _child_linked(supabase, row["id"], factory_id):
        return False
    return True


def _reactivate_exact(supabase, schedule_id: str, factory_id: str) -> None:
    """Exact inactive latest: active_yn false → true only."""
    (
        supabase.table("work_schedules")
        .update({"active_yn": True})
        .eq("id", schedule_id)
        .eq("factory_id", factory_id)
        .execute()
    )


def _inactivate_stale(supabase, schedule_id: str, factory_id: str) -> None:
    """Eligible stale: active_yn true → false only (occurrence pair)."""
    (
        supabase.table("work_schedules")
        .update({"active_yn": False})
        .eq("id", schedule_id)
        .eq("factory_id", factory_id)
        .eq("active_yn", True)
        .execute()
    )


def _list_stale_future_candidates(
    supabase, factory_id: str, inspection_set_id: str, expected_planned: str
) -> List[dict]:
    """Future LEGAL planned/scheduled active rows with other planned_date."""
    today = business_today().isoformat()
    res = (
        supabase.table("work_schedules")
        .select(_WS_SELECT)
        .eq("factory_id", factory_id)
        .eq("inspection_set_id", inspection_set_id)
        .eq("source_type", "LEGAL")
        .gte("planned_date", today)
        .neq("planned_date", expected_planned)
        .execute()
    )
    out: List[dict] = []
    for row in res.data or []:
        if row.get("active_yn") is not True:
            continue
        norm = normalize_ws_status_read(row.get("status_code"))
        if norm not in _RECONCILE_STATUSES:
            continue
        out.append(row)
    return out


def _sync_assignee_only(
    supabase, schedule_id: str, factory_id: str, assignee_user_id
) -> None:
    """Exact LEGAL future row: assigned_user_id ONLY."""
    (
        supabase.table("work_schedules")
        .update({"assigned_user_id": assignee_user_id})
        .eq("id", schedule_id)
        .eq("factory_id", factory_id)
        .execute()
    )


def _insert_idempotent(supabase, row: dict) -> int:
    """Reuse rolling UNIQUE conflict idiom — ON CONFLICT DO NOTHING."""
    res = (
        supabase.table("work_schedules")
        .upsert(row, on_conflict=CONFLICT_KEY, ignore_duplicates=True)
        .execute()
    )
    return 1 if res.data else 0


def _handle_exact_active_legal(
    supabase,
    iset: dict,
    existing: dict,
    factory_id: str,
    counters: dict,
) -> None:
    """Exact LEGAL active_yn=true — preserve / child / assignee-only sync."""
    norm = normalize_ws_status_read(existing.get("status_code"))
    sid = existing["id"]

    if norm in _PRESERVE_STATUSES:
        counters["preserved_existing"] += 1
        counters["skipped_dup"] += 1
        return

    if _child_linked(supabase, sid, factory_id):
        counters["preserved_child_linked"] += 1
        counters["skipped_dup"] += 1
        return

    if norm in _RECONCILE_STATUSES:
        latest_assignee = iset.get("assignee_user_id")
        if existing.get("assigned_user_id") != latest_assignee:
            _sync_assignee_only(supabase, sid, factory_id, latest_assignee)
            counters["assignee_synced"] += 1
        else:
            counters["preserved_existing"] += 1
        counters["skipped_dup"] += 1
        return

    # Unknown lifecycle → preserve
    counters["preserved_existing"] += 1
    counters["skipped_dup"] += 1


def _ensure_expected_latest_executable(
    supabase,
    iset: dict,
    factory_id: str,
    set_id: str,
    planned,
    planned_s: str,
    rule,
    counters: dict,
) -> bool:
    """ENSURE EXPECTED_LATEST_EXECUTABLE then verify. Returns secured bool."""
    exact = _fetch_exact(supabase, factory_id, set_id, planned_s)

    # CASE A — missing
    if exact is None:
        row = _build_operation_schedule_row(iset, planned, rule)
        inserted = _insert_idempotent(supabase, row)
        verified = _fetch_exact(supabase, factory_id, set_id, planned_s)
        if _is_exact_secured(verified):
            counters["created"] += inserted
            return True
        counters["latest_not_secured"] += 1
        return False

    # CASE B / C / D — exact identity occupied
    if exact.get("source_type") != "LEGAL":
        # non-LEGAL: no takeover
        counters["preserved_existing"] += 1
        counters["skipped_dup"] += 1
        counters["latest_not_secured"] += 1
        return False

    active = exact.get("active_yn")

    # CASE B — already active LEGAL
    if active is True:
        _handle_exact_active_legal(supabase, iset, exact, factory_id, counters)
        return True

    # CASE C — inactive eligible reactivate
    if active is False and _auto_reactivatable_exact(supabase, exact, factory_id):
        sid = exact["id"]
        _reactivate_exact(supabase, sid, factory_id)
        verified = _fetch_exact(supabase, factory_id, set_id, planned_s)
        if not _is_exact_secured(verified):
            counters["latest_not_secured"] += 1
            return False
        counters["reactivated"] += 1
        # optional assignee-only sync after reactivation (child-free already proven)
        latest_assignee = iset.get("assignee_user_id")
        if verified.get("assigned_user_id") != latest_assignee:
            _sync_assignee_only(supabase, sid, factory_id, latest_assignee)
            counters["assignee_synced"] += 1
        counters["skipped_dup"] += 1
        return True

    # CASE D — inactive / NULL / not reactivatable → PRESERVE INACTIVE
    counters["preserved_existing"] += 1
    counters["skipped_dup"] += 1
    counters["latest_not_secured"] += 1
    return False


def _inactivate_eligible_stales(
    supabase,
    factory_id: str,
    set_id: str,
    planned_s: str,
    counters: dict,
) -> None:
    """Only after latest secured: child-free eligible stale → active_yn=false."""
    stales = _list_stale_future_candidates(supabase, factory_id, set_id, planned_s)
    for stale in stales:
        sid = stale["id"]
        if _child_linked(supabase, sid, factory_id):
            counters["stale_preserved"] += 1
            continue
        _inactivate_stale(supabase, sid, factory_id)
        counters["stale_inactivated"] += 1


def _empty_counters() -> dict:
    return {
        "created": 0,
        "skipped_dup": 0,
        "skipped_no_condition": 0,
        "assignee_synced": 0,
        "preserved_existing": 0,
        "preserved_child_linked": 0,
        "stale_preserved": 0,
        "reactivated": 0,
        "stale_inactivated": 0,
        "latest_not_secured": 0,
    }


def run_generate_operation_schedules(factory_id: str, supabase) -> dict:
    """Factory-scoped official materializer: latest OTR → work_schedules."""
    sets_res = (
        supabase.table("inspection_sets")
        .select(_SET_SELECT)
        .eq("factory_id", factory_id)
        .eq("is_active", True)
        .eq("source", "LEGAL_ENGINE")
        .execute()
    )
    all_sets: List[dict] = sets_res.data or []
    if not all_sets:
        return {"total_sets": 0, **_empty_counters()}

    counters = _empty_counters()

    for iset in all_sets:
        if not _has_atom(iset):
            counters["skipped_no_condition"] += 1
            continue

        rule = iset.get("operation_time_rule")
        if not is_operation_time_ready(rule, iset.get("assignee_user_id")):
            counters["skipped_no_condition"] += 1
            continue

        planned, skip_reason = _operation_planned_date(rule)
        if planned is None:
            counters["skipped_no_condition"] += 1
            continue

        op = (rule.get("operator") or "").upper()
        if op == "EVERY":
            planned = adjust_planned_for_holiday(
                planned,
                iset.get("company_id"),
                iset.get("factory_id"),
                iset.get("holiday_process_type"),
            )
            if planned is None:
                counters["skipped_no_condition"] += 1
                continue

        planned_s = planned.isoformat()
        set_id = iset["id"]

        # 1–4: ENSURE EXPECTED_LATEST_EXECUTABLE → verify
        secured = _ensure_expected_latest_executable(
            supabase, iset, factory_id, set_id, planned, planned_s, rule, counters
        )
        # 5–6: stale inactivation only after latest secured
        if secured:
            _inactivate_eligible_stales(
                supabase, factory_id, set_id, planned_s, counters
            )

    return {
        "total_sets": len(all_sets),
        "created": counters["created"],
        "skipped_dup": counters["skipped_dup"],
        "skipped_no_condition": counters["skipped_no_condition"],
        "assignee_synced": counters["assignee_synced"],
        "preserved_existing": counters["preserved_existing"],
        "preserved_child_linked": counters["preserved_child_linked"],
        "stale_preserved": counters["stale_preserved"],
        "reactivated": counters["reactivated"],
        "stale_inactivated": counters["stale_inactivated"],
        "latest_not_secured": counters["latest_not_secured"],
    }


def run_generate_law_engine(factory_id: str, supabase) -> dict:
    """Compatibility wrapper → official OTR materializer.

    Name retained for callers/tests. Does NOT use PENDING/LAW_ENGINE writers.
    """
    return run_generate_operation_schedules(factory_id, supabase)
