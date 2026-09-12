"""Official LEGAL_ENGINE → work_schedules materializer (OTR-based).

WO-SAFE-DAILY-SCHEDULE-MATERIALIZER-V1-001 — REUSE_WITH_PATCH.

- Consumes latest inspection_sets.operation_time_rule only.
- Writes lowercase scheduled + source LEGAL via status_vocab.
- Reconciliation V1: create-missing + limited child-free assignee sync.
- DELETE = 0. PENDING/SCHEDULED/LAW_ENGINE write = 0.
"""
from __future__ import annotations

from datetime import date
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


def _has_atom(iset: dict) -> bool:
    atom = iset.get("legal_obligation_atom_id")
    return isinstance(atom, str) and bool(atom.strip())


def _child_linked(supabase, schedule_id: str, factory_id: str) -> bool:
    """True if any child row references (schedule_id, factory_id)."""
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


def _fetch_exact(
    supabase, factory_id: str, inspection_set_id: str, planned_date: str
) -> Optional[dict]:
    res = (
        supabase.table("work_schedules")
        .select(
            "id, factory_id, inspection_set_id, planned_date, status_code, "
            "source_type, assigned_user_id, active_yn"
        )
        .eq("factory_id", factory_id)
        .eq("inspection_set_id", inspection_set_id)
        .eq("planned_date", planned_date)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    return rows[0] if rows else None


def _count_stale_future(
    supabase, factory_id: str, inspection_set_id: str, planned_date: str
) -> int:
    """Read-only: other-date future rows for same set (no mutation)."""
    today = business_today().isoformat()
    res = (
        supabase.table("work_schedules")
        .select("id, planned_date")
        .eq("factory_id", factory_id)
        .eq("inspection_set_id", inspection_set_id)
        .gte("planned_date", today)
        .neq("planned_date", planned_date)
        .execute()
    )
    return len(res.data or [])


def _insert_idempotent(supabase, row: dict) -> int:
    """Reuse rolling UNIQUE conflict idiom — ON CONFLICT DO NOTHING."""
    res = (
        supabase.table("work_schedules")
        .upsert(row, on_conflict=CONFLICT_KEY, ignore_duplicates=True)
        .execute()
    )
    return 1 if res.data else 0


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
    empty = {
        "total_sets": 0,
        "created": 0,
        "skipped_dup": 0,
        "skipped_no_condition": 0,
        "assignee_synced": 0,
        "preserved_existing": 0,
        "preserved_child_linked": 0,
        "preserved_stale_future": 0,
    }
    if not all_sets:
        return empty

    created = skipped_dup = skipped_no_cond = 0
    assignee_synced = preserved_existing = preserved_child = preserved_stale = 0

    for iset in all_sets:
        if not _has_atom(iset):
            skipped_no_cond += 1
            continue

        rule = iset.get("operation_time_rule")
        if not is_operation_time_ready(rule, iset.get("assignee_user_id")):
            skipped_no_cond += 1
            continue

        planned, skip_reason = _operation_planned_date(rule)
        if planned is None:
            skipped_no_cond += 1
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
                skipped_no_cond += 1
                continue

        planned_s = planned.isoformat()
        set_id = iset["id"]

        preserved_stale += _count_stale_future(supabase, factory_id, set_id, planned_s)

        existing = _fetch_exact(supabase, factory_id, set_id, planned_s)
        if existing:
            norm = normalize_ws_status_read(existing.get("status_code"))
            sid = existing["id"]

            if norm in _PRESERVE_STATUSES:
                preserved_existing += 1
                skipped_dup += 1
                continue

            if _child_linked(supabase, sid, factory_id):
                preserved_child += 1
                skipped_dup += 1
                continue

            if norm in _RECONCILE_STATUSES:
                latest_assignee = iset.get("assignee_user_id")
                if existing.get("assigned_user_id") != latest_assignee:
                    supabase.table("work_schedules").update(
                        {"assigned_user_id": latest_assignee}
                    ).eq("id", sid).eq("factory_id", factory_id).execute()
                    assignee_synced += 1
                else:
                    preserved_existing += 1
                skipped_dup += 1
                continue

            # unknown / excluded / other — preserve, no create
            preserved_existing += 1
            skipped_dup += 1
            continue

        row = _build_operation_schedule_row(iset, planned, rule)
        created += _insert_idempotent(supabase, row)

    return {
        "total_sets": len(all_sets),
        "created": created,
        "skipped_dup": skipped_dup,
        "skipped_no_condition": skipped_no_cond,
        "assignee_synced": assignee_synced,
        "preserved_existing": preserved_existing,
        "preserved_child_linked": preserved_child,
        "preserved_stale_future": preserved_stale,
    }


def run_generate_law_engine(factory_id: str, supabase) -> dict:
    """Compatibility wrapper → official OTR materializer.

    Name retained for callers/tests. Does NOT use PENDING/LAW_ENGINE writers.
    """
    return run_generate_operation_schedules(factory_id, supabase)
