"""CSI Accident Public Data adapter — thin Control Plane layer over refresh_latest_csi_artifact."""
from __future__ import annotations

import os

from services.public_data_sync.adapters.base import SourceAdapter
from services.public_data_sync.contracts import RunContext, RunResult, RunStatus
from services.public_data_sync.errors import PreflightError


class CsiAccidentAdapter(SourceAdapter):
    """Adapter for CSI_ACCIDENT (FILE_SNAPSHOT / DAILY discovery).

    Delegates all logic to refresh_latest_csi_artifact(). This class maps
    the domain RefreshResult to a RunResult — it performs no HTTP, CSV, or DB
    operations directly.
    """

    adapter_key = "csi_accident"

    def preflight(self, ctx: RunContext) -> None:
        from services.csi_accidents.contract import APPLY_ENABLE_ENV
        if not os.environ.get("SUPABASE_URL"):
            raise PreflightError("SUPABASE_URL not configured (PREFLIGHT_ERROR)")
        if not (os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY")):
            raise PreflightError(
                "SUPABASE_SERVICE_KEY / SUPABASE_KEY not configured (PREFLIGHT_ERROR)"
            )
        if os.environ.get(APPLY_ENABLE_ENV) != "1":
            raise PreflightError(
                f"{APPLY_ENABLE_ENV} != '1' — CSI writes not enabled (PREFLIGHT_ERROR)"
            )

    def run(self, ctx: RunContext) -> RunResult:
        try:
            from db.supabase_client import get_supabase
            from services.csi_accidents.refresh import (
                RefreshResult,
                refresh_latest_csi_artifact,
            )
            from services.csi_accidents.store import SupabaseCsiStore

            store = SupabaseCsiStore(get_supabase())
            result: RefreshResult = refresh_latest_csi_artifact(store=store)
            return self._map(ctx, result)
        except Exception as exc:
            return self._fail(ctx, "CSI_REFRESH_EXCEPTION", type(exc).__name__)

    def _map(self, ctx: RunContext, result: "RefreshResult") -> RunResult:  # type: ignore[name-defined]
        run_id = ctx.run_id
        source_id = ctx.source_id

        if result.status == "NO_CHANGE":
            return RunResult(
                run_id=run_id,
                source_id=source_id,
                status=RunStatus.NO_CHANGE,
                change_detected=False,
                details={
                    "discovery_status": result.discovery_status,
                    "effective_date": result.effective_date,
                    "attachment_id": result.attachment_id,
                    "file_detail_sn": result.file_detail_sn,
                    "metadata_requests": result.metadata_requests,
                    "full_csv_downloads": result.full_csv_downloads,
                },
            )

        if result.status == "COMPLETED":
            return RunResult(
                run_id=run_id,
                source_id=source_id,
                status=RunStatus.SUCCESS,
                change_detected=True,
                created=result.new,
                changed=result.changed,
                unchanged=result.unchanged,
                source_version=result.snapshot_id,
                content_hash=result.sha256,
                details={
                    "discovery_status": result.discovery_status,
                    "effective_date": result.effective_date,
                    "attachment_id": result.attachment_id,
                    "file_detail_sn": result.file_detail_sn,
                    "filename": result.filename,
                    "bytes": result.bytes,
                    "parsed_rows": result.parsed_rows,
                    "metadata_requests": result.metadata_requests,
                    "full_csv_downloads": result.full_csv_downloads,
                    **result.details,
                },
            )

        # FAILED
        return RunResult(
            run_id=run_id,
            source_id=source_id,
            status=RunStatus.FAILED,
            error_code=result.error_code or "CSI_REFRESH_FAILED",
            error_message=result.error_message,
            details={
                "discovery_status": result.discovery_status,
                "metadata_requests": result.metadata_requests,
                "full_csv_downloads": result.full_csv_downloads,
            },
        )

    def _fail(self, ctx: RunContext, error_code: str, error_message: str) -> RunResult:
        return RunResult(
            run_id=ctx.run_id,
            source_id=ctx.source_id,
            status=RunStatus.FAILED,
            error_code=error_code,
            error_message=error_message,
        )
