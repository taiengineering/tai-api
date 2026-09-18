"""Shared Search vocabulary constants + typed contract error.

WO-TAI-SHARED-SEARCH-F1. Kept minimal — every value here is a
contract clause enforced somewhere downstream:

- `ALLOWED_PUBLICATION_STATUSES` matches the SQL CHECK on
  `search_documents.publication_status`.
- `ALLOWED_VISIBILITY_SCOPES` matches Document Contract §7.
- `ALLOWED_CONTEXT_TYPES` matches Document Contract §8.
- Rebuild run statuses match the SQL CHECK on
  `search_rebuild_runs.status`.
"""
from __future__ import annotations


# --- publication_status --------------------------------------------------
PUBLICATION_STATUS_PUBLISHED = "PUBLISHED"
PUBLICATION_STATUS_HOLD = "HOLD"
PUBLICATION_STATUS_REMOVED = "REMOVED"

ALLOWED_PUBLICATION_STATUSES = frozenset({
    PUBLICATION_STATUS_PUBLISHED,
    PUBLICATION_STATUS_HOLD,
    PUBLICATION_STATUS_REMOVED,
})

# --- visibility_scopes ---------------------------------------------------
VISIBILITY_PUBLIC = "PUBLIC"
VISIBILITY_SAAS = "SAAS"
VISIBILITY_PAID = "PAID"
VISIBILITY_INTERNAL = "INTERNAL"

ALLOWED_VISIBILITY_SCOPES = frozenset({
    VISIBILITY_PUBLIC, VISIBILITY_SAAS,
    VISIBILITY_PAID, VISIBILITY_INTERNAL,
})

# --- context_type --------------------------------------------------------
ALLOWED_CONTEXT_TYPES = frozenset({
    "process", "task", "equipment", "chemical",
    "legal_obligation", "risk_factor", "sector",
})

# --- rebuild run statuses ------------------------------------------------
RUN_STATUS_RUNNING = "RUNNING"
RUN_STATUS_VALIDATED = "VALIDATED"
RUN_STATUS_PROMOTED = "PROMOTED"
RUN_STATUS_FAILED = "FAILED"

ALLOWED_RUN_STATUSES = frozenset({
    RUN_STATUS_RUNNING, RUN_STATUS_VALIDATED,
    RUN_STATUS_PROMOTED, RUN_STATUS_FAILED,
})

RUN_TYPE_FULL = "FULL"
RUN_TYPE_DOMAIN = "DOMAIN"
ALLOWED_RUN_TYPES = frozenset({RUN_TYPE_FULL, RUN_TYPE_DOMAIN})

# --- tenant / secret field allowlist (guard §7.3) ------------------------
# Fields that MUST NOT appear on any SearchDocument. If a caller sneaks
# one in the writer rejects.
FORBIDDEN_DOCUMENT_KEYS = frozenset({
    "company_id", "factory_id", "user_id",
    "diagnosis_answer", "diagnosis_answers", "diagnosis_result",
    "api_key", "api_token", "access_token", "secret",
    # legal-applicability leakage (see Constitution §2)
    "legal_applicable", "applicability_score", "is_required",
    "compliance_score", "violation",
    # LLM-inference leakage (Constitution §8; also Result Contract §10)
    "llm_inferred", "llm_reasoning",
})


class SearchContractError(ValueError):
    """Raised when a SearchDocument violates the Shared Search contract."""
