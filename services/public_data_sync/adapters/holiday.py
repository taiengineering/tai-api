"""Control Plane adapter — Public Holiday (공휴일) daily sync."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Callable

from services.public_data_sync.adapters.base import SourceAdapter
from services.public_data_sync.contracts import RunContext, RunResult, RunStatus
from services.public_data_sync.errors import PreflightError


class HolidayAdapter(SourceAdapter):
    """Thin adapter: delegates to holiday_sync_svc.sync_current_and_next.

    DI: sync_fn can be injected for tests without touching the production path.
    """

    adapter_key = "holiday"

    def __init__(self, sync_fn: Callable | None = None) -> None:
        self._sync_fn = sync_fn

    def preflight(self, ctx: RunContext) -> None:
        if not os.getenv("DATA_GO_KR_SERVICE_KEY"):
            raise PreflightError("DATA_GO_KR_SERVICE_KEY not configured (PREFLIGHT_ERROR)")

    def run(self, ctx: RunContext) -> RunResult:
        try:
            if self._sync_fn is not None:
                result = self._sync_fn()
            else:
                from services.holiday_sync_svc import sync_current_and_next
                result = sync_current_and_next()
        except Exception as exc:
            return RunResult(
                run_id=ctx.run_id,
                source_id=ctx.source_id,
                status=RunStatus.FAILED,
                started_at=ctx.started_at,
                finished_at=datetime.now(timezone.utc),
                error_code="HOLIDAY_SYNC_FAILED",
                error_message=type(exc).__name__,
            )

        results = result.get("results") or []
        total_inserted = sum(int(r.get("inserted") or 0) for r in results)

        return RunResult(
            run_id=ctx.run_id,
            source_id=ctx.source_id,
            status=RunStatus.SUCCESS,
            started_at=ctx.started_at,
            finished_at=datetime.now(timezone.utc),
            fetched=sum(int(r.get("fetched") or 0) for r in results),
            created=total_inserted,
            change_detected=total_inserted > 0,
            details={"results": results},
        )
