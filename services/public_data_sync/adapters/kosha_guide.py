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

_CHANGE_DETECTED: dict[str, bool] = {
    "COMPLETED": True,
    "SNAPSHOT_NO_CHANGE": False,
    "DRY_RUN": False,
    "REJECT": False,
    "FAILED": False,
    "VALIDATED": False,
}

# Keys allowed in RunResult.details.
# snapshot_hash omitted — already stored in RunResult.content_hash.
# fetched omitted — already stored in RunResult.fetched.
# failure_reason omitted — not a stable code; kept out of details to avoid raw exception text.
_GUIDE_DETAILS_KEYS = (
    "domain_status",
    "declared",
    "unique",
    "hold_count",
    "membership",
    "snapshot_id",
    "catalog_upserted",
    "business_dml",
)


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
            return self._fail(
                ctx,
                error_code="DOMAIN_EXECUTION_ERROR",
                error_message=type(exc).__name__,
            )

        domain_status = getattr(sync_result, "status", None)
        run_status = _STATUS_MAP.get(domain_status)
        if run_status is None:
            return self._fail(
                ctx,
                error_code="UNKNOWN_DOMAIN_STATUS",
                error_message=f"unrecognised domain status: {domain_status!r}",
            )

        error_code = None
        error_message = None
        if run_status == RunStatus.FAILED:
            error_code = domain_status   # stable domain code
            error_message = domain_status

        return RunResult(
            run_id=ctx.run_id,
            source_id=ctx.source_id,
            status=run_status,
            started_at=ctx.started_at,
            finished_at=datetime.now(timezone.utc),
            fetched=int(getattr(sync_result, "fetched", None) or 0),
            source_version=getattr(sync_result, "snapshot_id", None),
            content_hash=getattr(sync_result, "snapshot_hash", None),
            change_detected=_CHANGE_DETECTED.get(domain_status, False),
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
            k: v for k, attr in {
                "domain_status": "status",
                "declared": "declared",
                "unique": "unique",
                "hold_count": "hold_count",
                "membership": "membership",
                "snapshot_id": "snapshot_id",
                "catalog_upserted": "catalog_upserted",
                "business_dml": "business_dml",
            }.items()
            if (v := getattr(sync_result, attr, None)) is not None
        }

    def _fail(
        self,
        ctx: RunContext,
        *,
        error_code: str,
        error_message: str,
    ) -> RunResult:
        return RunResult(
            run_id=ctx.run_id,
            source_id=ctx.source_id,
            status=RunStatus.FAILED,
            started_at=ctx.started_at,
            finished_at=datetime.now(timezone.utc),
            error_code=error_code,
            error_message=error_message,
        )
