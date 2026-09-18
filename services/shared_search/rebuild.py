"""FULL REBUILD framework with atomic promotion.

WO-TAI-SHARED-SEARCH-F1. Contract source:
- Constitution §10 (fail-closed; no partial promotion)
- Document Contract §11.1 (FULL REBUILD)

State machine:
    RUNNING → VALIDATED → PROMOTED
             ↘         ↘ (any failure)
              FAILED   FAILED

`promote()` performs the atomic swap in memory (mirrors the SQL
`public.promote_search_rebuild` function). Partial success is
never allowed to replace the current projection.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Optional

from services.shared_search.contract import (
    ALLOWED_RUN_STATUSES,
    ALLOWED_RUN_TYPES,
    PUBLICATION_STATUS_PUBLISHED,
    RUN_STATUS_FAILED,
    RUN_STATUS_PROMOTED,
    RUN_STATUS_RUNNING,
    RUN_STATUS_VALIDATED,
    RUN_TYPE_FULL,
    SearchContractError,
)
from services.shared_search.writer import MemoryStore, Writer, WriterRejected


class RebuildAborted(SearchContractError):
    """Raised when the rebuild framework refuses to promote."""


@dataclass
class RebuildRun:
    run_id: str
    run_type: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    expected_domains: tuple = ()
    completed_domains: tuple = ()
    candidate_count: int = 0
    current_count_before: Optional[int] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    manifest: dict = field(default_factory=dict)


class RebuildFramework:
    """One instance per rebuild attempt.

    Adapters call `framework.begin(expected_domains=[...])`, then
    stream `stage(...)` calls, then either `mark_domain_done(...)` for
    each Domain and finally `validate() -> promote()`.

    On any partial failure the caller invokes `fail(code, msg)` which
    marks the run FAILED and leaves the current projection untouched.
    """

    def __init__(self, store: MemoryStore, writer: Optional[Writer] = None):
        self.store = store
        self.writer = writer or Writer(store)

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    # ---------------------------------------------------------------
    # Lifecycle
    # ---------------------------------------------------------------
    def begin(
        self,
        *,
        expected_domains: Iterable[str],
        run_type: str = RUN_TYPE_FULL,
        manifest: Optional[dict] = None,
    ) -> RebuildRun:
        if run_type not in ALLOWED_RUN_TYPES:
            raise RebuildAborted(f"unknown run_type {run_type!r}")
        expected = tuple(dict.fromkeys(expected_domains))
        if not expected:
            raise RebuildAborted("expected_domains must be non-empty")
        run = RebuildRun(
            run_id=str(uuid.uuid4()),
            run_type=run_type,
            status=RUN_STATUS_RUNNING,
            started_at=self._now(),
            expected_domains=expected,
            manifest=dict(manifest or {}),
            current_count_before=self.store.count_current(),
        )
        self.store.insert_run({
            "run_id": run.run_id,
            "run_type": run.run_type,
            "status": run.status,
            "started_at": run.started_at.isoformat(),
            "expected_domains": list(run.expected_domains),
            "completed_domains": [],
            "candidate_count": 0,
            "current_count_before": run.current_count_before,
            "manifest": dict(run.manifest),
        })
        return run

    def stage(self, run: RebuildRun, payload: dict) -> None:
        if run.status != RUN_STATUS_RUNNING:
            raise RebuildAborted(f"cannot stage into run in status {run.status}")
        self.writer.stage(run.run_id, payload)
        run.candidate_count += 1
        self.store.update_run(run.run_id, candidate_count=run.candidate_count)

    def mark_domain_done(self, run: RebuildRun, domain: str) -> None:
        if domain not in run.expected_domains:
            raise RebuildAborted(
                f"domain {domain!r} not in expected {run.expected_domains}")
        if domain in run.completed_domains:
            return
        run.completed_domains = run.completed_domains + (domain,)
        self.store.update_run(run.run_id,
                              completed_domains=list(run.completed_domains))

    def validate(self, run: RebuildRun) -> None:
        """Move from RUNNING → VALIDATED iff every expected Domain
        reported completion and the run has at least one staged doc."""
        if run.status != RUN_STATUS_RUNNING:
            raise RebuildAborted(
                f"validate() called on run in status {run.status}")
        missing = set(run.expected_domains) - set(run.completed_domains)
        if missing:
            raise RebuildAborted(
                f"domains did not complete: {sorted(missing)}")
        if self.store.count_staging(run.run_id) == 0:
            raise RebuildAborted("no staged documents in this run")
        run.status = RUN_STATUS_VALIDATED
        self.store.update_run(run.run_id, status=RUN_STATUS_VALIDATED)

    def promote(self, run: RebuildRun) -> int:
        """Atomic swap: staged rows replace current. Only PUBLISHED
        staged rows enter the current projection; HOLD / REMOVED
        staged rows do NOT.
        """
        if run.status != RUN_STATUS_VALIDATED:
            raise RebuildAborted(
                f"promote() requires VALIDATED status; got {run.status}")

        # Snapshot current — used only if the swap raises, to prove
        # we didn't corrupt it. Foundation is single-process so an
        # exception aborts the caller; the SQL function relies on
        # transaction rollback for the same guarantee.
        current_snapshot = list(self.store.iter_current())
        try:
            promoted_count = 0
            # Build a NEW mapping from staging, filtering non-PUBLISHED.
            new_current: dict[tuple[str, str], dict] = {}
            for staged in self.store.iter_staging(run.run_id):
                wire = staged["document_json"]
                if wire.get("publication_status") != PUBLICATION_STATUS_PUBLISHED:
                    continue
                key = (wire["object_type"], wire["canonical_id"])
                new_current[key] = dict(wire)
                promoted_count += 1
            # Atomic swap in memory.
            self.store._current = new_current
            run.status = RUN_STATUS_PROMOTED
            run.completed_at = self._now()
            self.store.update_run(
                run.run_id,
                status=RUN_STATUS_PROMOTED,
                completed_at=run.completed_at.isoformat(),
            )
            return promoted_count
        except Exception:
            # Restore the current projection to guarantee no partial swap.
            self.store._current = {
                (r["object_type"], r["canonical_id"]): r
                for r in current_snapshot
            }
            self.fail(run, "PROMOTION_ERROR", "atomic swap raised")
            raise

    def fail(self, run: RebuildRun, error_code: str, error_message: str) -> None:
        run.status = RUN_STATUS_FAILED
        run.error_code = error_code
        run.error_message = error_message
        run.completed_at = self._now()
        self.store.update_run(
            run.run_id,
            status=RUN_STATUS_FAILED,
            error_code=error_code,
            error_message=error_message,
            completed_at=run.completed_at.isoformat(),
        )
