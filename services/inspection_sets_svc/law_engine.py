"""Official LEGAL_ENGINE → work_schedules materializer (OTR-based).

WO-SAFE-DAILY-SCHEDULE-MATERIALIZER-V1-001 / PATCH-R1 — REUSE_WITH_PATCH.

- Consumes latest inspection_sets.operation_time_rule only.
- Writes lowercase scheduled + source LEGAL via status_vocab.
- Stale future convergence: UPDATE in-place when UNIQUE allows;
  leftover child-free stale LEGAL future rows removed only when UNIQUE
  blocks further UPDATE (soft-cancel status is not used; not in WS_CANONICAL).
- completed / in_progress / child-linked: PRESERVE.
- PENDING/SCHEDULED/LAW_ENGINE write = 0.
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
from services.status_vocab import normalize_ws_status_read, ws_write_scheduled
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
    "source_type, assigned_user_id, active_yn"
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
        # Real FK: safety_inspections.assignment_id → work_schedules.id (name mismatch).
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


def _list_stale_future_candidates(
    supabase, factory_id: str, inspection_set_id: str, expected_planned: str
) -> List[dict]:
    """Child-free future LEGAL planned/scheduled rows with other planned_date."""
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
        norm = normalize_ws_status_read(row.get("status_code"))
        if norm not in _RECONCILE_STATUSES:
            continue
        if _child_linked(supabase, row["id"], factory_id):
            continue
        out.append(row)
    return out


def _converge_payload(iset: dict, planned, rule: dict) -> dict:
    """Fields safe to UPDATE on a converging future row (no id/factory rewrite)."""
    row = _build_operation_schedule_row(iset, planned, rule)
    return {
        "planned_date": row["planned_date"],
        "start_date": row["start_date"],
        "end_date": row["end_date"],
        "repeat_type": row["repeat_type"],
        "repeat_interval": row["repeat_interval"],
        "status_code": ws_write_scheduled(),
        "source_type": "LEGAL",
        "assigned_user_id": row["assigned_user_id"],
        "obligation_type": row["obligation_type"],
        "summary": row["summary"],
        "description": row.get("description") or "",
        "active_yn": True,
    }


def _update_schedule(
    supabase, schedule_id: str, factory_id: str, payload: dict
) -> None:
    (
        supabase.table("work_schedules")
        .update(payload)
        .eq("id", schedule_id)
        .eq("factory_id", factory_id)
        .execute()
    )


def _delete_stale(supabase, schedule_id: str, factory_id: str) -> None:
    """Remove leftover child-free stale LEGAL future when UNIQUE blocks UPDATE.

    Not a cancel invention — row must not remain concurrently executable with
    the latest-OTR identity. Predicates: id + factory_id only.
    """
    (
        supabase.table("work_schedules")
        .delete()
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


def _handle_exact_identity(
    supabase,
    iset: dict,
    existing: dict,
    factory_id: str,
    counters: dict,
) -> None:
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
            _update_schedule(
                supabase, sid, factory_id, {"assigned_user_id": latest_assignee}
            )
            counters["assignee_synced"] += 1
        else:
            counters["preserved_existing"] += 1
        counters["skipped_dup"] += 1
        return

    counters["preserved_existing"] += 1
    counters["skipped_dup"] += 1


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
        "stale_converged": 0,
        "stale_removed": 0,
        "delete_count": 0,
    }
    if not all_sets:
        return empty

    counters = {
        "created": 0,
        "skipped_dup": 0,
        "skipped_no_condition": 0,
        "assignee_synced": 0,
        "preserved_existing": 0,
        "preserved_child_linked": 0,
        "stale_converged": 0,
        "stale_removed": 0,
        "delete_count": 0,
    }

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
        payload = _converge_payload(iset, planned, rule)

        stales = _list_stale_future_candidates(supabase, factory_id, set_id, planned_s)
        exact = _fetch_exact(supabase, factory_id, set_id, planned_s)

        # Preferred: UPDATE one child-free stale onto expected date when free.
        if exact is None and stales:
            victim = stales[0]
            _update_schedule(supabase, victim["id"], factory_id, payload)
            counters["stale_converged"] += 1
            exact = _fetch_exact(supabase, factory_id, set_id, planned_s)
            stales = [s for s in stales if s["id"] != victim["id"]]

        if exact is not None:
            _handle_exact_identity(supabase, iset, exact, factory_id, counters)
        else:
            row = _build_operation_schedule_row(iset, planned, rule)
            counters["created"] += _insert_idempotent(supabase, row)
            exact = _fetch_exact(supabase, factory_id, set_id, planned_s)

        # Leftover stales cannot UPDATE onto occupied expected identity (UNIQUE).
        # No canonical cancelled — remove only narrowly-eligible leftovers.
        for stale in stales:
            live_res = (
                supabase.table("work_schedules")
                .select(_WS_SELECT)
                .eq("factory_id", factory_id)
                .eq("id", stale["id"])
                .limit(1)
                .execute()
            )
            live = (live_res.data or [None])[0]
            if not live:
                continue
            norm = normalize_ws_status_read(live.get("status_code"))
            if norm not in _RECONCILE_STATUSES:
                counters["preserved_existing"] += 1
                continue
            if live.get("source_type") != "LEGAL":
                counters["preserved_existing"] += 1
                continue
            if str(live.get("planned_date") or "") == planned_s:
                continue
            if _child_linked(supabase, live["id"], factory_id):
                counters["preserved_child_linked"] += 1
                continue
            _delete_stale(supabase, live["id"], factory_id)
            counters["stale_removed"] += 1
            counters["delete_count"] += 1

    return {
        "total_sets": len(all_sets),
        "created": counters["created"],
        "skipped_dup": counters["skipped_dup"],
        "skipped_no_condition": counters["skipped_no_condition"],
        "assignee_synced": counters["assignee_synced"],
        "preserved_existing": counters["preserved_existing"],
        "preserved_child_linked": counters["preserved_child_linked"],
        "stale_converged": counters["stale_converged"],
        "stale_removed": counters["stale_removed"],
        "delete_count": counters["delete_count"],
    }


def run_generate_law_engine(factory_id: str, supabase) -> dict:
    """Compatibility wrapper → official OTR materializer.

    Name retained for callers/tests. Does NOT use PENDING/LAW_ENGINE writers.
    """
    return run_generate_operation_schedules(factory_id, supabase)
