"""Control Plane adapter — KECO 화학물질 참조 (TARGET_REFRESH / daily bounded)."""
from __future__ import annotations

import os
from datetime import datetime, timezone

from services.public_data_sync.adapters.base import SourceAdapter
from services.public_data_sync.contracts import RunContext, RunResult, RunStatus
from services.public_data_sync.errors import PreflightError

_REQUIRED_DB_CREDS = ("LEG_SUPABASE_URL", "LEG_SUPABASE_SERVICE_ROLE_KEY")
_BUDGET_ENV = "KECO_REQUEST_BUDGET"
_BATCH_ENV = "KECO_REFRESH_BATCH_SIZE"


def _parse_capacity() -> tuple[int, int]:
    """Return (request_budget, refresh_batch_size) from env; raise PreflightError on any issue."""
    budget_raw = os.getenv(_BUDGET_ENV, "").strip()
    batch_raw = os.getenv(_BATCH_ENV, "").strip()

    if not budget_raw:
        raise PreflightError(f"{_BUDGET_ENV} not configured (PREFLIGHT_ERROR)")
    if not batch_raw:
        raise PreflightError(f"{_BATCH_ENV} not configured (PREFLIGHT_ERROR)")

    try:
        request_budget = int(budget_raw)
    except ValueError:
        raise PreflightError(f"{_BUDGET_ENV} is not a valid integer (KECO_CAPACITY_CONFIG_INVALID)")

    try:
        refresh_batch_size = int(batch_raw)
    except ValueError:
        raise PreflightError(f"{_BATCH_ENV} is not a valid integer (KECO_CAPACITY_CONFIG_INVALID)")

    if request_budget <= 0 or refresh_batch_size <= 0 or refresh_batch_size > request_budget:
        raise PreflightError(
            f"Invalid capacity: budget={request_budget} batch={refresh_batch_size} "
            "(KECO_CAPACITY_CONFIG_INVALID)"
        )

    return request_budget, refresh_batch_size


def _is_bounded_partial(result) -> bool:
    """True when PARTIAL is a planned budget stop, not a domain failure."""
    if result.status != "PARTIAL":
        return False
    if result.failed > 0 or result.conflict > 0:
        return False
    stop_batch_signal = any(getattr(r, "stop_batch", False) for r in (result.results or []))
    return result.budget_remaining == 0 or stop_batch_signal


class KecoChemicalAdapter(SourceAdapter):
    """Thin Control Plane adapter — delegates to refresh_due_targets() domain function.

    Does not duplicate any KECO fetch/parse/persist logic. The domain function
    owns the exclusive DB lock (prevents parallel BULK/RETRY/MANUAL_SINGLE runs).
    """

    adapter_key = "keco_chemical"

    def preflight(self, ctx: RunContext) -> None:
        from services.keco_chemical.contract import SERVICE_KEY_ENV
        if not any((os.getenv(name) or "").strip() for name in SERVICE_KEY_ENV):
            raise PreflightError(
                "DATA_GO_KR_SERVICE_KEY or legacy KECO_API_SERVICE_KEY not configured (PREFLIGHT_ERROR)"
            )
        for key in _REQUIRED_DB_CREDS:
            if not os.getenv(key):
                raise PreflightError(f"{key} not configured (PREFLIGHT_ERROR)")
        _parse_capacity()  # raises PreflightError on missing / invalid capacity

    def run(self, ctx: RunContext) -> RunResult:
        try:
            request_budget, refresh_batch_size = _parse_capacity()
        except PreflightError as exc:
            return self._fail(ctx, "KECO_CAPACITY_CONFIG_INVALID", str(exc))

        try:
            from services.keco_chemical.client import KecoChemicalClient
            from services.keco_chemical.store import KecoReferenceStore
            from services.keco_chemical.budget import RequestBudget
            from services.keco_chemical.sync import refresh_due_targets

            client = KecoChemicalClient()
            store = KecoReferenceStore()
            budget = RequestBudget(limit=request_budget)
            result = refresh_due_targets(client, store, budget, max_targets=refresh_batch_size)
        except Exception as exc:
            return self._fail(ctx, "KECO_REFRESH_EXCEPTION", type(exc).__name__)

        return self._map(ctx, result)

    # ─────────────────────────────────────────────────────────────────────────

    def _map(self, ctx: RunContext, result) -> RunResult:
        now = datetime.now(timezone.utc)

        # Domain lock — another KECO run is active
        if result.run_id == "LOCKED":
            return RunResult(
                run_id=ctx.run_id,
                source_id=ctx.source_id,
                status=RunStatus.SKIPPED,
                started_at=ctx.started_at,
                finished_at=now,
                details={"domain_status": "LOCKED"},
            )

        # No due targets
        if result.targets_selected == 0:
            return RunResult(
                run_id=ctx.run_id,
                source_id=ctx.source_id,
                status=RunStatus.NO_CHANGE,
                started_at=ctx.started_at,
                finished_at=now,
                change_detected=False,
                details=self._safe_details(result),
            )

        # Target-level failures (highest priority for PARTIAL)
        if result.failed > 0 or result.conflict > 0:
            return RunResult(
                run_id=ctx.run_id,
                source_id=ctx.source_id,
                status=RunStatus.PARTIAL,
                started_at=ctx.started_at,
                finished_at=now,
                fetched=result.source_items,
                created=result.new,
                changed=result.changed,
                unchanged=result.unchanged,
                failed=result.failed + result.conflict,
                change_detected=(result.new + result.changed) > 0,
                error_code="KECO_TARGET_ATTENTION_REQUIRED",
                source_version=result.run_id,
                details=self._safe_details(result),
            )

        # Bounded domain partial — intentional budget stop, not a Control Plane error
        if _is_bounded_partial(result):
            return RunResult(
                run_id=ctx.run_id,
                source_id=ctx.source_id,
                status=RunStatus.SUCCESS,
                started_at=ctx.started_at,
                finished_at=now,
                fetched=result.source_items,
                created=result.new,
                changed=result.changed,
                unchanged=result.unchanged,
                change_detected=(result.new + result.changed) > 0,
                source_version=result.run_id,
                details={
                    **self._safe_details(result),
                    "bounded_partial": True,
                },
            )

        # Retry targets remaining (non-budget)
        if result.retry > 0:
            return RunResult(
                run_id=ctx.run_id,
                source_id=ctx.source_id,
                status=RunStatus.PARTIAL,
                started_at=ctx.started_at,
                finished_at=now,
                fetched=result.source_items,
                created=result.new,
                changed=result.changed,
                unchanged=result.unchanged,
                change_detected=(result.new + result.changed) > 0,
                error_code="KECO_TARGET_RETRY_REQUIRED",
                source_version=result.run_id,
                details=self._safe_details(result),
            )

        # Normal COMPLETED path
        if result.status == "COMPLETED":
            has_changes = (result.new + result.changed) > 0
            return RunResult(
                run_id=ctx.run_id,
                source_id=ctx.source_id,
                status=RunStatus.SUCCESS if has_changes else RunStatus.NO_CHANGE,
                started_at=ctx.started_at,
                finished_at=now,
                fetched=result.source_items,
                created=result.new,
                changed=result.changed,
                unchanged=result.unchanged,
                change_detected=has_changes,
                source_version=result.run_id,
                details=self._safe_details(result),
            )

        # Unknown domain status — fail closed
        return self._fail(ctx, "KECO_UNKNOWN_DOMAIN_STATUS", result.status)

    def _safe_details(self, result) -> dict:
        return {
            "domain_run_id": result.run_id,
            "targets_selected": result.targets_selected,
            "targets_processed": result.targets_processed,
            "requests": result.requests,
            "empty": result.empty,
            "conflict": result.conflict,
            "retry": result.retry,
            "failed": result.failed,
            "budget_used": result.budget_used,
            "budget_remaining": result.budget_remaining,
            "domain_status": result.status,
        }

    def _fail(self, ctx: RunContext, error_code: str, error_message: str = "") -> RunResult:
        return RunResult(
            run_id=ctx.run_id,
            source_id=ctx.source_id,
            status=RunStatus.FAILED,
            started_at=ctx.started_at,
            finished_at=datetime.now(timezone.utc),
            error_code=error_code,
            error_message=error_message,
        )
