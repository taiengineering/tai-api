"""Control Plane adapter — EXT-165 화학물질안전원 화학사고 (FULL_SNAPSHOT).

GAP-A: dry_run=True → SKIPPED 즉시 반환 (HTTP/DB 쓰기 없음).
GAP-B: ctx.metadata resume_snapshot_id/resume_from_page로 체크포인트 기반 Resume.
       R3-02: on_page_complete에서 upsert_items 후 체크포인트 갱신 (순서 보장).
GAP-D: atomic_complete_snapshot() RPC로 원자적 스냅샷 완결.
R3-03: atomic_complete_snapshot에 run_id 전달 — RPC에서 소유권 검증.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from services.public_data_sync.adapters.base import SourceAdapter
from services.public_data_sync.contracts import RunContext, RunResult, RunStatus
from services.public_data_sync.errors import PreflightError


class Ext165ChemicalAccidentAdapter(SourceAdapter):
    """FULL_SNAPSHOT: collect_all → per-page save → STAGING snapshot → atomic_complete_snapshot."""

    adapter_key = "ext165_chemical_accident"

    def preflight(self, ctx: RunContext) -> None:
        if not os.getenv("DATA_GO_KR_SERVICE_KEY"):
            raise PreflightError("DATA_GO_KR_SERVICE_KEY not configured")

    def run(self, ctx: RunContext) -> RunResult:
        # GAP-A: dry_run → no HTTP calls, no DB writes, return SKIPPED immediately
        if ctx.dry_run:
            return RunResult(
                run_id=ctx.run_id,
                source_id=ctx.source_id,
                status=RunStatus.SKIPPED,
                started_at=ctx.started_at,
                finished_at=datetime.now(timezone.utc),
                details={"dry_run": True, "message": "dry_run=True: HTTP and DB writes suppressed"},
            )

        from services.ext165_chemical_accident.store import (
            atomic_complete_snapshot,
            compute_content_hash,
            compute_content_hash_from_db,
            create_staging_snapshot,
            fail_snapshot,
            save_page_checkpoint,
        )
        from services.ext165_chemical_accident.sync import SyncStatus, collect_all
        from services.ext165_chemical_accident.contract import SOURCE_ID
        from services.public_data_sync.errors import PageFencedError

        yyyy = ctx.metadata.get("yyyy")

        # GAP-B: support resume via ctx.metadata
        resume_snapshot_id: str | None = ctx.metadata.get("resume_snapshot_id")
        resume_from_page: int = int(ctx.metadata.get("resume_from_page", 1))
        expected_total: int | None = ctx.metadata.get("expected_total_count")

        snapshot_id: str | None = None
        is_resume = bool(resume_snapshot_id)

        if is_resume:
            snapshot_id = resume_snapshot_id
            initial_db_count: int = int(ctx.metadata.get("checkpoint_total_count", 0))
        else:
            try:
                snapshot_id = create_staging_snapshot(ctx.run_id, source_id=SOURCE_ID)
            except Exception as exc:
                return self._fail(ctx, "STAGING_CREATE_ERROR", type(exc).__name__)
            initial_db_count = 0

        # R3-02: track items actually saved to DB
        total_in_db: list[int] = [initial_db_count]

        def _on_page_complete(page_no: int, page_items: Any, total_collected: int, total_count_from_api: int | None) -> None:
            """PATCH-02/03: atomic page save + checkpoint via RPC with pre-write fencing.
            PageFencedError re-raised so sync.collect_all returns FENCED immediately.
            """
            from services.public_data_sync.errors import PageFencedError
            try:
                actual = save_page_checkpoint(snapshot_id, page_items, page_no, total_count_from_api, run_id=ctx.run_id)
                total_in_db[0] = actual
            except PageFencedError:
                raise  # PATCH-03: stop collection immediately
            except Exception:
                pass  # non-fencing save failure: non-fatal

        try:
            sync = collect_all(
                yyyy=yyyy,
                request_budget=ctx.request_budget,
                start_page_no=resume_from_page,
                on_page_complete=_on_page_complete,
                expected_total_count=expected_total,
            )
        except Exception as exc:
            self._safe_fail_snapshot(snapshot_id, type(exc).__name__)
            return self._fail(ctx, "COLLECT_EXCEPTION", type(exc).__name__)

        if sync.status in (SyncStatus.FAILED, SyncStatus.ABORTED_TOTAL_CHANGED):
            self._safe_fail_snapshot(snapshot_id, sync.error_code or "COLLECT_FAILED")
            return RunResult(
                run_id=ctx.run_id,
                source_id=ctx.source_id,
                status=RunStatus.FAILED,
                started_at=ctx.started_at,
                finished_at=datetime.now(timezone.utc),
                fetched=sync.fetched,
                error_code=sync.error_code,
                error_message=sync.error_message,
                details={"budget_used": sync.budget_used, "pages": sync.pages_fetched},
            )

        # R3-02: on resume, compute hash from DB
        if is_resume:
            content_hash = compute_content_hash_from_db(snapshot_id)
        else:
            content_hash = compute_content_hash(sync.items)

        # GAP-D/R3-03: atomic promotion — RPC verifies run ownership + item count
        try:
            promoted = atomic_complete_snapshot(
                snapshot_id,
                source_id=SOURCE_ID,
                total_items=total_in_db[0],
                content_hash=content_hash,
                run_id=ctx.run_id,
            )
        except Exception as exc:
            self._safe_fail_snapshot(snapshot_id, type(exc).__name__)
            return self._fail(ctx, "PROMOTE_ERROR", type(exc).__name__)

        if not promoted:
            return self._fail(ctx, "PROMOTE_FENCED", "atomic snapshot promotion rejected")

        run_status = RunStatus.SUCCESS if sync.status == SyncStatus.COMPLETED else RunStatus.PARTIAL
        return RunResult(
            run_id=ctx.run_id,
            source_id=ctx.source_id,
            status=run_status,
            started_at=ctx.started_at,
            finished_at=datetime.now(timezone.utc),
            fetched=total_in_db[0],
            created=total_in_db[0],
            content_hash=content_hash,
            change_detected=total_in_db[0] > 0,
            details={
                "snapshot_id": snapshot_id,
                "budget_used": sync.budget_used,
                "pages": sync.pages_fetched,
                "yyyy": yyyy,
                "stop_reason": sync.error_code,
                "resumed_from_page": resume_from_page if is_resume else None,
            },
        )

    @staticmethod
    def _safe_fail_snapshot(snapshot_id: str | None, reason: str) -> None:
        if snapshot_id is None:
            return
        try:
            from services.ext165_chemical_accident.store import fail_snapshot
            fail_snapshot(snapshot_id, error_message=reason)
        except Exception:
            pass

    @staticmethod
    def _fail(ctx: RunContext, error_code: str, error_message: str) -> RunResult:
        return RunResult(
            run_id=ctx.run_id,
            source_id=ctx.source_id,
            status=RunStatus.FAILED,
            started_at=ctx.started_at,
            finished_at=datetime.now(timezone.utc),
            error_code=error_code,
            error_message=error_message,
        )
