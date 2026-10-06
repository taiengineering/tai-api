"""Control Plane errors — programming errors vs runtime failures.

Programming errors (raise): unknown source_id, unregistered adapter.
Runtime failures: returned as RunResult(status=FAILED) — never raise.
"""
from __future__ import annotations


class PublicDataSyncError(Exception):
    """Base for all control-plane programming errors."""


class SourceNotFoundError(PublicDataSyncError):
    def __init__(self, source_id: str) -> None:
        super().__init__(f"Source not registered: {source_id!r}")
        self.source_id = source_id


class AdapterNotRegisteredError(PublicDataSyncError):
    def __init__(self, source_id: str) -> None:
        super().__init__(f"No adapter registered for source: {source_id!r}")
        self.source_id = source_id


class PreflightError(PublicDataSyncError):
    """Raised by adapter.preflight() to signal a hard configuration error."""
