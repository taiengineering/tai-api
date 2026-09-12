"""Daily KOSHA safety-library orchestration — WO-SAFETY-LIBRARY-002 WP-DL+A1.

Existing pipeline only: sync → latest COMPLETED → detail enrichment → R2 storage.
Does not reimplement collection, KOGL, matching, or storage rules.
"""
from __future__ import annotations

import os
import socket
import uuid
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import urljoin

from services.kosha_safety_material_sync import kosha_service_key, media_list_params
from services.kosha_safety_materials.enrichment import DEFAULT_BATCH, select_pending
from services.time import now_kst

KOSHA_LIST_PATH = "selectMediaList01/getselectMediaList01"
KOSHA_BASE = "https://apis.data.go.kr/B552468"
DETAIL_SYSTEMIC = frozenset({
    "QUOTA_BLOCKED",
    "ACCESS_BLOCKED",
    "UPSTREAM_UNSTABLE",
    "TRANSIENT_UPSTREAM_FAILURE",
    "MEDSEQ_MISMATCH",
    "SNAPSHOT_INVALID",
    "CONTRACT_VIOLATION",
    "DB_FAILURE",
    "AUTH",
    "QUOTA",
    "INTEGRITY",
})
STORAGE_SYSTEMIC = frozenset({
    "QUOTA_BLOCKED",
    "ACCESS_BLOCKED",
    "TRANSIENT_UPSTREAM_FAILURE",
    "R2_ACCESS_BLOCKED",
    "R2_TRANSIENT",
    "R2_HEAD_AUTH",
    "PENDING_NO_PROGRESS",
    "SNAPSHOT_INVALID",
    "CONTRACT_VIOLATION",
})
SYNC_OK = frozenset({"COMPLETED", "SNAPSHOT_NO_CHANGE"})
MAX_DETAIL_BATCHES = 200
MAX_STORAGE_BATCHES = 500
EXIT_OK = 0
EXIT_FAIL = 2

GetFn = Callable[..., tuple[int, str]]
PreflightFn = Callable[[], dict]
SyncFn = Callable[..., Awaitable[dict]]
LatestFn = Callable[[], Optional[dict]]
DetailBatchFn = Callable[..., dict]
StorageFn = Callable[..., dict]
ConsistencyFn = Callable[..., dict]


def try_acquire_lock(path: str):
    """Non-blocking exclusive lock. Returns an open file or None if already held."""
    import fcntl

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fh = open(path, "a+")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return None
    fh.write(str(os.getpid()))
    fh.flush()
    return fh


def release_lock(fh) -> None:
    if fh is None:
        return
    import fcntl

    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    finally:
        fh.close()


def _looks_like_code10(text: str) -> bool:
    t = (text or "").lower()
    if "code10" in t.replace(" ", ""):
        return True
    if "<resultcode>10</resultcode>" in t.replace(" ", ""):
        return True
    if '"resultcode":"10"' in t.replace(" ", "").replace("'", '"'):
        return True
    if "service key is not registered" in t:
        return True
    return False


def network_preflight(*, service_key: str | None = None, get_fn: GetFn | None = None) -> dict:
    """KOSHA list page=1 only. Never writes. Does not create a snapshot."""
    key = (service_key if service_key is not None else kosha_service_key()) or ""
    if not key.strip():
        return {"ok": False, "code": "NETWORK_PREFLIGHT_FAIL", "reason": "SERVICE_KEY_MISSING", "http_status": None}
    if get_fn is None:
        from services.kr_public_api import kr_get
        get_fn = kr_get
    url = urljoin(KOSHA_BASE + "/", KOSHA_LIST_PATH)
    params = {**media_list_params(1, 1), "serviceKey": key}
    try:
        status, text = get_fn(url, params=params, timeout=30)
    except Exception as e:
        return {
            "ok": False,
            "code": "NETWORK_PREFLIGHT_FAIL",
            "reason": type(e).__name__,
            "http_status": None,
        }
    body = text or ""
    if int(status) in (401, 403):
        return {"ok": False, "code": "NETWORK_PREFLIGHT_FAIL", "reason": "AUTH", "http_status": status}
    if int(status) == 429:
        return {"ok": False, "code": "NETWORK_PREFLIGHT_FAIL", "reason": "QUOTA", "http_status": status}
    if int(status) >= 500:
        return {"ok": False, "code": "NETWORK_PREFLIGHT_FAIL", "reason": "UPSTREAM_5XX", "http_status": status}
    if int(status) >= 400:
        return {"ok": False, "code": "NETWORK_PREFLIGHT_FAIL", "reason": f"HTTP_{status}", "http_status": status}
    if _looks_like_code10(body):
        return {"ok": False, "code": "NETWORK_PREFLIGHT_FAIL", "reason": "CODE10", "http_status": status}
    return {"ok": True, "code": "NETWORK_PREFLIGHT_OK", "reason": None, "http_status": status}


def wrap_detail_batch(store, *, fetch_detail_fn=None, fetch_attachments_fn=None, sleeper=None, log=print):
    """Adapter: run_one_batch + pending before/after. No enrichment logic copied."""
    from services.kosha_safety_materials.enrichment import run_one_batch

    def _run(*, snapshot_id: str, batch_size: int) -> dict:
        pending_before = len(select_pending(store, snapshot_id, limit=10**9))
        kw: dict[str, Any] = {
            "run_snapshot_id": snapshot_id,
            "batch_size": batch_size,
            "dry_run": False,
            "log": log,
        }
        if fetch_detail_fn is not None:
            kw["fetch_detail_fn"] = fetch_detail_fn
        if fetch_attachments_fn is not None:
            kw["fetch_attachments_fn"] = fetch_attachments_fn
        if sleeper is not None:
            kw["sleeper"] = sleeper
        out = run_one_batch(store, **kw)
        out["pending_before"] = pending_before
        out["pending_after"] = int(out.get("remaining") or 0)
        return out

    return _run


def _report_base(*, run_id: str, started: str, host: str) -> dict:
    return {
        "run_id": run_id,
        "started_at_kst": started,
        "ended_at_kst": None,
        "execution_host": host,
        "network_preflight": None,
        "snapshot_result": None,
        "snapshot_id": None,
        "snapshot_hash": None,
        "snapshot_membership": None,
        "catalog_new": 0,
        "detail_batches": 0,
        "detail_new": 0,
        "detail_pending": None,
        "storage_batches": 0,
        "storage_completed": 0,
        "storage_pending": None,
        "new_hold_count": 0,
        "existing_open_holds": None,
        "final_status": None,
        "failure_code": None,
        "r2_overwrite": 0,
        "r2_delete": 0,
    }


def _finish(report: dict, status: str, code: int, *, failure: str | None = None) -> tuple[dict, int]:
    report["final_status"] = status
    report["failure_code"] = failure
    report["ended_at_kst"] = now_kst().isoformat()
    return report, code


async def run_daily(
    *,
    preflight_fn: PreflightFn,
    sync_fn: SyncFn,
    latest_completed_fn: LatestFn,
    detail_batch_fn: DetailBatchFn,
    storage_fn: StorageFn,
    consistency_fn: ConsistencyFn,
    host: str | None = None,
    detail_batch_size: int = DEFAULT_BATCH,
    max_detail_batches: int = MAX_DETAIL_BATCHES,
) -> tuple[dict, int]:
    run_id = str(uuid.uuid4())
    started = now_kst().isoformat()
    report = _report_base(run_id=run_id, started=started, host=host or socket.gethostname())

    pre = preflight_fn()
    report["network_preflight"] = pre.get("code") or ("NETWORK_PREFLIGHT_OK" if pre.get("ok") else "NETWORK_PREFLIGHT_FAIL")
    if not pre.get("ok"):
        return _finish(report, "NETWORK_PREFLIGHT_FAIL", EXIT_FAIL, failure=pre.get("reason") or "NETWORK_PREFLIGHT_FAIL")

    sync_out = await sync_fn(dry_run=False, start_page=1)
    report["snapshot_result"] = sync_out.get("status")
    report["catalog_new"] = int(sync_out.get("catalog_dml") or sync_out.get("catalog_inserts_planned") or 0)
    if sync_out.get("status") not in SYNC_OK:
        return _finish(
            report, "SNAPSHOT_FAILED", EXIT_FAIL,
            failure=sync_out.get("failure_reason") or sync_out.get("status"),
        )

    latest = latest_completed_fn()
    if not latest or latest.get("status") != "COMPLETED":
        return _finish(report, "NO_COMPLETED_SNAPSHOT", EXIT_FAIL, failure="NO_COMPLETED_SNAPSHOT")
    snapshot_id = latest["id"]
    report["snapshot_id"] = snapshot_id
    report["snapshot_hash"] = latest.get("snapshot_hash") or sync_out.get("snapshot_hash")
    report["snapshot_membership"] = int(latest.get("unique_count") or 0)

    detail_new = 0
    last_detail = None
    for _ in range(max(1, int(max_detail_batches))):
        last_detail = detail_batch_fn(snapshot_id=snapshot_id, batch_size=detail_batch_size)
        report["detail_batches"] += 1
        added = int(last_detail.get("new_detail_rows") or 0)
        detail_new += added
        pending_before = int(last_detail.get("pending_before") if last_detail.get("pending_before") is not None else 0)
        pending_after = int(
            last_detail.get("pending_after")
            if last_detail.get("pending_after") is not None
            else last_detail.get("remaining") or 0
        )
        report["detail_pending"] = pending_after
        status = last_detail.get("status")
        if status in DETAIL_SYSTEMIC or last_detail.get("stop_reason") in DETAIL_SYSTEMIC:
            report["detail_new"] = detail_new
            return _finish(report, "DETAIL_STOP", EXIT_FAIL, failure=status or last_detail.get("stop_reason"))
        if status in ("FULL_SWEEP_COMPLETE",) or pending_after == 0:
            break
        if pending_after >= pending_before and added == 0:
            report["detail_new"] = detail_new
            return _finish(report, "NO_PROGRESS", EXIT_FAIL, failure="NO_PROGRESS")
    else:
        report["detail_new"] = detail_new
        return _finish(report, "NO_PROGRESS", EXIT_FAIL, failure="DETAIL_MAX_BATCHES")
    report["detail_new"] = detail_new
    if last_detail is not None:
        report["detail_pending"] = int(last_detail.get("pending_after") if last_detail.get("pending_after") is not None else last_detail.get("remaining") or 0)

    try:
        storage_out = storage_fn(snapshot_id=snapshot_id)
    except Exception as e:
        reason = getattr(e, "reason", None) or getattr(e, "code", None) or type(e).__name__
        report["storage_pending"] = None
        return _finish(report, "STORAGE_STOP", EXIT_FAIL, failure=str(reason))
    st = storage_out.get("status")
    if st in STORAGE_SYSTEMIC or storage_out.get("stop_reason") in STORAGE_SYSTEMIC:
        return _finish(report, "STORAGE_STOP", EXIT_FAIL, failure=st or storage_out.get("stop_reason"))
    report["storage_batches"] = int(storage_out.get("batches") or 0)
    report["storage_completed"] = int(storage_out.get("stored") or storage_out.get("storage_completed") or 0)
    report["storage_pending"] = int(
        storage_out.get("actionable_pending")
        if storage_out.get("actionable_pending") is not None
        else storage_out.get("remaining") or 0
    )
    report["new_hold_count"] = int(storage_out.get("HOLD") or storage_out.get("new_hold_count") or 0)
    report["existing_open_holds"] = storage_out.get("existing_open_holds", storage_out.get("held"))
    report["r2_overwrite"] = int(storage_out.get("r2_overwrite") or 0)
    report["r2_delete"] = int(storage_out.get("r2_delete") or 0)
    if int(report["r2_overwrite"] or 0) or int(report["r2_delete"] or 0):
        return _finish(report, "STORAGE_STOP", EXIT_FAIL, failure="R2_MUTATION_FORBIDDEN")

    cons = consistency_fn(snapshot_id=snapshot_id)
    report["snapshot_membership"] = cons.get("membership", report["snapshot_membership"])
    if not cons.get("ok"):
        return _finish(report, "CONSISTENCY_FAIL", EXIT_FAIL, failure=cons.get("code") or "CONSISTENCY_FAIL")
    report["list_universe"] = cons.get("list_universe")
    report["stats_universe"] = cons.get("stats_universe")
    report["historical_leak"] = cons.get("historical_leak", 0)
    return _finish(report, "SUCCESS", EXIT_OK)


def production_consistency(*, snapshot_store, display_store) -> Callable[..., dict]:
    from services.kosha_safety_materials.display import stats_current_materials
    from services.kosha_safety_materials.enrichment import snapshot_precondition

    def _run(*, snapshot_id: str) -> dict:
        pre = snapshot_precondition(snapshot_store)
        snap = pre["snapshot"]
        if snap.get("id") != snapshot_id or snap.get("status") != "COMPLETED":
            return {"ok": False, "code": "SNAPSHOT_NOT_COMPLETED"}
        membership = int(pre["membership_count"])
        stats = stats_current_materials(display_store)
        if stats.get("snapshot_id") != snapshot_id:
            return {"ok": False, "code": "STATS_SNAPSHOT_MISMATCH", "membership": membership}
        total = int(stats.get("total") or 0)
        leak = 0 if total == membership else abs(total - membership)
        if leak:
            return {
                "ok": False,
                "code": "MEMBERSHIP_STATS_MISMATCH",
                "membership": membership,
                "list_universe": total,
                "stats_universe": total,
                "historical_leak": leak,
            }
        return {
            "ok": True,
            "membership": membership,
            "list_universe": total,
            "stats_universe": total,
            "historical_leak": 0,
        }

    return _run
