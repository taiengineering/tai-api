"""Generic incremental adapter for KOSHA API sources (accident_cases, construction_accidents)."""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Callable, Coroutine, Any

from services.public_data_sync.adapters.base import SourceAdapter
from services.public_data_sync.contracts import RunContext, RunResult, RunStatus
from services.public_data_sync.errors import PreflightError


class KoshaIncrementalAdapter(SourceAdapter):
    """Reusable Control Plane adapter for incremental KOSHA sources.

    Delegates collection to a caller-supplied async collect_fn that accepts
    (since_date, strict=True) and returns {"upserted": int, ...}.

    Known-non-empty guard: raises SOURCE_EMPTY_UNEXPECTED rather than
    treating a zero-item first page as NO_CHANGE.
    """

    def __init__(
        self,
        adapter_key: str,
        collect_fn: Callable[..., Coroutine[Any, Any, dict]],
        log_target: str,
        get_since_fn: Callable[[str], str | None] | None = None,
    ) -> None:
        self._adapter_key = adapter_key
        self._collect_fn = collect_fn
        self._log_target = log_target
        self._get_since_fn = get_since_fn

    @property
    def adapter_key(self) -> str:
        return self._adapter_key

    def preflight(self, ctx: RunContext) -> None:
        if not os.getenv("DATA_GO_KR_SERVICE_KEY") and not os.getenv("KOSHA_SERVICE_KEY"):
            raise PreflightError(
                f"KOSHA API credential missing for {self._adapter_key} "
                "(DATA_GO_KR_SERVICE_KEY / KOSHA_SERVICE_KEY)"
            )

    def run(self, ctx: RunContext) -> RunResult:
        try:
            asyncio.get_running_loop()
            return self._fail(ctx, "ASYNC_CONTEXT_UNSUPPORTED")
        except RuntimeError:
            pass  # no running loop — safe to call asyncio.run()

        since: str | None = None
        if self._get_since_fn is not None:
            try:
                since = self._get_since_fn(self._log_target)
            except Exception as exc:
                error_code = getattr(exc, "code", None) or type(exc).__name__
                return self._fail(ctx, error_code)

        async def _call() -> dict:
            kwargs: dict = {"strict": True}
            if since is not None:
                kwargs["since_date"] = since
            return await self._collect_fn(**kwargs)

        try:
            result = asyncio.run(_call())
        except Exception as exc:
            error_code = getattr(exc, "code", None) or type(exc).__name__
            return self._fail(ctx, error_code)

        upserted = int(result.get("upserted") or 0)
        status = RunStatus.SUCCESS if upserted > 0 else RunStatus.NO_CHANGE

        return RunResult(
            run_id=ctx.run_id,
            source_id=ctx.source_id,
            status=status,
            started_at=ctx.started_at,
            finished_at=datetime.now(timezone.utc),
            fetched=upserted,
            created=upserted,
            change_detected=upserted > 0,
            details={"upserted": upserted, "since": result.get("since")},
        )

    def _fail(self, ctx: RunContext, error_code: str) -> RunResult:
        return RunResult(
            run_id=ctx.run_id,
            source_id=ctx.source_id,
            status=RunStatus.FAILED,
            started_at=ctx.started_at,
            finished_at=datetime.now(timezone.utc),
            error_code=error_code,
            error_message=error_code,
        )
