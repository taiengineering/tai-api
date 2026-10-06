"""Control Plane adapter — KOSHA Safety Material daily pipeline."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

from services.public_data_sync.adapters.base import SourceAdapter
from services.public_data_sync.contracts import RunContext, RunResult, RunStatus
from services.public_data_sync.errors import PreflightError

# final_status values that map to non-FAILED RunStatus
_FINAL_SUCCESS = "SUCCESS"
_SNAPSHOT_NO_CHANGE = "SNAPSHOT_NO_CHANGE"


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
            return self._result(
                ctx,
                RunStatus.FAILED,
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
            return self._result(
                ctx,
                RunStatus.FAILED,
                error_code="DAILY_FN_EXCEPTION",
                error_message=f"{type(exc).__name__}: {exc}",
            )

        final_status = report.get("final_status")
        snapshot_result = report.get("snapshot_result")

        if final_status == _FINAL_SUCCESS:
            if snapshot_result == _SNAPSHOT_NO_CHANGE:
                status = RunStatus.NO_CHANGE
            else:
                status = RunStatus.SUCCESS
            return self._result(ctx, status, details=report)

        return self._result(
            ctx,
            RunStatus.FAILED,
            error_code=report.get("failure_code") or final_status,
            error_message=final_status,
            details=report,
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
            return self._result(
                ctx,
                RunStatus.FAILED,
                error_code="DRY_RUN_FN_EXCEPTION",
                error_message=f"{type(exc).__name__}: {exc}",
            )

        return self._result(ctx, RunStatus.SKIPPED, details=report)

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
