"""Control Plane adapter — KOSHA Safety Material daily pipeline."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

from services.public_data_sync.adapters.base import SourceAdapter
from services.public_data_sync.contracts import RunContext, RunResult, RunStatus
from services.public_data_sync.errors import PreflightError

_FINAL_SUCCESS = "SUCCESS"
_SNAPSHOT_NO_CHANGE = "SNAPSHOT_NO_CHANGE"

# Keys allowed in RunResult.details for the daily (non-dry-run) path.
_SM_DAILY_DETAILS_KEYS = (
    "snapshot_result",
    "snapshot_id",
    "snapshot_hash",
    "snapshot_membership",
    "catalog_new",
    "detail_new",
    "detail_pending",
    "storage_completed",
    "storage_pending",
    "new_hold_count",
    "existing_open_holds",
    "historical_leak",
)

# Keys allowed in RunResult.details for the dry-run path.
_SM_DRY_DETAILS_KEYS = (
    "status",
    "dry_run",
    "declared",
    "fetched",
    "unique",
    "snapshot_hash",
    "catalog_inserts_planned",
    "membership_planned",
)


def _pick(src: dict, keys: tuple[str, ...]) -> dict:
    return {k: src[k] for k in keys if k in src}


class KoshaSafetyMaterialAdapter(SourceAdapter):
    """Thin adapter: delegates to the KOSHA Safety Material daily pipeline.

    DI params allow tests to inject stubs without touching production stores.
    When omitted, defaults to production_daily assembly functions.
    """

    adapter_key = "kosha_safety_material"

    def __init__(
        self,
        daily_fn: Callable[[], Coroutine[Any, Any, tuple[dict, int]]] | None = None,
        dry_run_fn: Callable[[], Coroutine[Any, Any, dict]] | None = None,
    ) -> None:
        self._daily_fn = daily_fn
        self._dry_run_fn = dry_run_fn

    def preflight(self, ctx: RunContext) -> None:
        from services.kosha_safety_material_sync import kosha_service_key
        if not kosha_service_key():
            raise PreflightError("KOSHA service key not configured (DATA_GO_KR_SERVICE_KEY / KOSHA_SERVICE_KEY)")

    def run(self, ctx: RunContext) -> RunResult:
        try:
            asyncio.get_running_loop()
            return self._fail(
                ctx,
                error_code="ASYNC_CONTEXT_UNSUPPORTED",
                error_message="KoshaSafetyMaterialAdapter.run() called from within a running event loop",
            )
        except RuntimeError:
            pass  # no running loop — safe to call asyncio.run()

        if ctx.dry_run:
            return self._run_dry(ctx)
        return self._run_daily(ctx)

    # ------------------------------------------------------------------
    # private
    # ------------------------------------------------------------------

    def _run_daily(self, ctx: RunContext) -> RunResult:
        async def _call():
            if self._daily_fn is not None:
                return await self._daily_fn()
            from services.kosha_safety_materials.production_daily import run_production_daily
            return await run_production_daily()

        try:
            report, _exit_code = asyncio.run(_call())
        except Exception as exc:
            return self._fail(
                ctx,
                error_code="DAILY_FN_EXCEPTION",
                error_message=type(exc).__name__,
            )

        final_status = report.get("final_status")
        snapshot_result = report.get("snapshot_result")

        if final_status == _FINAL_SUCCESS:
            detail_new = int(report.get("detail_new") or 0)
            storage_completed = int(report.get("storage_completed") or 0)
            new_hold_count = int(report.get("new_hold_count") or 0)

            has_change = (
                snapshot_result != _SNAPSHOT_NO_CHANGE
                or detail_new > 0
                or storage_completed > 0
                or new_hold_count > 0
            )
            status = RunStatus.SUCCESS if has_change else RunStatus.NO_CHANGE
            change_detected = has_change

            return RunResult(
                run_id=ctx.run_id,
                source_id=ctx.source_id,
                status=status,
                started_at=ctx.started_at,
                finished_at=datetime.now(timezone.utc),
                fetched=int(report.get("snapshot_membership") or 0),
                created=int(report.get("catalog_new") or 0),
                source_version=report.get("snapshot_id"),
                content_hash=report.get("snapshot_hash"),
                change_detected=change_detected,
                details=_pick(report, _SM_DAILY_DETAILS_KEYS),
            )

        return RunResult(
            run_id=ctx.run_id,
            source_id=ctx.source_id,
            status=RunStatus.FAILED,
            started_at=ctx.started_at,
            finished_at=datetime.now(timezone.utc),
            error_code=report.get("failure_code") or final_status,
            error_message=final_status,
            details=_pick(report, _SM_DAILY_DETAILS_KEYS),
        )

    def _run_dry(self, ctx: RunContext) -> RunResult:
        async def _call():
            if self._dry_run_fn is not None:
                return await self._dry_run_fn()
            from services.kosha_safety_materials.production_daily import run_production_dry_run
            return await run_production_dry_run()

        try:
            report = asyncio.run(_call())
        except Exception as exc:
            return self._fail(
                ctx,
                error_code="DRY_RUN_FN_EXCEPTION",
                error_message=type(exc).__name__,
            )

        return RunResult(
            run_id=ctx.run_id,
            source_id=ctx.source_id,
            status=RunStatus.SKIPPED,
            started_at=ctx.started_at,
            finished_at=datetime.now(timezone.utc),
            fetched=int(report.get("fetched") or 0),
            content_hash=report.get("snapshot_hash"),
            change_detected=False,
            details=_pick(report, _SM_DRY_DETAILS_KEYS),
        )

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
