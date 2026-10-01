"""QA Control Service — WO-QA-CONTROL-PHASE2B-001 PATCH-1.

5-table canonical schema: qa_items / qa_schedules / qa_runs / qa_run_targets / qa_run_results
N+1 금지 — 목록 조회는 bulk query + Python join.
GitHub dispatch = 0. Slack = 0.
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from services.time import now_kst

log = logging.getLogger("qa_control")

_FINAL_STATUSES = frozenset({"COMPLETED", "ERROR", "CANCELED"})
_VALID_STATUSES = frozenset({"QUEUED", "RUNNING", "COMPLETED", "ERROR", "CANCELED"})
_VALID_TRANSITIONS: Dict[str, frozenset] = {
    "QUEUED":    frozenset({"RUNNING", "ERROR", "CANCELED"}),  # QUEUED→ERROR allowed
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

# ── Error redaction ───────────────────────────────────────────────────────────

_MAX_ERROR_LEN = 1000
_REDACT_RE = re.compile(
    r"(Authorization:\s*Bearer\s+|"
    r"access_token[\"'\s:=]+|"
    r"refresh_token[\"'\s:=]+|"
    r"password[\"'\s:=]+|"
    r"api_key[\"'\s:=]+|"
    r"secret[\"'\s:=]+|"
    r"token=)"
    r"\S+",
    re.IGNORECASE,
)
_SIGNED_URL_RE = re.compile(r"(token=|X-Amz-Signature=|sig=|signature=)", re.IGNORECASE)


def redact_error_summary(text: Optional[str]) -> Optional[str]:
    """credential 패턴 마스킹 + 1000자 truncation."""
    if not text:
        return text
    text = _REDACT_RE.sub(lambda m: m.group(1) + "[REDACTED]", text)
    return text[:_MAX_ERROR_LEN]


def _validate_artifact_ref(artifact_ref: Optional[str]) -> None:
    if artifact_ref and _SIGNED_URL_RE.search(artifact_ref):
        raise HTTPException(400, "artifact_ref에 credential 또는 signed URL을 저장할 수 없습니다")


# ── Effective status derivation ───────────────────────────────────────────────

def derive_effective_status(attempts: List[Dict]) -> str:
    """sorted attempts list → PASS / FAIL / FLAKY / BLOCKED / SKIPPED / NEVER_RUN.

    FLAKY: final attempt=PASS + any earlier attempt=FAIL.
    NEVER_RUN: empty list (caller should pass [] for no results).
    """
    if not attempts:
        return "NEVER_RUN"
    sorted_a = sorted(attempts, key=lambda a: a.get("attempt", 1))
    final_status = sorted_a[-1]["result_status"]
    if final_status == "PASS" and any(a["result_status"] == "FAIL" for a in sorted_a[:-1]):
        return "FLAKY"
    return final_status


def _enrich_items(supabase, items: List[Dict]) -> None:
    """Mutates items in-place: adds effective_status, last_run_id, last_checked_at,
    last_duration_ms, last_error_summary. Single bulk results query — no N+1."""
    item_ids = [i["id"] for i in items]
    if not item_ids:
        return

    res = (
        supabase.table("qa_run_results")
        .select("run_id, qa_item_id, result_status, attempt, duration_ms, error_summary, checked_at")
        .in_("qa_item_id", item_ids)
        .execute()
    )
    all_results = res.data or []

    # item_id → run_id → attempts
    by_item: Dict[str, Dict[str, List]] = defaultdict(lambda: defaultdict(list))
    for r in all_results:
        by_item[r["qa_item_id"]][r["run_id"]].append(r)

    for item in items:
        iid = item["id"]
        runs = by_item.get(iid, {})
        if not runs:
            item["effective_status"] = "NEVER_RUN"
            item["last_run_id"] = None
            item["last_checked_at"] = None
            item["last_duration_ms"] = None
            item["last_error_summary"] = None
            continue

        latest_run_id = max(
            runs.keys(),
            key=lambda rid: max((r.get("checked_at") or "") for r in runs[rid]),
        )
        attempts = sorted(runs[latest_run_id], key=lambda a: a.get("attempt", 1))

        item["effective_status"] = derive_effective_status(attempts)
        item["last_run_id"] = latest_run_id
        item["last_checked_at"] = max(a.get("checked_at") or "" for a in attempts) or None
        item["last_duration_ms"] = (
            sum(a.get("duration_ms") or 0 for a in attempts) or None
        )
        item["last_error_summary"] = attempts[-1].get("error_summary")


# ── Schedule validation ───────────────────────────────────────────────────────

_VALID_FREQ_TYPES = frozenset({"MANUAL", "MINUTES", "HOURLY", "DAILY", "WEEKLY"})
_ALL_EFFECTIVE_STATUSES = ("PASS", "FAIL", "FLAKY", "BLOCKED", "SKIPPED", "NEVER_RUN")


def _validate_effective_schedule(effective: Dict) -> None:
    """Merged effective schedule의 semantic CHECK. DB CHECK는 2차 방어선."""
    tz = effective.get("timezone")
    if tz is not None and tz != "Asia/Seoul":
        raise HTTPException(400, "timezone은 Asia/Seoul만 허용됩니다")

    ft = effective.get("frequency_type")
    if ft is None:
        return

    if ft not in _VALID_FREQ_TYPES:
        raise HTTPException(400, f"알 수 없는 frequency_type: {ft}")

    if ft == "MANUAL":
        if effective.get("enabled") is True:
            raise HTTPException(400, "MANUAL schedule은 enabled=true가 불가합니다")
    elif ft == "DAILY":
        if not effective.get("anchor_time"):
            raise HTTPException(400, "DAILY는 anchor_time이 필요합니다")
    elif ft == "WEEKLY":
        if not effective.get("anchor_time"):
            raise HTTPException(400, "WEEKLY는 anchor_time이 필요합니다")
        dow = effective.get("day_of_week")
        if dow is None:
            raise HTTPException(400, "WEEKLY는 day_of_week(0-6)이 필요합니다")
        if not isinstance(dow, int) or not (0 <= dow <= 6):
            raise HTTPException(400, "day_of_week는 0~6 범위의 정수여야 합니다")
    elif ft in ("MINUTES", "HOURLY"):
        fv = effective.get("frequency_value")
        if fv is None or fv <= 0:
            raise HTTPException(400, f"{ft}는 frequency_value > 0이 필요합니다")


# ── Summary ───────────────────────────────────────────────────────────────────

def get_summary(supabase) -> Dict[str, Any]:
    items_res = supabase.table("qa_items").select(_ITEM_COLS).execute()
    all_items = items_res.data or []
    total = len(all_items)
    enabled_count = sum(1 for i in all_items if i.get("enabled"))

    # Bulk enrich
    _enrich_items(supabase, all_items)

    status_counts: Dict[str, int] = dict.fromkeys(_ALL_EFFECTIVE_STATUSES, 0)
    site_data: Dict[str, Dict] = {}
    for item in all_items:
        eff = item.get("effective_status", "NEVER_RUN")
        if eff in status_counts:
            status_counts[eff] += 1
        sc = item.get("site_code", "UNKNOWN")
        if sc not in site_data:
            site_data[sc] = {"total": 0, "status_counts": dict.fromkeys(_ALL_EFFECTIVE_STATUSES, 0)}
        site_data[sc]["total"] += 1
        if eff in site_data[sc]["status_counts"]:
            site_data[sc]["status_counts"][eff] += 1

    sites = [
        {"site_code": sc, "total": v["total"], "status_counts": v["status_counts"]}
        for sc, v in site_data.items()
    ]

    return {
        "total":         total,
        "enabled":       enabled_count,
        "status_counts": status_counts,
        "sites":         sites,
    }


# ── Items ─────────────────────────────────────────────────────────────────────

def list_items(
    supabase,
    site_code:        Optional[str]  = None,
    priority:         Optional[str]  = None,
    enabled:          Optional[bool] = None,
    category:         Optional[str]  = None,
    effective_status: Optional[str]  = None,
    page:             int            = 1,
    page_size:        int            = 50,
) -> Dict[str, Any]:
    # Fetch all items matching basic filters (effective_status requires post-compute filter)
    q = supabase.table("qa_items").select(_ITEM_COLS)
    if site_code:
        q = q.eq("site_code", site_code)
    if priority:
        q = q.eq("priority", priority)
    if enabled is not None:
        q = q.eq("enabled", enabled)
    if category:
        q = q.eq("category", category)
    res = q.order("priority").order("created_at").execute()
    all_items = res.data or []

    # Bulk fetch schedules — no N+1
    item_ids = [r["id"] for r in all_items]
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

    # Bulk enrich with effective_status + last run info
    _enrich_items(supabase, all_items)

    for item in all_items:
        item["schedule"] = sched_map.get(item["id"])

    # Post-filter by effective_status (derived field)
    if effective_status:
        all_items = [i for i in all_items if i.get("effective_status") == effective_status]

    # Paginate
    total = len(all_items)
    off = (page - 1) * page_size
    page_items = all_items[off: off + page_size]
    total_pages = (total + page_size - 1) // page_size

    return {
        "items":       page_items,
        "total":       total,
        "page":        page,
        "page_size":   page_size,
        "total_pages": total_pages,
    }


def update_item(supabase, qa_item_id: str, enabled: Optional[bool]) -> Dict[str, Any]:
    """enabled 필드만 수정 가능."""
    if enabled is None:
        raise HTTPException(422, "enabled 값이 필요합니다")
    data = {"enabled": enabled, "updated_at": now_kst().isoformat()}
    res = supabase.table("qa_items").update(data).eq("id", qa_item_id).execute()
    rows = res.data or []
    if not rows:
        raise HTTPException(404, "qa_item not found")
    return rows[0]


def update_schedule(supabase, qa_item_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    _ALLOWED = {
        "enabled", "frequency_type", "frequency_value",
        "anchor_time", "day_of_week", "timezone",
    }
    data = {k: v for k, v in patch.items() if k in _ALLOWED}
    if not data:
        raise HTTPException(422, "수정할 필드가 없습니다")

    # Fetch existing to compute effective merged state
    existing_res = (
        supabase.table("qa_schedules")
        .select(_SCHED_COLS)
        .eq("qa_item_id", qa_item_id)
        .limit(1)
        .execute()
    )
    existing_rows = existing_res.data or []
    if not existing_rows:
        raise HTTPException(404, "qa_schedule not found for this item")
    existing = existing_rows[0]

    # Merge patch into existing → effective state
    effective = {**existing, **data}
    _validate_effective_schedule(effective)

    # Canonicalize: force fields that must be NULL per frequency_type
    ft = effective.get("frequency_type")
    if ft == "MANUAL":
        data["enabled"] = False
        data["frequency_value"] = None
        data["anchor_time"] = None
        data["day_of_week"] = None
    elif ft == "DAILY":
        data["frequency_value"] = None
        data["day_of_week"] = None
    elif ft == "WEEKLY":
        data["frequency_value"] = None
    elif ft in ("MINUTES", "HOURLY"):
        data["day_of_week"] = None

    # next_run_at는 항상 NULL로 강제 (Phase 2-E scheduler authority)
    data["next_run_at"] = None
    data["updated_at"] = now_kst().isoformat()

    res = (
        supabase.table("qa_schedules")
        .update(data)
        .eq("qa_item_id", qa_item_id)
        .execute()
    )
    rows = res.data or []
    if not rows:
        raise HTTPException(404, "qa_schedule not found for this item")
    return rows[0]


# ── Runs ──────────────────────────────────────────────────────────────────────

def list_runs(
    supabase,
    run_status:   Optional[str] = None,
    trigger_type: Optional[str] = None,
    from_date:    Optional[str] = None,
    to_date:      Optional[str] = None,
    page:         int           = 1,
    page_size:    int           = 20,
) -> Dict[str, Any]:
    off = (page - 1) * page_size
    q = supabase.table("qa_runs").select(_RUN_COLS, count="exact")
    if run_status:
        q = q.eq("run_status", run_status)
    if trigger_type:
        q = q.eq("trigger_type", trigger_type)
    if from_date:
        q = q.gte("requested_at", from_date)
    if to_date:
        q = q.lte("requested_at", to_date)
    res = q.order("requested_at", desc=True).range(off, off + page_size - 1).execute()
    items = res.data or []
    total = res.count if res.count is not None else len(items)
    total_pages = (total + page_size - 1) // page_size

    # Bulk enrich with target_count / result_count / effective_counts — no N+1
    if items:
        run_ids = [r["id"] for r in items]
        tgt_res = (
            supabase.table("qa_run_targets")
            .select("run_id")
            .in_("run_id", run_ids)
            .execute()
        )
        rst_res = (
            supabase.table("qa_run_results")
            .select("run_id, qa_item_id, result_status, attempt")
            .in_("run_id", run_ids)
            .execute()
        )

        tgt_counts: Dict[str, int] = defaultdict(int)
        for t in (tgt_res.data or []):
            tgt_counts[t["run_id"]] += 1

        rst_by_run_item: Dict[str, Dict[str, List]] = defaultdict(lambda: defaultdict(list))
        for r in (rst_res.data or []):
            rst_by_run_item[r["run_id"]][r["qa_item_id"]].append(r)

        for run in items:
            rid = run["id"]
            run["target_count"] = tgt_counts.get(rid, 0)
            item_results = rst_by_run_item.get(rid, {})
            run["result_count"] = len(item_results)
            eff_counts: Dict[str, int] = defaultdict(int)
            for item_id, attempts in item_results.items():
                sorted_a = sorted(attempts, key=lambda a: a.get("attempt", 1))
                eff_counts[derive_effective_status(sorted_a)] += 1
            run["effective_counts"] = dict(eff_counts)

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
        raise HTTPException(404, "qa_run not found")
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

    # Enrich targets with item info (scenario_id, site_code, name, effective_status)
    target_item_ids = [t["qa_item_id"] for t in targets]
    items_map: Dict[str, Any] = {}
    if target_item_ids:
        itm_res = (
            supabase.table("qa_items")
            .select("id, scenario_id, site_code, name")
            .in_("id", target_item_ids)
            .execute()
        )
        items_map = {i["id"]: i for i in (itm_res.data or [])}

    attempts_by_item: Dict[str, List] = defaultdict(list)
    for r in results:
        attempts_by_item[r["qa_item_id"]].append(r)
        r.pop("flaky", None)  # clean up before re-derive

    # Derive FLAKY per item on result rows
    for item_id, attempts in attempts_by_item.items():
        sorted_a = sorted(attempts, key=lambda a: a.get("attempt", 1))
        if derive_effective_status(sorted_a) == "FLAKY":
            for a in attempts:
                a["flaky"] = True

    for target in targets:
        iid = target["qa_item_id"]
        item = items_map.get(iid, {})
        target["scenario_id"] = item.get("scenario_id")
        target["site_code"] = item.get("site_code")
        target["name"] = item.get("name")
        sorted_a = sorted(attempts_by_item.get(iid, []), key=lambda a: a.get("attempt", 1))
        target["effective_status"] = derive_effective_status(sorted_a)

    run["targets"] = targets
    run["results"] = results
    return run


def create_run(
    supabase,
    requested_by: str,
    qa_item_ids:  List[str],
) -> Dict[str, Any]:
    """MANUAL run 생성.

    client authority 고정:
      trigger_type = MANUAL
      requested_by = current user id
      ordinal = 1..N
    """
    if not qa_item_ids:
        raise HTTPException(422, "qa_item_ids가 비어있습니다")
    if len(qa_item_ids) > 100:
        raise HTTPException(422, "qa_item_ids는 최대 100건입니다")
    if len(qa_item_ids) != len(set(qa_item_ids)):
        raise HTTPException(422, "qa_item_ids에 중복이 있습니다")

    items_res = (
        supabase.table("qa_items")
        .select("id, enabled")
        .in_("id", qa_item_ids)
        .execute()
    )
    found = {r["id"]: r for r in (items_res.data or [])}
    missing = [qid for qid in qa_item_ids if qid not in found]
    if missing:
        raise HTTPException(422, f"존재하지 않는 qa_item_ids: {missing}")
    disabled = [qid for qid in qa_item_ids if not found[qid]["enabled"]]
    if disabled:
        raise HTTPException(422, f"disabled item은 run에 포함할 수 없습니다: {disabled}")

    now = now_kst().isoformat()
    run_row = {
        "trigger_type": "MANUAL",
        "run_status":   "QUEUED",
        "requested_by": requested_by,
        "requested_at": now,
        "created_at":   now,
        "updated_at":   now,
    }
    run_res = supabase.table("qa_runs").insert(run_row).execute()
    if not run_res.data:
        raise HTTPException(500, "qa_run 생성 실패")
    run = run_res.data[0]
    run_id = run["id"]

    target_rows = [
        {
            "run_id":     run_id,
            "qa_item_id": qid,
            "ordinal":    idx + 1,
            "created_at": now,
        }
        for idx, qid in enumerate(qa_item_ids)
    ]

    try:
        supabase.table("qa_run_targets").insert(target_rows).execute()
    except Exception as e:
        log.error("[qa_control] target insert failed for run %s, compensating: %s", run_id, e)
        supabase.table("qa_runs").delete().eq("id", run_id).execute()
        raise HTTPException(500, "qa_run_targets 생성 실패 — run 롤백됨")

    run["targets"] = target_rows
    return run


# ── Status transition event matrix ───────────────────────────────────────────

_TRANSITION_EVENTS: Dict[tuple, str] = {
    # → FAIL
    ("NEVER_RUN", "FAIL"): "QA_FAIL_DETECTED",
    ("PASS",      "FAIL"): "QA_FAIL_DETECTED",
    ("SKIPPED",   "FAIL"): "QA_FAIL_DETECTED",
    ("BLOCKED",   "FAIL"): "QA_FAIL_DETECTED",
    ("FLAKY",     "FAIL"): "QA_FAIL_DETECTED",
    # → BLOCKED
    ("NEVER_RUN", "BLOCKED"): "QA_BLOCKED_DETECTED",
    ("PASS",      "BLOCKED"): "QA_BLOCKED_DETECTED",
    ("SKIPPED",   "BLOCKED"): "QA_BLOCKED_DETECTED",
    ("FAIL",      "BLOCKED"): "QA_BLOCKED_DETECTED",
    # → FLAKY
    ("NEVER_RUN", "FLAKY"): "QA_FLAKY_DETECTED",
    ("PASS",      "FLAKY"): "QA_FLAKY_DETECTED",
    ("SKIPPED",   "FLAKY"): "QA_FLAKY_DETECTED",
    ("FAIL",      "FLAKY"): "QA_FLAKY_DETECTED",
    ("BLOCKED",   "FLAKY"): "QA_FLAKY_DETECTED",
    # → PASS (recovery)
    ("FAIL",    "PASS"): "QA_RECOVERED",
    ("BLOCKED", "PASS"): "QA_RECOVERED",
    ("FLAKY",   "PASS"): "QA_RECOVERED",
}


def _get_transition_event(prev: str, new: str) -> Optional[str]:
    return _TRANSITION_EVENTS.get((prev, new))


def _latest_run_effective_status(by_run: Dict[str, List]) -> str:
    """Given run_id → attempts mapping, compute effective status of the latest run."""
    if not by_run:
        return "NEVER_RUN"
    latest_run_id = max(
        by_run.keys(),
        key=lambda rid: max((r.get("checked_at") or "") for r in by_run[rid]),
    )
    attempts = sorted(by_run[latest_run_id], key=lambda a: a.get("attempt", 1))
    return derive_effective_status(attempts)


# ── Internal: Result Callback ─────────────────────────────────────────────────

def _check_final_run_replay(
    run: Dict,
    github_run_id:      Optional[int],
    github_run_attempt: Optional[int],
    head_sha:           Optional[str],
    branch_name:        Optional[str],
    run_started_at:     Optional[str],
    run_finished_at:    Optional[str],
    run_error_code:     Optional[str],
    run_error_summary:  Optional[str],
) -> None:
    """Final state exact replay guard. Any non-None incoming field that differs from stored → 409."""
    mismatches = []
    for key, val in [
        ("github_run_id",      github_run_id),
        ("github_run_attempt", github_run_attempt),
        ("head_sha",           head_sha),
        ("branch_name",        branch_name),
        ("started_at",         run_started_at),
        ("finished_at",        run_finished_at),
        ("error_code",         run_error_code),
    ]:
        if val is not None and run.get(key) != val:
            mismatches.append(key)
    if run_error_summary is not None:
        if redact_error_summary(run_error_summary) != redact_error_summary(run.get("error_summary")):
            mismatches.append("error_summary")
    if mismatches:
        raise HTTPException(409, {"message": "FINAL_RUN_CONFLICT", "fields": mismatches})


def _results_match(existing: Dict, incoming: Dict) -> bool:
    """canonical evidence 전체 동일 여부."""
    for field in ("result_status", "duration_ms", "http_status", "error_code", "artifact_ref", "started_at", "finished_at"):
        if existing.get(field) != incoming.get(field):
            return False
    if redact_error_summary(existing.get("error_summary")) != redact_error_summary(incoming.get("error_summary")):
        return False
    return True


def apply_results(
    supabase,
    run_id:             str,
    new_status:         Optional[str],
    github_run_id:      Optional[int],
    github_run_attempt: Optional[int],
    head_sha:           Optional[str],
    branch_name:        Optional[str],
    run_started_at:     Optional[str],
    run_finished_at:    Optional[str],
    run_error_code:     Optional[str],
    run_error_summary:  Optional[str],
    results:            List[Dict[str, Any]],
) -> Dict[str, Any]:
    # GitHub identity pair check
    if (github_run_id is None) != (github_run_attempt is None):
        raise HTTPException(422, "github_run_id와 github_run_attempt는 함께 제공해야 합니다")

    run_res = (
        supabase.table("qa_runs").select(_RUN_COLS).eq("id", run_id).limit(1).execute()
    )
    if not run_res.data:
        raise HTTPException(404, "qa_run not found")
    run = run_res.data[0]
    current_status = run["run_status"]

    # Lifecycle validation + final replay guard
    if current_status in _FINAL_STATUSES:
        if new_status is not None and new_status != current_status:
            raise HTTPException(409, f"run {run_id} is already in final status {current_status}")
        _check_final_run_replay(
            run, github_run_id, github_run_attempt, head_sha, branch_name,
            run_started_at, run_finished_at, run_error_code, run_error_summary,
        )
    elif new_status:
        if new_status not in _VALID_STATUSES:
            raise HTTPException(422, f"invalid run_status: {new_status}")
        allowed = _VALID_TRANSITIONS.get(current_status, frozenset())
        if new_status != current_status and new_status not in allowed:
            raise HTTPException(422, f"invalid transition {current_status} → {new_status}")

    # GitHub identity guard
    if github_run_id is not None:
        existing_gri = run.get("github_run_id")
        existing_gra = run.get("github_run_attempt")
        if existing_gri is None:
            pass  # First binding — allowed
        elif existing_gri != github_run_id or existing_gra != github_run_attempt:
            raise HTTPException(409, "GITHUB_IDENTITY_MISMATCH")
        # else: same identity — idempotent

    # Run-level error notification
    run_notification: Optional[Dict[str, Any]] = None
    if new_status == "ERROR" and current_status not in _FINAL_STATUSES:
        run_notification = {
            "event_type":   "QA_RUN_ERROR",
            "run_id":       run_id,
            "run_status":   "ERROR",
            "trigger_type": run.get("trigger_type"),
            "github_run_id": github_run_id if github_run_id is not None else run.get("github_run_id"),
            "head_sha":     head_sha or run.get("head_sha"),
            "error_summary": redact_error_summary(run_error_summary or run.get("error_summary")),
        }

    # Resolve scenario_id → qa_item_id
    scenario_ids = [r["scenario_id"] for r in results]
    resolved: List[Dict[str, Any]] = []
    if scenario_ids:
        items_res = (
            supabase.table("qa_items")
            .select("id, scenario_id, site_code, name, enabled")
            .in_("scenario_id", scenario_ids)
            .execute()
        )
        sid_to_item = {i["scenario_id"]: i for i in (items_res.data or [])}
        not_found = [sid for sid in scenario_ids if sid not in sid_to_item]
        if not_found:
            raise HTTPException(422, f"scenario_id not found: {not_found}")
        for r in results:
            rc = dict(r)
            rc["qa_item_id"] = sid_to_item[r["scenario_id"]]["id"]
            resolved.append(rc)
    else:
        resolved = results

    # Validate result target membership (API integrity before DB FK)
    if resolved:
        tgts_res = (
            supabase.table("qa_run_targets")
            .select("qa_item_id")
            .eq("run_id", run_id)
            .execute()
        )
        target_ids = {t["qa_item_id"] for t in (tgts_res.data or [])}
        non_targeted = [r["qa_item_id"] for r in resolved if r["qa_item_id"] not in target_ids]
        if non_targeted:
            raise HTTPException(409, {"message": "RESULT_NOT_TARGETED", "qa_item_ids": non_targeted})

    # Validate artifact_refs
    for r in resolved:
        _validate_artifact_ref(r.get("artifact_ref"))

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

    for r in resolved:
        qa_item_id = r["qa_item_id"]
        attempt = r.get("attempt", 1)
        key = (qa_item_id, attempt)

        if key in existing_map:
            if not _results_match(existing_map[key], r):
                conflicts.append({
                    "qa_item_id":     qa_item_id,
                    "attempt":        attempt,
                    "conflict":       "RESULT_CONFLICT",
                })
            else:
                skipped += 1
        else:
            # No new inserts into a finalized run
            if current_status in _FINAL_STATUSES:
                raise HTTPException(409, f"run {run_id} is finalized — new results cannot be added")
            to_insert.append({
                "run_id":        run_id,
                "qa_item_id":    qa_item_id,
                "result_status": r["result_status"],
                "attempt":       attempt,
                "duration_ms":   r.get("duration_ms"),
                "http_status":   r.get("http_status"),
                "error_code":    r.get("error_code"),
                "error_summary": redact_error_summary(r.get("error_summary")),
                "artifact_ref":  r.get("artifact_ref"),
                "started_at":    r.get("started_at"),
                "finished_at":   r.get("finished_at"),
                "checked_at":    r.get("checked_at") or now,
                "created_at":    now,
            })

    if conflicts:
        raise HTTPException(409, {"message": "RESULT_CONFLICT", "conflicts": conflicts})

    # Item status transition notifications — N+1 safe: single IN_ bulk history query
    notifications: List[Dict[str, Any]] = []
    if to_insert:
        notify_item_ids = list({r["qa_item_id"] for r in to_insert})
        hist_res = (
            supabase.table("qa_run_results")
            .select("run_id, qa_item_id, result_status, attempt, checked_at")
            .in_("qa_item_id", notify_item_ids)
            .execute()
        )
        all_hist = hist_res.data or []

        hist_by_item: Dict[str, Dict[str, List]] = defaultdict(lambda: defaultdict(list))
        for r in all_hist:
            hist_by_item[r["qa_item_id"]][r["run_id"]].append(r)

        new_by_item: Dict[str, List] = defaultdict(list)
        for r in to_insert:
            new_by_item[r["qa_item_id"]].append(r)

        for item_id in notify_item_ids:
            by_run_existing = dict(hist_by_item[item_id])
            prev_eff = _latest_run_effective_status(by_run_existing)

            by_run_new: Dict[str, List] = {k: list(v) for k, v in by_run_existing.items()}
            by_run_new.setdefault(run_id, [])
            by_run_new[run_id] = list(by_run_existing.get(run_id, [])) + new_by_item[item_id]
            new_eff = _latest_run_effective_status(by_run_new)

            event_type = _get_transition_event(prev_eff, new_eff)
            if event_type:
                item_meta = next(
                    (i for i in sid_to_item.values() if i["id"] == item_id),
                    {},
                )
                sorted_new = sorted(new_by_item[item_id], key=lambda a: a.get("attempt", 1))
                last = sorted_new[-1] if sorted_new else {}
                notifications.append({
                    "event_type":      event_type,
                    "qa_item_id":      item_id,
                    "scenario_id":     item_meta.get("scenario_id"),
                    "site_code":       item_meta.get("site_code"),
                    "name":            item_meta.get("name"),
                    "previous_status": prev_eff,
                    "new_status":      new_eff,
                    "run_id":          run_id,
                    "trigger_type":    run.get("trigger_type"),
                    "github_run_id":   github_run_id if github_run_id is not None else run.get("github_run_id"),
                    "head_sha":        head_sha or run.get("head_sha"),
                    "error_summary":   last.get("error_summary"),
                    "duration_ms":     last.get("duration_ms"),
                })

    if to_insert:
        supabase.table("qa_run_results").insert(to_insert).execute()

    # Update run
    run_patch: Dict[str, Any] = {"updated_at": now}
    if new_status and new_status != current_status:
        run_patch["run_status"] = new_status
        if new_status == "RUNNING" and not run.get("started_at"):
            run_patch["started_at"] = run_started_at or now
        elif new_status in _FINAL_STATUSES and not run.get("finished_at"):
            run_patch["finished_at"] = run_finished_at or now
    if head_sha is not None:
        run_patch["head_sha"] = head_sha
    if branch_name is not None:
        run_patch["branch_name"] = branch_name
    if run_error_code is not None:
        run_patch["error_code"] = run_error_code
    if run_error_summary is not None:
        run_patch["error_summary"] = redact_error_summary(run_error_summary)
    if github_run_id is not None and run.get("github_run_id") is None:
        run_patch["github_run_id"] = github_run_id
        run_patch["github_run_attempt"] = github_run_attempt

    supabase.table("qa_runs").update(run_patch).eq("id", run_id).execute()

    return {
        "run_id":           run_id,
        "inserted":         len(to_insert),
        "skipped":          skipped,
        "notifications":    notifications,
        "run_notification": run_notification,
    }
