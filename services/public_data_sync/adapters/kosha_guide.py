"""Control Plane adapter — KOSHA Guide sync pipeline."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from services.public_data_sync.adapters.base import SourceAdapter
from services.public_data_sync.contracts import RunContext, RunResult, RunStatus
from services.public_data_sync.errors import PreflightError

_STATUS_MAP: dict[str, RunStatus] = {
    "COMPLETED": RunStatus.SUCCESS,
    "SNAPSHOT_NO_CHANGE": RunStatus.NO_CHANGE,
    "DRY_RUN": RunStatus.SKIPPED,
    "REJECT": RunStatus.FAILED,
    "FAILED": RunStatus.FAILED,
    "VALIDATED": RunStatus.FAILED,  # intermediate state — should never be final
}


class KoshaGuideAdapter(SourceAdapter):
    """Thin adapter: delegates to sync_kosha_guides (synchronous).

    DI param allows tests to inject a stub without production stores.
    When omitted, defaults to the production sync_kosha_guides function.
    """

    adapter_key = "kosha_guide"

    def __init__(
        self,
        sync_fn: Callable[..., Any] | None = None,
    ) -> None:
        self._sync_fn = sync_fn

    def preflight(self, ctx: RunContext) -> None:
        from services.kosha_safety_material_sync import kosha_service_key
        if not kosha_service_key():
            raise PreflightError("KOSHA service key not configured (DATA_GO_KR_SERVICE_KEY / KOSHA_SERVICE_KEY)")

    def run(self, ctx: RunContext) -> RunResult:
        try:
            if self._sync_fn is not None:
                sync_result = self._sync_fn(dry_run=ctx.dry_run)
            else:
                from services.kosha_guide_sync import sync_kosha_guides
                sync_result = sync_kosha_guides(dry_run=ctx.dry_run)
        except Exception as exc:
            return self._result(
                ctx,
                RunStatus.FAILED,
                error_code="SYNC_FN_EXCEPTION",
                error_message=f"{type(exc).__name__}: {exc}",
            )

        domain_status = getattr(sync_result, "status", None)
        run_status = _STATUS_MAP.get(domain_status)
        if run_status is None:
            return self._result(
                ctx,
                RunStatus.FAILED,
                error_code="UNKNOWN_DOMAIN_STATUS",
                error_message=f"unrecognised domain status: {domain_status!r}",
                details=self._to_details(sync_result),
            )

        error_code = None
        error_message = None
        if run_status == RunStatus.FAILED:
            error_code = domain_status
            error_message = getattr(sync_result, "failure_reason", None) or domain_status

        return self._result(
            ctx,
            run_status,
            error_code=error_code,
            error_message=error_message,
            details=self._to_details(sync_result),
        )

    # ------------------------------------------------------------------
    # private
    # ------------------------------------------------------------------

    @staticmethod
    def _to_details(sync_result: Any) -> dict:
        return {
            "domain_status": getattr(sync_result, "status", None),
            "declared": getattr(sync_result, "declared", None),
            "fetched": getattr(sync_result, "fetched", None),
            "unique": getattr(sync_result, "unique", None),
            "hold_count": getattr(sync_result, "hold_count", None),
            "membership": getattr(sync_result, "membership", None),
            "snapshot_hash": getattr(sync_result, "snapshot_hash", None),
            "snapshot_id": getattr(sync_result, "snapshot_id", None),
            "catalog_upserted": getattr(sync_result, "catalog_upserted", None),
            "business_dml": getattr(sync_result, "business_dml", None),
            "failure_reason": getattr(sync_result, "failure_reason", None),
        }

    def _result(
        self,
        ctx: RunContext,
        status: RunStatus,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
        details: dict | None = None,
    ) -> RunResult:
        return RunResult(
            run_id=ctx.run_id,
            source_id=ctx.source_id,
            status=status,
            started_at=ctx.started_at,
            finished_at=datetime.now(timezone.utc),
            error_code=error_code,
            error_message=error_message,
            details=details or {},
        )
