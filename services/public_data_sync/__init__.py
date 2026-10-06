"""Public-data sync: census/diff primitives + Control Plane foundation."""
from services.public_data_sync.census import (
    CensusDiff,
    CensusError,
    diff_identity_maps,
    validate_identity_census,
)
from services.public_data_sync.contracts import (
    RunContext,
    RunResult,
    RunStatus,
    SourceKind,
    SourceMode,
    SourceSpec,
    TriggerKind,
)
from services.public_data_sync.errors import (
    AdapterNotRegisteredError,
    PreflightError,
    PublicDataSyncError,
    RuntimeClaimError,
    RuntimeCompletionError,
    RuntimeFencedError,
    SourceNotFoundError,
)
from services.public_data_sync.registry import SourceRegistry, registry
from services.public_data_sync.runner import run_source
from services.public_data_sync.runtime import execute_due_source
from services.public_data_sync.runtime_store import ClaimResult, PublicDataRuntimeStore

__all__ = [
    # census primitives (existing contract — do not remove)
    "CensusDiff",
    "CensusError",
    "diff_identity_maps",
    "validate_identity_census",
    # contracts
    "RunContext",
    "RunResult",
    "RunStatus",
    "SourceKind",
    "SourceMode",
    "SourceSpec",
    "TriggerKind",
    # errors
    "AdapterNotRegisteredError",
    "PreflightError",
    "PublicDataSyncError",
    "RuntimeClaimError",
    "RuntimeCompletionError",
    "RuntimeFencedError",
    "SourceNotFoundError",
    # registry
    "SourceRegistry",
    "registry",
    # runner
    "run_source",
    # runtime
    "execute_due_source",
    # runtime_store
    "ClaimResult",
    "PublicDataRuntimeStore",
]
