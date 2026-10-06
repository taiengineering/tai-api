"""Abstract base for all public-data source adapters."""
from __future__ import annotations

from abc import ABC, abstractmethod

from services.public_data_sync.contracts import RunContext, RunResult


class SourceAdapter(ABC):
    """Every concrete adapter must implement these three methods."""

    @property
    @abstractmethod
    def source_id(self) -> str:
        """Must match exactly the SourceSpec.source_id this adapter handles."""

    def preflight(self, ctx: RunContext) -> None:
        """Validate configuration before any I/O.

        Raise PreflightError if a required credential or config is missing.
        Default: no-op (adapter handles its own validation in execute).
        """

    @abstractmethod
    def execute(self, ctx: RunContext) -> RunResult:
        """Run the sync. Must return RunResult — never raise for runtime errors."""
