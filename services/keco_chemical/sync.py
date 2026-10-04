"""KECO Shared Sync Core — Mac Bulk / Railway API / Cron 공통 경로.

Mac Bulk CLI, Railway API, Railway Cron 모두 이 모듈만 호출한다.
수집 판단/파싱/저장/변경감지/재시도 로직을 중복 구현하지 않는다.

주요 공개 함수:
  sync_one_target     — 단일 CAS target 전체 수집 (pagination 포함)
  sync_batch          — claim한 target 목록을 순차 처리
  refresh_due_targets — next_refresh_at <= now 대상 처리

KECO API calls = 0 here — all API I/O delegated to KecoChemicalClient.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import List, Optional

from services.keco_chemical.budget import RequestBudget, RequestBudgetExceeded
from services.keco_chemical.client import KecoChemicalClient, KecoChemicalClientError
from services.keco_chemical.contract import (
    DEFAULT_CLAIM_BATCH_SIZE,
    DEFAULT_RATE_RETRY_BASE_SECONDS,
    DEFAULT_RATE_RETRY_MAX,
    DEFAULT_REFRESH_BATCH_SIZE,
    DEFAULT_REQUEST_BUDGET,
    DEFAULT_STALE_RUNNING_MINUTES,
    ERROR_RATE_LIMIT,
    MAX_PAGES_SAFETY_CAP,
    NON_RETRY_CODES,
    RATE_LIMIT_SECOND_CODE,
    RATE_RETRY_BASE_SECONDS_ENV,
    RATE_RETRY_MAX_ENV,
    REFRESH_BATCH_SIZE_ENV,
    REQUEST_BUDGET_ENV,
    RUN_TYPE_INITIAL_BULK,
    RUN_TYPE_MANUAL_SINGLE,
    RUN_TYPE_RETRY,
    RUN_TYPE_SCHEDULED_REFRESH,
    SEARCH_CAS,
    STALE_RUNNING_MINUTES_ENV,
    SYNC_PAGE_SIZE,
    TARGET_STATUS_CONFLICT,
    TARGET_STATUS_DONE,
    TARGET_STATUS_EMPTY,
    TARGET_STATUS_FAILED,
    TARGET_STATUS_RETRY,
)
from services.keco_chemical.store import KecoReferenceStore

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Result types
# ─────────────────────────────────────────────────────────────

@dataclass
class SyncTargetResult:
    target_id: str
    target_type: str
    target_value: str
    status: str          # DONE | EMPTY | CONFLICT | RETRY | FAILED
    api_requests: int    # physical HTTP attempts (including retries)
    source_items: int
    new_count: int
    unchanged_count: int
    changed_count: int
    fact_insert_count: int
    error: Optional[str] = None
    stop_batch: bool = False   # True = rate limit daily quota or budget exhausted → halt batch


@dataclass
class SyncBatchResult:
    run_id: str
    run_type: str
    targets_selected: int
    targets_processed: int
    requests: int
    new: int
    unchanged: int
    changed: int
    empty: int
    conflict: int
    retry: int
    failed: int
    source_items: int
    facts_inserted: int
    budget_used: int
    budget_remaining: int
    status: str                # COMPLETED | PARTIAL | FAILED
    results: List[SyncTargetResult] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────
# Core sync for one target
# ─────────────────────────────────────────────────────────────

def sync_one_target(
    client: KecoChemicalClient,
    store: KecoReferenceStore,
    target: dict,
    run_id: str,
    budget: RequestBudget,
) -> SyncTargetResult:
    """단일 CAS target 전체 수집.

    Pagination 전체를 읽고 → CAS match 확인 → persist_item 호출.
    budget 소진 시 RETRY로 마크하고 stop_batch=True 반환.
    rate limit daily (22) 시 RETRY + stop_batch=True.
    rate limit per-second (23) 시 bounded backoff retry, stop_batch=False.
    CAS mismatch 1건이라도 → CONFLICT (partial persist 금지).
    Pagination safety cap 초과 → RETRY (totalCount 미달시).

    api_requests = physical HTTP attempts (budget 차감 횟수). 재시도 포함.
    """
    target_id = target["id"]
    target_type = target["target_type"]
    target_value = target["target_value"]

    request_start = budget.used
    page_call_count = 0   # successful client.search() calls (floor for api_requests)
    new_count = 0
    unchanged_count = 0
    changed_count = 0
    fact_insert_count = 0

    rate_retry_max_raw = (os.getenv(RATE_RETRY_MAX_ENV) or "").strip()
    try:
        rate_retry_max = int(rate_retry_max_raw) if rate_retry_max_raw else DEFAULT_RATE_RETRY_MAX
    except ValueError:
        rate_retry_max = DEFAULT_RATE_RETRY_MAX

    rate_retry_base_raw = (os.getenv(RATE_RETRY_BASE_SECONDS_ENV) or "").strip()
    try:
        rate_retry_base = float(rate_retry_base_raw) if rate_retry_base_raw else DEFAULT_RATE_RETRY_BASE_SECONDS
    except ValueError:
        rate_retry_base = DEFAULT_RATE_RETRY_BASE_SECONDS

    def _budget_hook() -> None:
        budget.consume_or_raise(1)

    try:
        all_items = []
        page_no = 1
        total_count = None
        cap_reached = False

        while page_no <= MAX_PAGES_SAFETY_CAP:
            if not budget.check_available():
                phys = max(page_call_count, budget.used - request_start)
                store.mark_target_retry(target_id, run_id, "BUDGET_EXHAUSTED", "Request budget exhausted before page fetch")
                return SyncTargetResult(
                    target_id=target_id, target_type=target_type, target_value=target_value,
                    status=TARGET_STATUS_RETRY, api_requests=phys,
                    source_items=len(all_items), new_count=0, unchanged_count=0,
                    changed_count=0, fact_insert_count=0,
                    error="BUDGET_EXHAUSTED", stop_batch=True,
                )

            resp = None
            for retry_23 in range(rate_retry_max + 1):
                try:
                    resp = client.search(
                        search_gubun=SEARCH_CAS,
                        search_nm=target_value,
                        page_no=page_no,
                        num_of_rows=SYNC_PAGE_SIZE,
                        attempt_hook=_budget_hook,
                    )
                    break
                except RequestBudgetExceeded:
                    phys = max(page_call_count, budget.used - request_start)
                    store.mark_target_retry(target_id, run_id, "BUDGET_EXHAUSTED", "Budget exhausted during HTTP attempt")
                    return SyncTargetResult(
                        target_id=target_id, target_type=target_type, target_value=target_value,
                        status=TARGET_STATUS_RETRY, api_requests=phys,
                        source_items=len(all_items), new_count=0, unchanged_count=0,
                        changed_count=0, fact_insert_count=0,
                        error="BUDGET_EXHAUSTED", stop_batch=True,
                    )
                except KecoChemicalClientError as _exc:
                    sc = getattr(_exc, "source_code", None) or ""
                    if sc == RATE_LIMIT_SECOND_CODE and retry_23 < rate_retry_max:
                        time.sleep(rate_retry_base * (2 ** retry_23))
                        continue
                    raise _exc

            # resp is set successfully; count this logical page
            page_call_count += 1

            if total_count is None:
                try:
                    total_count = int(resp.total_count or "0")
                except (TypeError, ValueError):
                    total_count = 0

            all_items.extend(resp.items)

            if total_count == 0 or len(all_items) >= total_count:
                break
            page_no += 1
        else:
            # while-condition false → page_no > MAX_PAGES_SAFETY_CAP
            if total_count is not None and len(all_items) < total_count:
                cap_reached = True

        # Pagination safety cap reached with unread pages → RETRY
        if cap_reached:
            phys = max(page_call_count, budget.used - request_start)
            store.mark_target_retry(
                target_id, run_id, "PAGINATION_CAP",
                f"Safety cap {MAX_PAGES_SAFETY_CAP} reached: totalCount={total_count} fetched={len(all_items)}",
            )
            return SyncTargetResult(
                target_id=target_id, target_type=target_type, target_value=target_value,
                status=TARGET_STATUS_RETRY, api_requests=phys,
                source_items=len(all_items), new_count=0, unchanged_count=0,
                changed_count=0, fact_insert_count=0, error="PAGINATION_CAP",
            )

        source_items_total = len(all_items)

        if not all_items:
            phys = max(page_call_count, budget.used - request_start)
            store.mark_target_empty(target_id, run_id, phys)
            return SyncTargetResult(
                target_id=target_id, target_type=target_type, target_value=target_value,
                status=TARGET_STATUS_EMPTY, api_requests=phys,
                source_items=0, new_count=0, unchanged_count=0,
                changed_count=0, fact_insert_count=0,
            )

        # Pre-check CAS — ANY mismatch = CONFLICT (partial persist 금지)
        target_cas = target_value.strip()
        mismatched = [item for item in all_items if (item.cas_no or "").strip() != target_cas]
        matched = [item for item in all_items if (item.cas_no or "").strip() == target_cas]

        if mismatched:
            phys = max(page_call_count, budget.used - request_start)
            store.mark_target_conflict(
                target_id, run_id, phys, source_items_total,
                f"CAS mismatch: {len(mismatched)}/{source_items_total} items differ",
            )
            return SyncTargetResult(
                target_id=target_id, target_type=target_type, target_value=target_value,
                status=TARGET_STATUS_CONFLICT, api_requests=phys,
                source_items=source_items_total, new_count=0, unchanged_count=0,
                changed_count=0, fact_insert_count=0, error="CAS_MISMATCH",
            )

        for item in matched:
            raw = item.raw_payload or {}
            result = store.persist_item(raw, item, run_id)
            if result.status == "NEW":
                new_count += 1
            elif result.status == "UNCHANGED":
                unchanged_count += 1
            elif result.status == "CHANGED":
                changed_count += 1
            fact_insert_count += result.inserted_fact_count

        phys = max(page_call_count, budget.used - request_start)
        store.mark_target_done(target_id, run_id, phys, source_items_total)
        return SyncTargetResult(
            target_id=target_id, target_type=target_type, target_value=target_value,
            status=TARGET_STATUS_DONE, api_requests=phys,
            source_items=source_items_total, new_count=new_count,
            unchanged_count=unchanged_count, changed_count=changed_count,
            fact_insert_count=fact_insert_count,
        )

    except KecoChemicalClientError as exc:
        source_code = getattr(exc, "source_code", None) or ""
        is_non_retry = source_code in NON_RETRY_CODES
        is_per_second = (source_code == RATE_LIMIT_SECOND_CODE)
        is_rate_limit = (exc.code == ERROR_RATE_LIMIT)
        phys = max(page_call_count, budget.used - request_start)

        if is_non_retry:
            store.mark_target_failed(target_id, run_id, exc.code, exc.message)
            return SyncTargetResult(
                target_id=target_id, target_type=target_type, target_value=target_value,
                status=TARGET_STATUS_FAILED, api_requests=phys,
                source_items=0, new_count=0, unchanged_count=0,
                changed_count=0, fact_insert_count=0, error=exc.message,
            )

        # code 22 → stop_batch=True (daily quota)
        # code 23 → stop_batch=False (per-second throttle, retries already exhausted)
        # no source_code, exc.code=RATE_LIMIT → stop_batch=True (fallback)
        stop_batch = is_rate_limit and not is_per_second

        store.mark_target_retry(target_id, run_id, exc.code, exc.message)
        return SyncTargetResult(
            target_id=target_id, target_type=target_type, target_value=target_value,
            status=TARGET_STATUS_RETRY, api_requests=phys,
            source_items=0, new_count=0, unchanged_count=0,
            changed_count=0, fact_insert_count=0, error=exc.message,
            stop_batch=stop_batch,
        )


# ─────────────────────────────────────────────────────────────
# Batch runner
# ─────────────────────────────────────────────────────────────

def sync_batch(
    client: KecoChemicalClient,
    store: KecoReferenceStore,
    targets: List[dict],
    run_id: str,
    budget: RequestBudget,
) -> SyncBatchResult:
    """target 목록을 순차 처리. rate limit / budget 소진 시 PARTIAL로 안전 종료."""
    results: List[SyncTargetResult] = []
    processed = 0

    for target in targets:
        if budget.exhausted:
            logger.info("[KECO-SYNC] budget exhausted — stopping batch at %d/%d", processed, len(targets))
            break
        r = sync_one_target(client, store, target, run_id, budget)
        results.append(r)
        processed += 1
        if r.stop_batch:
            logger.info("[KECO-SYNC] stop_batch signal from target %s — halting", target.get("target_value"))
            break

    run_status = "COMPLETED"
    if processed < len(targets) or any(r.stop_batch for r in results):
        run_status = "PARTIAL"

    total_requests = sum(r.api_requests for r in results)
    total_items = sum(r.source_items for r in results)
    total_facts = sum(r.fact_insert_count for r in results)

    counters = {s: 0 for s in (TARGET_STATUS_DONE, TARGET_STATUS_EMPTY, TARGET_STATUS_CONFLICT,
                                TARGET_STATUS_RETRY, TARGET_STATUS_FAILED)}
    new = unchanged = changed = 0
    for r in results:
        if r.status in counters:
            counters[r.status] += 1
        new += r.new_count
        unchanged += r.unchanged_count
        changed += r.changed_count

    return SyncBatchResult(
        run_id=run_id,
        run_type="",
        targets_selected=len(targets),
        targets_processed=processed,
        requests=total_requests,
        new=new,
        unchanged=unchanged,
        changed=changed,
        empty=counters[TARGET_STATUS_EMPTY],
        conflict=counters[TARGET_STATUS_CONFLICT],
        retry=counters[TARGET_STATUS_RETRY],
        failed=counters[TARGET_STATUS_FAILED],
        source_items=total_items,
        facts_inserted=total_facts,
        budget_used=budget.used,
        budget_remaining=budget.remaining,
        status=run_status,
        results=results,
    )


# ─────────────────────────────────────────────────────────────
# Scheduled refresh — due targets only
# ─────────────────────────────────────────────────────────────

def refresh_due_targets(
    client: KecoChemicalClient,
    store: KecoReferenceStore,
    budget: RequestBudget,
    max_targets: Optional[int] = None,
) -> SyncBatchResult:
    """next_refresh_at <= now のtarget を最大 max_targets 件処理.

    lock: INITIAL_BULK or SCHEDULED_REFRESH already RUNNING → NOOP.
    """
    if store.has_active_run(RUN_TYPE_INITIAL_BULK):
        logger.info("[KECO-REFRESH] INITIAL_BULK active — skipping scheduled refresh")
        run_id = store.start_run(RUN_TYPE_SCHEDULED_REFRESH)
        store.complete_run(run_id, 0, 0, {"skipped": "INITIAL_BULK_ACTIVE"})
        return _empty_batch_result(run_id, RUN_TYPE_SCHEDULED_REFRESH, "COMPLETED")

    if store.has_active_run(RUN_TYPE_SCHEDULED_REFRESH):
        logger.info("[KECO-REFRESH] SCHEDULED_REFRESH already RUNNING — skipping")
        run_id = store.start_run(RUN_TYPE_SCHEDULED_REFRESH)
        store.complete_run(run_id, 0, 0, {"skipped": "REFRESH_ACTIVE"})
        return _empty_batch_result(run_id, RUN_TYPE_SCHEDULED_REFRESH, "COMPLETED")

    raw_batch_size = (os.getenv(REFRESH_BATCH_SIZE_ENV) or "").strip()
    try:
        batch_size = int(raw_batch_size) if raw_batch_size else DEFAULT_REFRESH_BATCH_SIZE
    except ValueError:
        batch_size = DEFAULT_REFRESH_BATCH_SIZE
    if max_targets is not None:
        batch_size = min(batch_size, max_targets)

    run_id = store.start_run(RUN_TYPE_SCHEDULED_REFRESH)
    try:
        due_targets = store.claim_due_targets(run_id, batch_size)
        if not due_targets:
            store.complete_run(run_id, 0, 0, {"due_targets": 0})
            return _empty_batch_result(run_id, RUN_TYPE_SCHEDULED_REFRESH, "COMPLETED")

        result = sync_batch(client, store, due_targets, run_id, budget)
        result.run_type = RUN_TYPE_SCHEDULED_REFRESH

        store.finish_run(run_id, result.status, result.requests, result.source_items, {
            "targets_selected": result.targets_selected,
            "targets_processed": result.targets_processed,
            "new": result.new, "unchanged": result.unchanged, "changed": result.changed,
            "empty": result.empty, "conflict": result.conflict,
            "retry": result.retry, "failed": result.failed,
            "budget_used": result.budget_used,
        })
        return result

    except Exception as exc:
        store.fail_run(run_id, "UNEXPECTED_ERROR", str(exc))
        raise


def _empty_batch_result(run_id: str, run_type: str, status: str) -> SyncBatchResult:
    return SyncBatchResult(
        run_id=run_id, run_type=run_type,
        targets_selected=0, targets_processed=0,
        requests=0, new=0, unchanged=0, changed=0,
        empty=0, conflict=0, retry=0, failed=0,
        source_items=0, facts_inserted=0,
        budget_used=0, budget_remaining=0,
        status=status,
    )
