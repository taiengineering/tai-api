"""Control Plane errors — programming errors vs runtime failures.

Programming errors (raise): unknown source_id, unregistered adapter.
Runtime failures: returned as RunResult(status=FAILED) — never raise.
Runtime infrastructure errors (raise): DB claim/complete RPC failure, fenced completion.
"""
from __future__ import annotations


class PublicDataSyncError(Exception):
    """Base for all control-plane programming errors."""


class SourceNotFoundError(PublicDataSyncError):
    def __init__(self, source_id: str) -> None:
        super().__init__(f"Source not registered: {source_id!r}")
        self.source_id = source_id


class AdapterNotRegisteredError(PublicDataSyncError):
    def __init__(self, adapter_key: str) -> None:
        super().__init__(f"No adapter registered for key: {adapter_key!r}")
        self.adapter_key = adapter_key


class PreflightError(PublicDataSyncError):
    """Raised by adapter.preflight() to signal a hard configuration error."""


class RuntimeClaimError(PublicDataSyncError):
    """DB/RPC infrastructure failure OR DB invariant violation during claim_run.

    Distinct from a normal claim rejection (DISABLED, NOT_DUE, SOURCE_BUSY, etc.).
    Callers must not interpret this as a skip decision.
    reason is a DB contract code (e.g. UNKNOWN_SOURCE_RUNTIME) — never a raw message.
    """

    def __init__(self, source_id: str, reason: str | None = None) -> None:
        detail = f" reason={reason!r}" if reason is not None else ""
        super().__init__(
            f"Claim infrastructure/invariant failure: source={source_id!r}{detail}"
        )
        self.source_id = source_id
        self.reason = reason


class RuntimeCompletionError(PublicDataSyncError):
    """DB/RPC infrastructure failure during complete_run.

    The run result may be correct but terminal evidence was not persisted.
    """

    def __init__(self, run_id: str) -> None:
        super().__init__(f"Completion infrastructure failure for run: {run_id!r}")
        self.run_id = run_id


class RuntimeFencedError(PublicDataSyncError):
    """complete_run returned false — source runtime ownership was lost before completion.

    Occurs when stale recovery or a concurrent process cleared current_run_id before
    this run could persist its terminal state.
    """

    def __init__(self, run_id: str, source_id: str) -> None:
        super().__init__(
            f"Run fenced — source ownership lost: source={source_id!r} run={run_id!r}"
        )
        self.run_id = run_id
        self.source_id = source_id
