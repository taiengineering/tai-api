"""KECO 15149420 Local Bulk CLI.

Mac Terminal에서 초기 전수수집 + Railway 운영 보조를 위한 단일 진입점.
Railway 환경변수는 `railway run` 명령으로 주입.

사용:
  python -m services.keco_chemical.collect --mode preflight
  python -m services.keco_chemical.collect --mode bootstrap [--dry-run]
  python -m services.keco_chemical.collect --mode batch [--max-targets N]
  python -m services.keco_chemical.collect --mode bulk [--max-targets N]
  python -m services.keco_chemical.collect --mode retry [--max-targets N]
  python -m services.keco_chemical.collect --mode refresh [--max-targets N]
  python -m services.keco_chemical.collect --mode status

로그:
  serviceKey / Supabase service_role / 기타 secret = 절대 출력 금지.

KECO API calls = 0 except in preflight/batch/bulk/retry/refresh modes (never in bootstrap/status).
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("keco.collect")


def _require_env(name: str) -> str:
    val = (os.getenv(name) or "").strip()
    if not val:
        logger.error("Required environment variable missing: %s", name)
        sys.exit(1)
    return val


def _make_client():
    from services.keco_chemical.client import KecoChemicalClient
    return KecoChemicalClient()


def _make_store():
    from services.keco_chemical.store import KecoReferenceStore
    return KecoReferenceStore()


def _make_budget():
    from services.keco_chemical.sync import RequestBudget
    return RequestBudget.from_env()


# ─────────────────────────────────────────────────────────────
# Mode: preflight — 3 live calls (ammonia + empty sentinel + CAS)
# ─────────────────────────────────────────────────────────────

def mode_preflight(args) -> None:
    """최대 3 API call로 live connectivity + 응답 구조 확인."""
    from services.keco_chemical.probe import run_preflight_probe
    _require_env("KECO_API_SERVICE_KEY")
    _require_env("LEG_SUPABASE_URL")
    _require_env("LEG_SUPABASE_SERVICE_ROLE_KEY")
    logger.info("[PREFLIGHT] Starting live probe (max 3 API calls)")
    run_preflight_probe()
    logger.info("[PREFLIGHT] Done")


# ─────────────────────────────────────────────────────────────
# Mode: bootstrap — create PENDING targets from identity_projection
# ─────────────────────────────────────────────────────────────

def mode_bootstrap(args) -> None:
    """identity_projection CAS → keco_collection_targets PENDING 생성."""
    _require_env("LEG_SUPABASE_URL")
    _require_env("LEG_SUPABASE_SERVICE_ROLE_KEY")
    store = _make_store()
    dry = getattr(args, "dry_run", False)
    label = "DRY-RUN" if dry else "LIVE"
    logger.info("[BOOTSTRAP][%s] Reading CAS from identity_projection...", label)
    count = store.bootstrap_targets(dry_run=dry)
    if dry:
        logger.info("[BOOTSTRAP][DRY-RUN] Would create %d targets (no DB write)", count)
    else:
        logger.info("[BOOTSTRAP][LIVE] Created %d new PENDING targets", count)


# ─────────────────────────────────────────────────────────────
# Mode: status — print target counts (no API calls)
# ─────────────────────────────────────────────────────────────

def mode_status(args) -> None:
    """keco_collection_targets 현재 상태 출력. API 호출 없음."""
    _require_env("LEG_SUPABASE_URL")
    _require_env("LEG_SUPABASE_SERVICE_ROLE_KEY")
    store = _make_store()
    summary = store.get_status_summary()
    logger.info("[STATUS] Target summary:")
    for k, v in summary.items():
        logger.info("  %-12s = %s", k, v)
    is_bulk = store.has_active_run("INITIAL_BULK")
    is_refresh = store.has_active_run("SCHEDULED_REFRESH")
    logger.info("[STATUS] INITIAL_BULK active = %s", is_bulk)
    logger.info("[STATUS] SCHEDULED_REFRESH active = %s", is_refresh)


# ─────────────────────────────────────────────────────────────
# Mode: batch — bounded sync (default 10 targets)
# ─────────────────────────────────────────────────────────────

def mode_batch(args) -> None:
    """PENDING/RETRY targets를 bounded batch 처리. preflight 후 controlled test용."""
    max_targets = getattr(args, "max_targets", None) or 10
    dry = getattr(args, "dry_run", False)
    _require_env("KECO_API_SERVICE_KEY")
    _require_env("LEG_SUPABASE_URL")
    _require_env("LEG_SUPABASE_SERVICE_ROLE_KEY")

    store = _make_store()

    if dry:
        from services.keco_chemical.contract import TARGET_STATUS_PENDING, TARGET_STATUS_RETRY
        summary = store.get_status_summary()
        pending = summary.get(TARGET_STATUS_PENDING, 0)
        retry = summary.get(TARGET_STATUS_RETRY, 0)
        claimable = pending + retry
        logger.info(
            "[BATCH][DRY-RUN] PENDING=%d RETRY=%d claimable=%d, would_claim=%d",
            pending, retry, claimable, min(claimable, max_targets),
        )
        return

    stale_min = _stale_minutes()
    client = _make_client()
    budget = _make_budget()

    from services.keco_chemical.contract import RUN_TYPE_INITIAL_BULK
    run_id, locked = store.start_exclusive_run(RUN_TYPE_INITIAL_BULK, stale_minutes=stale_min)
    if locked:
        logger.warning("[BATCH] Another KECO runtime run is RUNNING — skipping")
        return

    logger.info("[BATCH] run_id=%s max_targets=%d budget=%d", run_id, max_targets, budget.limit)

    try:
        targets = store.claim_targets(run_id, max_targets, stale_min)
        logger.info("[BATCH] claimed %d targets", len(targets))

        from services.keco_chemical.sync import sync_batch
        result = sync_batch(client, store, targets, run_id, budget)

        store.finish_run(run_id, result.status, result.requests, result.source_items, _metrics(result))
        _log_result(result)
    except Exception as exc:
        store.fail_run(run_id, "UNEXPECTED_ERROR", str(exc))
        logger.error("[BATCH] run %s FAILED: %s", run_id, exc)
        raise


# ─────────────────────────────────────────────────────────────
# Mode: bulk — full initial load with resume support
# ─────────────────────────────────────────────────────────────

def mode_bulk(args) -> None:
    """전수 초기 적재. PENDING/RETRY 전체를 budget 소진까지 처리."""
    _require_env("KECO_API_SERVICE_KEY")
    _require_env("LEG_SUPABASE_URL")
    _require_env("LEG_SUPABASE_SERVICE_ROLE_KEY")

    store = _make_store()
    stale_min = _stale_minutes()

    # start_exclusive_run: recover stale + atomic INSERT
    from services.keco_chemical.contract import RUN_TYPE_INITIAL_BULK, DEFAULT_CLAIM_BATCH_SIZE
    run_id, locked = store.start_exclusive_run(RUN_TYPE_INITIAL_BULK, stale_minutes=stale_min)
    if locked:
        logger.warning("[BULK] Another KECO runtime run is RUNNING — skipping to prevent double run")
        return

    budget = _make_budget()
    client = _make_client()
    max_targets = getattr(args, "max_targets", None)

    logger.info("[BULK] run_id=%s budget=%d", run_id, budget.limit)

    try:
        total_processed = 0
        total_source_items = 0
        final_status = "PARTIAL"   # 기본 PARTIAL; targets 소진 시에만 COMPLETED로 변경
        from services.keco_chemical.sync import sync_batch

        while not budget.exhausted:
            batch_size = DEFAULT_CLAIM_BATCH_SIZE
            if max_targets is not None:
                remaining_allowed = max_targets - total_processed
                if remaining_allowed <= 0:
                    break
                batch_size = min(batch_size, remaining_allowed)

            targets = store.claim_targets(run_id, batch_size, stale_min, mode="bulk")
            if not targets:
                logger.info("[BULK] No more claimable targets")
                final_status = "COMPLETED"
                break

            result = sync_batch(client, store, targets, run_id, budget)
            total_processed += result.targets_processed
            total_source_items += result.source_items
            _log_result(result)

            if result.status == "PARTIAL":
                logger.info("[BULK] Partial stop (budget/rate-limit) after %d total processed", total_processed)
                break

        store.finish_run(run_id, final_status, budget.used, total_source_items, {
            "total_processed": total_processed,
            "total_source_items": total_source_items,
            "budget_used": budget.used,
            "budget_remaining": budget.remaining,
        })
        logger.info("[BULK] DONE — run_id=%s status=%s processed=%d source_items=%d budget_used=%d",
                    run_id, final_status, total_processed, total_source_items, budget.used)

    except Exception as exc:
        store.fail_run(run_id, "UNEXPECTED_ERROR", str(exc))
        logger.error("[BULK] run %s FAILED: %s", run_id, exc)
        raise


# ─────────────────────────────────────────────────────────────
# Mode: retry — reprocess FAILED/RETRY targets
# ─────────────────────────────────────────────────────────────

def mode_retry(args) -> None:
    """FAILED/RETRY 대상 재처리 (PENDING 포함 안함)."""
    max_targets = getattr(args, "max_targets", None) or 50
    _require_env("KECO_API_SERVICE_KEY")
    _require_env("LEG_SUPABASE_URL")
    _require_env("LEG_SUPABASE_SERVICE_ROLE_KEY")

    store = _make_store()
    stale_min = _stale_minutes()

    from services.keco_chemical.contract import RUN_TYPE_RETRY
    run_id, locked = store.start_exclusive_run(RUN_TYPE_RETRY, stale_minutes=stale_min)
    if locked:
        logger.warning("[RETRY] Another KECO runtime run is RUNNING — skipping")
        return

    budget = _make_budget()
    client = _make_client()
    logger.info("[RETRY] run_id=%s max_targets=%d", run_id, max_targets)

    try:
        targets = store.claim_targets(run_id, max_targets, stale_min, mode="retry")
        from services.keco_chemical.sync import sync_batch
        result = sync_batch(client, store, targets, run_id, budget)
        store.finish_run(run_id, result.status, result.requests, result.source_items, _metrics(result))
        _log_result(result)
    except Exception as exc:
        store.fail_run(run_id, "UNEXPECTED_ERROR", str(exc))
        logger.error("[RETRY] run %s FAILED: %s", run_id, exc)
        raise


# ─────────────────────────────────────────────────────────────
# Mode: refresh — due targets only
# ─────────────────────────────────────────────────────────────

def mode_refresh(args) -> None:
    """next_refresh_at <= now のtarget 처리."""
    max_targets = getattr(args, "max_targets", None)
    _require_env("KECO_API_SERVICE_KEY")
    _require_env("LEG_SUPABASE_URL")
    _require_env("LEG_SUPABASE_SERVICE_ROLE_KEY")

    store = _make_store()
    budget = _make_budget()
    client = _make_client()

    from services.keco_chemical.sync import refresh_due_targets
    result = refresh_due_targets(client, store, budget, max_targets=max_targets)
    _log_result(result)


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _stale_minutes() -> int:
    from services.keco_chemical.contract import DEFAULT_STALE_RUNNING_MINUTES, STALE_RUNNING_MINUTES_ENV
    raw = (os.getenv(STALE_RUNNING_MINUTES_ENV) or "").strip()
    try:
        return int(raw) if raw else DEFAULT_STALE_RUNNING_MINUTES
    except ValueError:
        return DEFAULT_STALE_RUNNING_MINUTES


def _metrics(result) -> dict:
    return {
        "targets_selected": result.targets_selected,
        "targets_processed": result.targets_processed,
        "new": result.new,
        "unchanged": result.unchanged,
        "changed": result.changed,
        "empty": result.empty,
        "conflict": result.conflict,
        "retry": result.retry,
        "failed": result.failed,
        "budget_used": result.budget_used,
    }


def _log_result(result) -> None:
    logger.info(
        "[RESULT] status=%s processed=%d/%d requests=%d "
        "new=%d unchanged=%d changed=%d empty=%d conflict=%d retry=%d failed=%d "
        "budget_used=%d remaining=%d",
        result.status,
        result.targets_processed, result.targets_selected,
        result.requests,
        result.new, result.unchanged, result.changed,
        result.empty, result.conflict, result.retry, result.failed,
        result.budget_used, result.budget_remaining,
    )


# ─────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="KECO 15149420 Local Bulk CLI",
        prog="python -m services.keco_chemical.collect",
    )
    parser.add_argument(
        "--mode",
        choices=["preflight", "bootstrap", "batch", "bulk", "retry", "refresh", "status"],
        required=True,
        help="실행 모드",
    )
    parser.add_argument("--max-targets", type=int, default=None, help="처리 대상 상한")
    parser.add_argument("--dry-run", action="store_true", help="DB write 없이 예상 결과만 출력")

    args = parser.parse_args()

    dispatch = {
        "preflight": mode_preflight,
        "bootstrap": mode_bootstrap,
        "batch": mode_batch,
        "bulk": mode_bulk,
        "retry": mode_retry,
        "refresh": mode_refresh,
        "status": mode_status,
    }
    dispatch[args.mode](args)


if __name__ == "__main__":
    main()
