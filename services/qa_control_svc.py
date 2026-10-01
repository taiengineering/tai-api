"""QA Control Service — WO-QA-CONTROL-PHASE2B-001.

5-table canonical schema: qa_items / qa_schedules / qa_runs / qa_run_targets / qa_run_results
N+1 금지 — 목록 조회는 bulk query + Python join.
GitHub dispatch = 0. Slack = 0.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from services.time import now_kst

log = logging.getLogger("qa_control")

_FINAL_STATUSES = frozenset({"COMPLETED", "ERROR", "CANCELED"})
_VALID_STATUSES = frozenset({"QUEUED", "RUNNING", "COMPLETED", "ERROR", "CANCELED"})
_VALID_TRANSITIONS: Dict[str, frozenset] = {
    "QUEUED":    frozenset({"RUNNING", "CANCELED"}),
    "RUNNING":   frozenset({"COMPLETED", "ERROR", "CANCELED"}),
    "COMPLETED": frozenset(),
    "ERROR":     frozenset(),
    "CANCELED":  frozenset(),
}

_ITEM_COLS = (
    "id, scenario_id, site_code, category, name, description, "
    "expected_summary, priority, runner_type, enabled, created_at, updated_at"
)
_SCHED_COLS = (
    "id, qa_item_id, enabled, frequency_type, frequency_value, "
    "anchor_time, day_of_week, timezone, next_run_at, last_scheduled_at, "
    "created_at, updated_at"
)
_RUN_COLS = (
    "id, trigger_type, run_status, github_run_id, github_run_attempt, "
    "head_sha, branch_name, requested_by, requested_at, "
    "started_at, finished_at, error_code, error_summary, created_at, updated_at"
)
_TARGET_COLS = "id, run_id, qa_item_id, ordinal, created_at"
_RESULT_COLS = (
    "id, run_id, qa_item_id, result_status, attempt, duration_ms, "
    "http_status, error_code, error_summary, artifact_ref, "
    "started_at, finished_at, checked_at, created_at"
)


# ── Summary ───────────────────────────────────────────────────────────────────

def get_summary(supabase) -> Dict[str, Any]:
    items_res = supabase.table("qa_items").select("id", count="exact").execute()
    sched_res = (
        supabase.table("qa_schedules")
        .select("id", count="exact")
        .eq("enabled", True)
        .execute()
    )
    runs_res = supabase.table("qa_runs").select("run_status").execute()

    status_counts: Dict[str, int] = {}
    for row in (runs_res.data or []):
        s = row.get("run_status", "UNKNOWN")
        status_counts[s] = status_counts.get(s, 0) + 1

    return {
        "total_items":      items_res.count or 0,
        "active_schedules": sched_res.count or 0,
        "runs_by_status":   status_counts,
    }


# ── Items ─────────────────────────────────────────────────────────────────────

def list_items(
    supabase,
    site_code: Optional[str] = None,
    priority: Optional[str] = None,
    enabled: Optional[bool] = None,
    page: int = 1,
    page_size: int = 50,
) -> Dict[str, Any]:
    off = (page - 1) * page_size
    q = supabase.table("qa_items").select(_ITEM_COLS, count="exact")
    if site_code:
        q = q.eq("site_code", site_code)
    if priority:
        q = q.eq("priority", priority)
    if enabled is not None:
        q = q.eq("enabled", enabled)
    res = q.order("priority").order("created_at").range(off, off + page_size - 1).execute()
    items = res.data or []
    total = res.count if res.count is not None else len(items)

    # Bulk fetch schedules — no N+1
    item_ids = [r["id"] for r in items]
    sched_map: Dict[str, Any] = {}
    if item_ids:
        s_res = (
            supabase.table("qa_schedules")
            .select(_SCHED_COLS)
            .in_("qa_item_id", item_ids)
            .execute()
        )
        for s in (s_res.data or []):
            sched_map[s["qa_item_id"]] = s

    for item in items:
        item["schedule"] = sched_map.get(item["id"])

    total_pages = (total + page_size - 1) // page_size
    return {
        "items":       items,
        "total":       total,
        "page":        page,
        "page_size":   page_size,
        "total_pages": total_pages,
    }


def update_item(supabase, qa_item_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    _ALLOWED = {"name", "description", "expected_summary", "enabled"}
    data = {k: v for k, v in patch.items() if k in _ALLOWED and v is not None}
    if not data:
        raise HTTPException(status_code=422, detail="수정할 필드가 없습니다")
    data["updated_at"] = now_kst().isoformat()
    res = supabase.table("qa_items").update(data).eq("id", qa_item_id).execute()
    rows = res.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="qa_item not found")
    return rows[0]


def update_schedule(supabase, qa_item_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    _ALLOWED = {
        "enabled", "frequency_type", "frequency_value",
        "anchor_time", "day_of_week", "timezone", "next_run_at",
    }
    data = {k: v for k, v in patch.items() if k in _ALLOWED}
    if not data:
        raise HTTPException(status_code=422, detail="수정할 필드가 없습니다")
    data["updated_at"] = now_kst().isoformat()
    res = (
        supabase.table("qa_schedules")
        .update(data)
        .eq("qa_item_id", qa_item_id)
        .execute()
    )
    rows = res.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="qa_schedule not found for this item")
    return rows[0]


# ── Runs ──────────────────────────────────────────────────────────────────────

def list_runs(
    supabase,
    run_status: Optional[str] = None,
    trigger_type: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> Dict[str, Any]:
    off = (page - 1) * page_size
    q = supabase.table("qa_runs").select(_RUN_COLS, count="exact")
    if run_status:
        q = q.eq("run_status", run_status)
    if trigger_type:
        q = q.eq("trigger_type", trigger_type)
    res = q.order("requested_at", desc=True).range(off, off + page_size - 1).execute()
    items = res.data or []
    total = res.count if res.count is not None else len(items)
    total_pages = (total + page_size - 1) // page_size
    return {
        "items":       items,
        "total":       total,
        "page":        page,
        "page_size":   page_size,
        "total_pages": total_pages,
    }


def get_run(supabase, run_id: str) -> Dict[str, Any]:
    run_res = (
        supabase.table("qa_runs").select(_RUN_COLS).eq("id", run_id).limit(1).execute()
    )
    if not run_res.data:
        raise HTTPException(status_code=404, detail="qa_run not found")
    run = run_res.data[0]

    # Bulk fetch targets and results — no N+1
    targets_res = (
        supabase.table("qa_run_targets")
        .select(_TARGET_COLS)
        .eq("run_id", run_id)
        .execute()
    )
    results_res = (
        supabase.table("qa_run_results")
        .select(_RESULT_COLS)
        .eq("run_id", run_id)
        .order("qa_item_id")
        .order("attempt")
        .execute()
    )
    targets = targets_res.data or []
    results = results_res.data or []

    # Derive FLAKY: attempt1=FAIL + attempt2=PASS same run+item
    attempts_by_item: Dict[str, List[Dict]] = defaultdict(list)
    for r in results:
        attempts_by_item[r["qa_item_id"]].append(r)

    for attempts in attempts_by_item.values():
        sorted_a = sorted(attempts, key=lambda x: x["attempt"])
        if (
            len(sorted_a) >= 2
            and sorted_a[0]["result_status"] == "FAIL"
            and sorted_a[-1]["result_status"] == "PASS"
        ):
            for a in attempts:
                a["flaky"] = True

    run["targets"] = targets
    run["results"] = results
    return run


def create_run(
    supabase,
    trigger_type: str,
    requested_by: Optional[str],
    qa_item_ids: List[str],
    ordinals: Optional[List[Optional[int]]] = None,
) -> Dict[str, Any]:
    if not qa_item_ids:
        raise HTTPException(status_code=422, detail="qa_item_ids가 비어있습니다")

    # Verify all qa_item_ids exist (bulk)
    items_res = (
        supabase.table("qa_items").select("id").in_("id", qa_item_ids).execute()
    )
    found_ids = {r["id"] for r in (items_res.data or [])}
    missing = [qid for qid in qa_item_ids if qid not in found_ids]
    if missing:
        raise HTTPException(status_code=422, detail=f"qa_item_ids not found: {missing}")

    now = now_kst().isoformat()
    run_row = {
        "trigger_type": trigger_type,
        "run_status":   "QUEUED",
        "requested_by": requested_by,
        "requested_at": now,
        "created_at":   now,
        "updated_at":   now,
    }
    run_res = supabase.table("qa_runs").insert(run_row).execute()
    if not run_res.data:
        raise HTTPException(status_code=500, detail="qa_run 생성 실패")
    run = run_res.data[0]
    run_id = run["id"]

    target_rows = []
    for i, qid in enumerate(qa_item_ids):
        ordinal = ordinals[i] if ordinals and i < len(ordinals) else None
        target_rows.append({
            "run_id":      run_id,
            "qa_item_id":  qid,
            "ordinal":     ordinal,
            "created_at":  now,
        })

    try:
        supabase.table("qa_run_targets").insert(target_rows).execute()
    except Exception as e:
        # Compensating DELETE: run created but targets failed
        log.error("[qa_control] target insert failed for run %s, compensating: %s", run_id, e)
        supabase.table("qa_runs").delete().eq("id", run_id).execute()
        raise HTTPException(status_code=500, detail="qa_run_targets 생성 실패 — run 롤백됨")

    run["targets"] = target_rows
    return run


# ── Internal: Result Callback ─────────────────────────────────────────────────

def apply_results(
    supabase,
    run_id: str,
    new_status: Optional[str],
    github_run_id: Optional[int],
    github_run_attempt: Optional[int],
    results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    run_res = (
        supabase.table("qa_runs").select(_RUN_COLS).eq("id", run_id).limit(1).execute()
    )
    if not run_res.data:
        raise HTTPException(status_code=404, detail="qa_run not found")
    run = run_res.data[0]
    current_status = run["run_status"]

    if new_status:
        if new_status not in _VALID_STATUSES:
            raise HTTPException(status_code=422, detail=f"invalid run_status: {new_status}")
        if current_status in _FINAL_STATUSES:
            raise HTTPException(
                status_code=409,
                detail=f"run {run_id} is already in final status {current_status}",
            )
        allowed = _VALID_TRANSITIONS.get(current_status, frozenset())
        if new_status != current_status and new_status not in allowed:
            raise HTTPException(
                status_code=422,
                detail=f"invalid transition {current_status} → {new_status}",
            )

    # Bulk fetch existing results — no N+1
    existing_res = (
        supabase.table("qa_run_results")
        .select(_RESULT_COLS)
        .eq("run_id", run_id)
        .execute()
    )
    existing_map = {
        (r["qa_item_id"], r["attempt"]): r
        for r in (existing_res.data or [])
    }

    now = now_kst().isoformat()
    to_insert: List[Dict[str, Any]] = []
    skipped = 0
    conflicts = []

    for r in results:
        qa_item_id = r["qa_item_id"]
        attempt = r.get("attempt", 1)
        key = (qa_item_id, attempt)

        if key in existing_map:
            if existing_map[key]["result_status"] != r.get("result_status"):
                conflicts.append({
                    "qa_item_id":        qa_item_id,
                    "attempt":           attempt,
                    "existing_status":   existing_map[key]["result_status"],
                    "incoming_status":   r.get("result_status"),
                })
            else:
                skipped += 1
        else:
            to_insert.append({
                "run_id":        run_id,
                "qa_item_id":    qa_item_id,
                "result_status": r["result_status"],
                "attempt":       attempt,
                "duration_ms":   r.get("duration_ms"),
                "http_status":   r.get("http_status"),
                "error_code":    r.get("error_code"),
                "error_summary": r.get("error_summary"),
                "artifact_ref":  r.get("artifact_ref"),
                "started_at":    r.get("started_at"),
                "finished_at":   r.get("finished_at"),
                "checked_at":    r.get("checked_at") or now,
                "created_at":    now,
            })

    if conflicts:
        raise HTTPException(
            status_code=409,
            detail={"message": "result payload conflict", "conflicts": conflicts},
        )

    if to_insert:
        supabase.table("qa_run_results").insert(to_insert).execute()

    # Update run
    run_patch: Dict[str, Any] = {"updated_at": now}
    if new_status and new_status != current_status:
        run_patch["run_status"] = new_status
        if new_status == "RUNNING" and not run.get("started_at"):
            run_patch["started_at"] = now
        elif new_status in _FINAL_STATUSES and not run.get("finished_at"):
            run_patch["finished_at"] = now
    if github_run_id is not None:
        run_patch["github_run_id"] = github_run_id
        run_patch["github_run_attempt"] = github_run_attempt

    supabase.table("qa_runs").update(run_patch).eq("id", run_id).execute()

    return {"run_id": run_id, "inserted": len(to_insert), "skipped": skipped}
