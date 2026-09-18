"""WO-TAI-SHARED-SEARCH-F1 — Shared Search Foundation.

Pure logic + memory store for the unified search projection. Domain
adapters (F2), retrieval engine (F3), and consumer wiring (F4) build
on top of this module. Foundation is store-agnostic — a Supabase
adapter will land under production_store.py in a later WO.

Public surface:

    contract          -- vocabulary constants + validators
    document          -- SearchDocument dataclass + normalization
    hash_utils        -- deterministic content_hash
    writer            -- MemoryStore + Writer (validate/normalize/hash/upsert/tombstone)
    rebuild           -- FULL REBUILD framework with atomic promotion
    reconcile         -- READ-only Domain SoT ↔ current projection reconciler

Contract source of truth:

    docs/search/TAI_SHARED_SEARCH_CONSTITUTION_v1.md
    docs/search/TAI_SHARED_SEARCH_DOCUMENT_CONTRACT_v1.md
    docs/search/TAI_SHARED_SEARCH_RESULT_CONTRACT_v1.md

Physical DB schema:

    supabase/migrations/20260919_shared_search_foundation.sql
"""
from services.shared_search.contract import (
    PUBLICATION_STATUS_PUBLISHED,
    PUBLICATION_STATUS_HOLD,
    PUBLICATION_STATUS_REMOVED,
    ALLOWED_PUBLICATION_STATUSES,
    VISIBILITY_PUBLIC,
    VISIBILITY_SAAS,
    VISIBILITY_PAID,
    VISIBILITY_INTERNAL,
    ALLOWED_VISIBILITY_SCOPES,
    ALLOWED_CONTEXT_TYPES,
    RUN_STATUS_RUNNING,
    RUN_STATUS_VALIDATED,
    RUN_STATUS_PROMOTED,
    RUN_STATUS_FAILED,
    SearchContractError,
)
from services.shared_search.document import (
    SearchDocument,
    normalize_document,
)
from services.shared_search.hash_utils import content_hash
from services.shared_search.writer import (
    MemoryStore,
    Writer,
    WriterRejected,
)
from services.shared_search.rebuild import (
    RebuildRun,
    RebuildFramework,
    RebuildAborted,
)
from services.shared_search.reconcile import (
    ReconcileReport,
    reconcile,
)

__all__ = [
    "PUBLICATION_STATUS_PUBLISHED", "PUBLICATION_STATUS_HOLD",
    "PUBLICATION_STATUS_REMOVED", "ALLOWED_PUBLICATION_STATUSES",
    "VISIBILITY_PUBLIC", "VISIBILITY_SAAS", "VISIBILITY_PAID",
    "VISIBILITY_INTERNAL", "ALLOWED_VISIBILITY_SCOPES",
    "ALLOWED_CONTEXT_TYPES",
    "RUN_STATUS_RUNNING", "RUN_STATUS_VALIDATED",
    "RUN_STATUS_PROMOTED", "RUN_STATUS_FAILED",
    "SearchContractError",
    "SearchDocument", "normalize_document",
    "content_hash",
    "MemoryStore", "Writer", "WriterRejected",
    "RebuildRun", "RebuildFramework", "RebuildAborted",
    "ReconcileReport", "reconcile",
]
