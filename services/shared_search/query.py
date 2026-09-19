"""Shared Search Query Understanding — WO-TAI-SHARED-SEARCH-F3 §17-§20.

Wraps `services.search_query_svc.lookup_deterministic()` (T1-T3 only,
deterministic-only path, Kiwi = 0) to produce a `SearchQueryPlan`.

Invariant (§17):
    services/shared_search/** → Kiwi import/call = 0

Rules:
- No new Dictionary implementation.
- No new Kiwi instantiation.
- Tier vocabulary (EXACT, SYNONYM_OF, …) is read-only from search_core.
- Identifier gate (§19): single-token queries checked as source_key /
  canonical_id candidates before any BM25 or fuzzy runs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# lookup_deterministic: T1-T3 only (EXACT, NORMALIZED_EXACT, PUNCTUATION,
# approved expansions). No Kiwi TOKEN. Deterministic-only path.
from services.search_query_svc import (
    lookup_deterministic as _dict_lookup,
    SearchDictError,
)


# ---------------------------------------------------------------------------
# Tier vocabulary (§21)
# ---------------------------------------------------------------------------
TIER_SOURCE_KEY_EXACT       = "SOURCE_KEY_EXACT"
TIER_CANONICAL_ID_EXACT     = "CANONICAL_ID_EXACT"
TIER_DICTIONARY_EXACT       = "DICTIONARY_EXACT"
TIER_DICTIONARY_EXPANSION   = "DICTIONARY_EXPANSION"
TIER_TITLE_EXACT            = "TITLE_EXACT"
TIER_ALIAS_EXACT            = "ALIAS_EXACT"
TIER_SUBJECT_EXACT          = "SUBJECT_EXACT"
TIER_CONTEXT_EXACT          = "CONTEXT_EXACT"
TIER_BM25_NORI              = "BM25_NORI"
TIER_FUZZY_FALLBACK         = "FUZZY_FALLBACK"

TIER_PRECEDENCE: list[str] = [
    TIER_SOURCE_KEY_EXACT,
    TIER_CANONICAL_ID_EXACT,
    TIER_DICTIONARY_EXACT,
    TIER_DICTIONARY_EXPANSION,
    TIER_TITLE_EXACT,
    TIER_ALIAS_EXACT,
    TIER_SUBJECT_EXACT,
    TIER_CONTEXT_EXACT,
    TIER_BM25_NORI,
    TIER_FUZZY_FALLBACK,
]

# Deterministic match types → DICTIONARY_EXACT tier
DICT_EXACT_MATCH_TYPES = frozenset({
    "EXACT", "NORMALIZED_EXACT", "PUNCTUATION", "EXACT_ALIAS",
})
# Approved expansion match types → DICTIONARY_EXPANSION tier
DICT_EXPANSION_MATCH_TYPES = frozenset({
    "ABBREVIATION_OF", "SPACING_VARIANT_OF", "PUNCTUATION_VARIANT_OF",
    "SPELLING_VARIANT_OF", "ENGLISH_OF", "SYNONYM_OF",
})


@dataclass
class SubjectCandidate:
    """One subject hit from the Search Dictionary."""
    subject_type: str
    subject_key:  str
    matched_term: str
    match_type:   str    # from DICT_EXACT_MATCH_TYPES or DICT_EXPANSION_MATCH_TYPES
    score:        float


@dataclass
class SearchQueryPlan:
    """Structured output of query understanding.

    The retrieval engine uses this to drive _msearch tier construction.
    """
    raw_query:              str
    normalized_query:       str
    active_tiers:           list[str]

    # Identifier gate (§19): single-token queries → SOURCE_KEY / CANONICAL_ID candidates
    identifier_candidates:  list[str] = field(default_factory=list)

    # Dictionary candidates (§20, §23)
    subject_candidates:     list[SubjectCandidate] = field(default_factory=list)

    # Caller-supplied filters
    object_types:           list[str] = field(default_factory=list)
    visibility_scopes:      list[str] = field(default_factory=list)
    page:                   int = 1
    page_size:              int = 10

    # Dictionary diagnostic
    dictionary_active_tiers:  list[str] = field(default_factory=list)
    dictionary_ok:            bool = True
    dictionary_error:         Optional[str] = None


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

    Kiwi is NOT called here (§17 invariant).
    Raises ``ValueError`` on blank query.
    """
    if not q or not q.strip():
        raise ValueError("query 'q' is required and must not be blank")

    normalized = q.strip()

    plan = SearchQueryPlan(
        raw_query=q,
        normalized_query=normalized,
        active_tiers=list(TIER_PRECEDENCE),
        object_types=list(object_types or []),
        visibility_scopes=list(visibility_scopes or ["PUBLIC"]),
        page=page,
        page_size=page_size,
    )

    # Identifier gate (§19): single-token → SOURCE_KEY / CANONICAL_ID candidates
    if normalized and " " not in normalized and len(normalized) >= 2:
        plan.identifier_candidates = [normalized]

    # Deterministic dictionary lookup (§16, §20)
    try:
        dict_result = _dict_lookup(normalized, limit=dict_limit)
        items = dict_result.get("items") or []
        plan.dictionary_active_tiers = dict_result.get("active_tiers") or []
        candidates = []
        for it in items:
            st = it.get("subject_type", "")
            sk = it.get("subject_key", "")
            mt = it.get("match_type", "EXACT")
            if st and sk:
                candidates.append(SubjectCandidate(
                    subject_type=st,
                    subject_key=sk,
                    matched_term=it.get("matched_term", normalized),
                    match_type=mt,
                    score=float(it.get("score", 0)),
                ))
        plan.subject_candidates = candidates
    except SearchDictError as exc:
        plan.dictionary_ok = False
        plan.dictionary_error = str(exc)
        # Remove DICTIONARY_EXACT / EXPANSION from active tiers
        plan.active_tiers = [
            t for t in plan.active_tiers
            if t not in (TIER_DICTIONARY_EXACT, TIER_DICTIONARY_EXPANSION)
        ]

    return plan
