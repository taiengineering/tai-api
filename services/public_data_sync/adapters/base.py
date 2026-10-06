"""Abstract base for all public-data source adapters."""
from __future__ import annotations

from abc import ABC, abstractmethod

from services.public_data_sync.contracts import RunContext, RunResult


class SourceAdapter(ABC):
    """Every concrete adapter must implement these two methods."""

    @property
    @abstractmethod
    def adapter_key(self) -> str:
        """Must match exactly the SourceSpec.adapter_key this adapter handles."""

    def preflight(self, ctx: RunContext) -> None:
        """Validate configuration before any I/O.

        Raise PreflightError if a required credential or config is missing.
        Default: no-op.
        """

    @abstractmethod
    def run(self, ctx: RunContext) -> RunResult:
        """Execute the sync. Must return RunResult — never raise for runtime errors."""
