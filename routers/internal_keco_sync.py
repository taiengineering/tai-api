"""Internal KECO Reference Sync API — CHEM-WO-DATA-KECO-003.

엔드포인트:
  GET  /internal/reference/keco/status             — target 현황 조회
  GET  /internal/reference/keco/runs/{run_id}      — run 상세 조회
  POST /internal/reference/keco/sync/{cas}         — 단일 CAS 즉시 수집
  POST /internal/reference/keco/retry              — RETRY/FAILED 대상 재처리
  POST /internal/reference/keco/refresh            — due targets 갱신

인증: X-Internal-Secret 헤더 (INTERNAL_API_SECRET env).
단일 HTTP request에서 전체 bulk 실행 금지 — bounded batch만 허용.
KOSHA mutation 금지. Product DB write 금지.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel

log = logging.getLogger("internal_keco_sync")

router = APIRouter(prefix="/internal/reference/keco", tags=["internal-keco-sync"])

# Server-side hard cap per HTTP request
_MAX_SINGLE_REQUEST_TARGETS = 100


def _auth(x_internal_secret: Optional[str]) -> None:
    expected = os.environ.get("INTERNAL_API_SECRET")
    if not expected or x_internal_secret != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid internal secret")


def _make_client():
    from services.keco_chemical.client import KecoChemicalClient
    return KecoChemicalClient()


def _make_store():
    from services.keco_chemical.store import KecoReferenceStore
    return KecoReferenceStore()


def _make_budget():
    from services.keco_chemical.sync import RequestBudget
    return RequestBudget.from_env()


# ── GET /status ───────────────────────────────────────────────────────────────

@router.get("/status")
def get_status(
    x_internal_secret: Optional[str] = Header(None, alias="X-Internal-Secret"),
):
    """target 상태 집계 + active run 여부 조회."""
    _auth(x_internal_secret)
    store = _make_store()
    summary = store.get_status_summary()
    is_bulk_active = store.has_active_run("INITIAL_BULK")
    is_refresh_active = store.has_active_run("SCHEDULED_REFRESH")
    return {
        "target_counts": summary,
        "is_initial_bulk_active": is_bulk_active,
        "is_refresh_active": is_refresh_active,
    }


# ── GET /runs/{run_id} ────────────────────────────────────────────────────────

@router.get("/runs/{run_id}")
def get_run(
    run_id: str,
    x_internal_secret: Optional[str] = Header(None, alias="X-Internal-Secret"),
):
    """run_id로 ingestion run 상세 조회."""
    _auth(x_internal_secret)
    store = _make_store()
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    # Strip any sensitive fields before returning
    run.pop("error_message", None)
    return {"run": run}


# ── POST /sync/{cas} ──────────────────────────────────────────────────────────

@router.post("/sync/{cas}")
def sync_single_cas(
    cas: str,
    x_internal_secret: Optional[str] = Header(None, alias="X-Internal-Secret"),
):
    """단일 CAS 즉시 수집 (운영 긴급 재수집용). 전체 bulk trigger 아님."""
    _auth(x_internal_secret)

    if not cas or not cas.strip():
        raise HTTPException(status_code=400, detail="CAS must not be blank")

    from services.keco_chemical.contract import (
        RUN_TYPE_MANUAL_SINGLE,
        TARGET_TYPE_CAS,
    )
    from services.keco_chemical.sync import sync_one_target

    client = _make_client()
    store = _make_store()
    budget = _make_budget()

    run_id = store.start_run(RUN_TYPE_MANUAL_SINGLE, search_gubun="2", search_nm=cas.strip())

    # Ensure target exists (create PENDING if not)
    db = None
    target: Optional[dict] = None
    try:
        from services.keco_chemical.store import _get_supabase_client
        _client = _get_supabase_client()
        db_sc = _client.schema("msds_ref")
        rows = (
            db_sc.table("keco_collection_targets")
            .select("id,target_type,target_value,attempt_count")
            .eq("target_type", TARGET_TYPE_CAS)
            .eq("target_value", cas.strip())
            .limit(1)
            .execute()
        )
        if rows.data:
            target = rows.data[0]
        else:
            # Create on-demand target
            from services.time import now_kst, serialize_business_datetime
            now = serialize_business_datetime(now_kst())
            ins = db_sc.table("keco_collection_targets").insert({
                "target_type": TARGET_TYPE_CAS,
                "target_value": cas.strip(),
                "status": "PENDING",
                "created_at": now,
                "updated_at": now,
            }).execute()
            target = ins.data[0] if ins.data else {"id": None, "target_type": TARGET_TYPE_CAS, "target_value": cas.strip(), "attempt_count": 0}
    except Exception as exc:
        store.fail_run(run_id, "STORE_ERROR", str(exc))
        raise HTTPException(status_code=500, detail="target lookup failed") from exc

    try:
        result = sync_one_target(client, store, target, run_id, budget)
        store.complete_run(run_id, result.api_requests, result.source_items, {
            "status": result.status,
            "new": result.new_count,
            "unchanged": result.unchanged_count,
            "changed": result.changed_count,
        })
        return {
            "run_id": run_id,
            "cas": cas.strip(),
            "status": result.status,
            "api_requests": result.api_requests,
            "source_items": result.source_items,
            "new_count": result.new_count,
            "unchanged_count": result.unchanged_count,
            "changed_count": result.changed_count,
            "fact_insert_count": result.fact_insert_count,
        }
    except Exception as exc:
        store.fail_run(run_id, "UNEXPECTED_ERROR", str(exc))
        raise HTTPException(status_code=500, detail="sync failed") from exc


# ── POST /retry ───────────────────────────────────────────────────────────────

class RetryRequest(BaseModel):
    limit: int = 20


@router.post("/retry")
def retry_targets(
    req: RetryRequest,
    x_internal_secret: Optional[str] = Header(None, alias="X-Internal-Secret"),
):
    """RETRY/FAILED targets 재처리. limit ≤ server-side max."""
    _auth(x_internal_secret)

    limit = min(req.limit, _MAX_SINGLE_REQUEST_TARGETS)
    if limit <= 0:
        raise HTTPException(status_code=400, detail="limit must be > 0")

    from services.keco_chemical.contract import (
        DEFAULT_STALE_RUNNING_MINUTES,
        RUN_TYPE_RETRY,
        STALE_RUNNING_MINUTES_ENV,
    )
    from services.keco_chemical.sync import sync_batch

    client = _make_client()
    store = _make_store()
    budget = _make_budget()

    import os as _os
    raw = (_os.getenv(STALE_RUNNING_MINUTES_ENV) or "").strip()
    try:
        stale_min = int(raw) if raw else DEFAULT_STALE_RUNNING_MINUTES
    except ValueError:
        stale_min = DEFAULT_STALE_RUNNING_MINUTES

    run_id = store.start_run(RUN_TYPE_RETRY)
    try:
        targets = store.claim_targets(limit, stale_min)
        result = sync_batch(client, store, targets, run_id, budget)
        result.run_type = RUN_TYPE_RETRY
        store.complete_run(run_id, result.requests, result.source_items, {
            "targets_selected": result.targets_selected,
            "targets_processed": result.targets_processed,
            "budget_used": result.budget_used,
        })
        return {
            "run_id": run_id,
            "limit": limit,
            "targets_selected": result.targets_selected,
            "targets_processed": result.targets_processed,
            "status": result.status,
            "requests": result.requests,
            "new": result.new,
            "unchanged": result.unchanged,
            "changed": result.changed,
            "retry": result.retry,
            "failed": result.failed,
        }
    except Exception as exc:
        store.fail_run(run_id, "UNEXPECTED_ERROR", str(exc))
        raise HTTPException(status_code=500, detail="retry failed") from exc


# ── POST /refresh ─────────────────────────────────────────────────────────────

class RefreshRequest(BaseModel):
    limit: Optional[int] = None


@router.post("/refresh")
def refresh_targets(
    req: RefreshRequest,
    x_internal_secret: Optional[str] = Header(None, alias="X-Internal-Secret"),
):
    """next_refresh_at <= now のdue targets 갱신. bounded. INITIAL_BULK active 시 skip."""
    _auth(x_internal_secret)

    max_t = None
    if req.limit is not None:
        max_t = min(req.limit, _MAX_SINGLE_REQUEST_TARGETS)

    from services.keco_chemical.sync import refresh_due_targets

    client = _make_client()
    store = _make_store()
    budget = _make_budget()

    try:
        result = refresh_due_targets(client, store, budget, max_targets=max_t)
        return {
            "run_id": result.run_id,
            "status": result.status,
            "targets_selected": result.targets_selected,
            "targets_processed": result.targets_processed,
            "requests": result.requests,
            "new": result.new,
            "unchanged": result.unchanged,
            "changed": result.changed,
            "budget_used": result.budget_used,
            "budget_remaining": result.budget_remaining,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail="refresh failed") from exc
