"""Shared Search Query Understanding — WO-TAI-SHARED-SEARCH-F3 §17-§20.

Wraps the existing `services.search_query_svc.lookup()` (and the
underlying Search Dictionary / Kiwi runtime) to produce a structured
`SearchQueryPlan`.  The retrieval engine (retrieval.py) consumes this
plan without re-implementing any dictionary or tokenisation logic.

Rules:
- No new Dictionary implementation.
- No new Kiwi instantiation (reuses search_query_svc lazy singleton).
- Tier vocabulary (EXACT, SYNONYM_OF, TOKEN, …) is read-only.
- Identifier (source_key / canonical_id) gate is checked here so the
  retrieval engine can short-circuit without touching FTS/trigram.

Public surface:

    build_query_plan(q, object_types, visibility_scopes, page, page_size)
    → SearchQueryPlan
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Re-export for retrieval.py (no re-implementation).
from services.search_query_svc import lookup as _dict_lookup, SearchDictError


# ---------------------------------------------------------------------------
# Constants — tier names. Not changed (WO §17).
# ---------------------------------------------------------------------------
TIER_IDENTIFIER_EXACT = "IDENTIFIER_EXACT"
TIER_CANONICAL_EXACT  = "CANONICAL_EXACT"
TIER_SUBJECT          = "SUBJECT"
TIER_TITLE_EXACT      = "TITLE_EXACT"
TIER_ALIAS_EXACT      = "ALIAS_EXACT"
TIER_CONTEXT          = "CONTEXT"
TIER_FTS              = "FTS"
TIER_TRIGRAM          = "TRIGRAM"

TIER_PRECEDENCE: list[str] = [
    TIER_IDENTIFIER_EXACT,
    TIER_CANONICAL_EXACT,
    TIER_SUBJECT,
    TIER_TITLE_EXACT,
    TIER_ALIAS_EXACT,
    TIER_CONTEXT,
    TIER_FTS,
    TIER_TRIGRAM,
]


@dataclass
class SubjectCandidate:
    """One subject hit from the Search Dictionary."""
    subject_type: str
    subject_key: str
    matched_term: str
    match_type: str    # EXACT / SYNONYM_OF / TOKEN / TRIGRAM / …
    score: float


@dataclass
class SearchQueryPlan:
    """Structured output of query understanding.

    The retrieval engine uses this to decide which tiers to execute
    and in what order.
    """
    raw_query: str
    normalized_query: str         # stripped, lower-cased
    active_tiers: list[str]

    # Identifier gate (§19): if the query string looks like a known
    # source_key / canonical_id it gets IDENTIFIER_EXACT priority.
    identifier_candidates: list[str] = field(default_factory=list)

    # Dictionary subject candidates (§20): each carries evidence that
    # the retrieval engine preserves in match_type / subject_match_type.
    subject_candidates: list[SubjectCandidate] = field(default_factory=list)

    # Caller-supplied filters (passed through, not interpreted here).
    object_types: list[str] = field(default_factory=list)
    visibility_scopes: list[str] = field(default_factory=list)
    page: int = 1
    page_size: int = 10

    # Which dictionary tiers actually ran (for diagnostics).
    dictionary_active_tiers: list[str] = field(default_factory=list)

    # Was the dictionary lookup successful?
    dictionary_ok: bool = True
    dictionary_error: Optional[str] = None


def build_query_plan(
    q: str,
    *,
    object_types: Optional[list[str]] = None,
    visibility_scopes: Optional[list[str]] = None,
    page: int = 1,
    page_size: int = 10,
    dict_limit: int = 20,
) -> SearchQueryPlan:
    """Build a `SearchQueryPlan` for the given raw query string.

    Does NOT touch the DB.  Raises ``ValueError`` on blank query.
    """
    if not q or not q.strip():
        raise ValueError("query 'q' is required and must not be blank")

    normalized = q.strip()

    plan = SearchQueryPlan(
        raw_query=q,
        normalized_query=normalized,
        active_tiers=list(TIER_PRECEDENCE),  # all tiers eligible by default
        object_types=list(object_types or []),
        visibility_scopes=list(visibility_scopes or ["PUBLIC"]),
        page=page,
        page_size=page_size,
    )

    # Identifier gate (§19): a raw query that is syntactically an
    # identifier (no whitespace, plausible length) is surfaced as a
    # candidate for IDENTIFIER_EXACT and CANONICAL_EXACT tiers.
    # The engine still falls through to lower tiers if no match is found.
    stripped = normalized.strip()
    if stripped and " " not in stripped and len(stripped) >= 2:
        plan.identifier_candidates = [stripped]

    # Dictionary lookup (§20): reuse the Search Dictionary / Kiwi
    # singleton.  If it fails we record the error and continue with
    # non-subject tiers only.
    try:
        dict_result = _dict_lookup(normalized, limit=dict_limit)
        items = dict_result.get("items") or []
        plan.dictionary_active_tiers = dict_result.get("active_tiers") or []
        plan.subject_candidates = [
            SubjectCandidate(
                subject_type=it.get("subject_type", ""),
                subject_key=it.get("subject_key", ""),
                matched_term=it.get("matched_term", normalized),
                match_type=it.get("match_type", "EXACT"),
                score=float(it.get("score", 0)),
            )
            for it in items
            if it.get("subject_type") and it.get("subject_key")
        ]
    except SearchDictError as exc:
        plan.dictionary_ok = False
        plan.dictionary_error = str(exc)
        # Remove SUBJECT tier since dictionary failed.
        plan.active_tiers = [
            t for t in plan.active_tiers if t != TIER_SUBJECT
        ]

    return plan
