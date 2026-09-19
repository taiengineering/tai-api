"""Shared Retrieval Engine — WO-TAI-SHARED-SEARCH-F3 §21-§29.

ONE engine for Public, SaaS, and Paid (F4 passes different
visibility_scopes; no engine copy or modification needed).

Backend: OpenSearch via opensearch_reader.OpenSearchSearchReader.
PostgreSQL and Kiwi paths are not present in this module (§4).

Tier precedence (§21, fixed):
  T0  SOURCE_KEY_EXACT
  T1  CANONICAL_ID_EXACT
  T2  DICTIONARY_EXACT
  T3  DICTIONARY_EXPANSION
  T4  TITLE_EXACT
  T5  ALIAS_EXACT
  T6  SUBJECT_EXACT
  T7  CONTEXT_EXACT
  T8  BM25_NORI
  T9  FUZZY_FALLBACK

_msearch (§22): T0-T8 in ONE HTTP round-trip via opensearch_reader.
FUZZY_FALLBACK fires separately only when T0-T8 yield insufficient
results (§25).

Ranking (§29):
  tier precedence → _score DESC → source_updated_at DESC
  → object_type ASC → canonical_id ASC

Dedup (§28): (object_type, canonical_id), highest tier wins.
Pagination (§30): stable offset, page_size ≤ 50.
Visibility (§27): enforced in reader queries.
Legal authority (§7): no applicability fields produced.
CHEM public mode (§28): controlled by adapter layer, not engine.
"""
from __future__ import annotations

import json
from typing import Any, Iterable, Optional

from services.shared_search.query import (
    SearchQueryPlan,
    SubjectCandidate,
    TIER_BM25_NORI,
    TIER_CANONICAL_ID_EXACT,
    TIER_CONTEXT_EXACT,
    TIER_DICTIONARY_EXACT,
    TIER_DICTIONARY_EXPANSION,
    TIER_FUZZY_FALLBACK,
    TIER_PRECEDENCE,
    TIER_SOURCE_KEY_EXACT,
    TIER_SUBJECT_EXACT,
    TIER_TITLE_EXACT,
    TIER_ALIAS_EXACT,
    build_query_plan,
)
from services.shared_search.result import SearchResponse, SearchResult


# ---------------------------------------------------------------------------
# MemorySearchReader — unit tests only (§20)
# ---------------------------------------------------------------------------

class MemorySearchReader:
    """In-process reader for unit tests. No DB / no HTTP.

    Supports the same 10-tier vocabulary as OpenSearchSearchReader.
    PostgreSQL-specific tier names (FTS, TRIGRAM) are not present.
    """

    def __init__(self, documents: list[dict]):
        self._docs = list(documents)

    def _visible(self, doc: dict, visibility: list[str]) -> bool:
        if doc.get("publication_status") != "PUBLISHED":
            return False
        scopes = doc.get("visibility_scopes") or []
        return all(s in scopes for s in visibility)

    def _filter_type(self, docs: list[dict], object_types: list[str]) -> list[dict]:
        if not object_types:
            return docs
        return [d for d in docs if d.get("object_type") in object_types]

    def _base(self, ot: list[str], vis: list[str]) -> list[dict]:
        return self._filter_type(
            [d for d in self._docs if self._visible(d, vis)], ot
        )

    def run_msearch(
        self,
        *,
        normalized_query: str,
        identifier_candidates: list[str],
        subject_candidates: list[Any],
        object_types: list[str],
        visibility: list[str],
    ) -> dict[str, list[dict]]:
        """Return dict: tier_name → matching docs."""
        q   = normalized_query
        ot  = object_types
        vis = visibility
        result: dict[str, list[dict]] = {}

        def add(tier: str, docs: list[dict]) -> None:
            if docs:
                result.setdefault(tier, []).extend(docs)

        q_lower = q.lower()

        # T0: source_key exact
        for ident in identifier_candidates:
            add(TIER_SOURCE_KEY_EXACT,
                [d for d in self._base(ot, vis)
                 if (d.get("source_key") or "").lower() == ident.lower()])

        # T1: canonical_id exact
        for ident in identifier_candidates:
            add(TIER_CANONICAL_ID_EXACT,
                [d for d in self._base(ot, vis)
                 if (d.get("canonical_id") or "").lower() == ident.lower()])

        # T2/T3: dictionary subject candidates
        _dict_exact_types = {"EXACT", "NORMALIZED_EXACT", "PUNCTUATION", "EXACT_ALIAS"}
        for cand in subject_candidates:
            sk_lower = (cand.subject_key or "").lower()
            tier = (TIER_DICTIONARY_EXACT
                    if cand.match_type in _dict_exact_types
                    else TIER_DICTIONARY_EXPANSION)
            matching = []
            for d in self._base(ot, vis):
                subjects = d.get("subjects") or []
                if isinstance(subjects, str):
                    try:
                        subjects = json.loads(subjects)
                    except Exception:
                        subjects = []
                for s in subjects:
                    if isinstance(s, dict) and (s.get("subject_key") or "").lower() == sk_lower:
                        matching.append(d)
                        break
            add(tier, matching)

        # T4: title exact
        add(TIER_TITLE_EXACT,
            [d for d in self._base(ot, vis)
             if (d.get("title") or "").lower() == q_lower])

        # T5: alias exact
        add(TIER_ALIAS_EXACT,
            [d for d in self._base(ot, vis)
             if any((a or "").lower() == q_lower for a in (d.get("aliases") or []))])

        # T6: subject_key = raw query (single token)
        if " " not in q.strip():
            matching = []
            for d in self._base(ot, vis):
                subjects = d.get("subjects") or []
                if isinstance(subjects, str):
                    try:
                        subjects = json.loads(subjects)
                    except Exception:
                        subjects = []
                for s in subjects:
                    if isinstance(s, dict) and (s.get("subject_key") or "").lower() == q_lower:
                        matching.append(d)
                        break
            add(TIER_SUBJECT_EXACT, matching)

        # T7: context_key = raw query (single token)
        if " " not in q.strip():
            matching = []
            for d in self._base(ot, vis):
                ctx = d.get("context") or []
                if isinstance(ctx, str):
                    try:
                        ctx = json.loads(ctx)
                    except Exception:
                        ctx = []
                for c in ctx:
                    if isinstance(c, dict) and (c.get("context_key") or "").lower() == q_lower:
                        matching.append(d)
                        break
            add(TIER_CONTEXT_EXACT, matching)

        # T8: BM25_NORI — simple substring for tests
        tokens = q.lower().split()
        if tokens:
            add(TIER_BM25_NORI,
                [d for d in self._base(ot, vis)
                 if all(t in (d.get("search_text") or "").lower() for t in tokens)])

        return result

    def run_fuzzy(
        self,
        normalized_query: str,
        *,
        object_types: list[str],
        visibility: list[str],
    ) -> list[dict]:
        """FUZZY_FALLBACK: prefix/substring match on title."""
        q_lower = normalized_query.lower()
        return [
            d for d in self._base(object_types, visibility)
            if q_lower in (d.get("title") or "").lower()
        ]


# ---------------------------------------------------------------------------
# Retrieve function — combines query plan + reader
# ---------------------------------------------------------------------------

def _doc_sort_key(doc: dict, tier_idx: int) -> tuple:
    """Deterministic within-tier sort (§29):
    tier_idx ASC → _score DESC → source_updated_at DESC
    → object_type ASC → canonical_id ASC
    """
    score = float(doc.get("_opensearch_score") or 0)
    ts    = doc.get("source_updated_at") or ""
    return (tier_idx, -score, -len(ts), ts[::-1],
            doc.get("object_type", ""), doc.get("canonical_id", ""))


def _make_result(
    doc: dict,
    *,
    tier_name: str,
    tier_idx: int,
    matched_on: Optional[str] = None,
    subject_candidate: Optional[SubjectCandidate] = None,
) -> SearchResult:
    r = SearchResult(
        object_type       = doc.get("object_type", ""),
        canonical_id      = doc.get("canonical_id", ""),
        title             = doc.get("title", ""),
        source_id         = doc.get("source_id", ""),
        source_key        = doc.get("source_key"),
        source_updated_at = doc.get("source_updated_at"),
        summary           = doc.get("summary"),
        public_url        = doc.get("public_url"),
        saas_url          = doc.get("saas_url"),
        match_type        = tier_name,
        matched_on        = matched_on,
        rank_tier         = tier_idx,
        opensearch_score  = doc.get("_opensearch_score"),
    )
    if subject_candidate is not None:
        r.subject_type       = subject_candidate.subject_type
        r.subject_key        = subject_candidate.subject_key
        r.subject_match_type = subject_candidate.match_type
        r.matched_term       = subject_candidate.matched_term
    return r


def retrieve(
    plan: SearchQueryPlan,
    reader: Any,  # MemorySearchReader | OpenSearchSearchReader
    *,
    fuzzy_trigger_threshold: int = 0,
) -> SearchResponse:
    """Execute the retrieval plan.

    1. Fire _msearch (T0-T8) via reader.run_msearch().
    2. Optionally fire FUZZY if hit count ≤ fuzzy_trigger_threshold (§25).
    3. Dedup by (object_type, canonical_id) — highest tier wins (§28).
    4. Sort globally by (tier_idx, -score, ts, otype, cid).
    5. Paginate (§30).
    """
    ot  = plan.object_types
    vis = plan.visibility_scopes

    tier_results = reader.run_msearch(
        normalized_query    = plan.normalized_query,
        identifier_candidates = plan.identifier_candidates,
        subject_candidates  = plan.subject_candidates,
        object_types        = ot,
        visibility          = vis,
    )

    # Materialise subject_candidate lookup for explanation preservation
    sk_to_cand: dict[str, SubjectCandidate] = {
        c.subject_key: c for c in plan.subject_candidates
    }

    # Dedup + collect — process tiers in TIER_PRECEDENCE order
    seen: dict[tuple[str, str], SearchResult] = {}
    active_tiers_hit: list[str] = []

    for tier_name in TIER_PRECEDENCE:
        docs = tier_results.get(tier_name)
        if not docs:
            continue
        tier_idx = TIER_PRECEDENCE.index(tier_name)
        if tier_name not in active_tiers_hit:
            active_tiers_hit.append(tier_name)
        sorted_docs = sorted(docs, key=lambda d: _doc_sort_key(d, tier_idx))
        for doc in sorted_docs:
            key = (doc.get("object_type", ""), doc.get("canonical_id", ""))
            if key not in seen:
                cand = None
                if tier_name in (TIER_DICTIONARY_EXACT, TIER_DICTIONARY_EXPANSION):
                    # try to find matching subject candidate for explanation
                    subjects = doc.get("subjects") or []
                    if isinstance(subjects, str):
                        try:
                            subjects = json.loads(subjects)
                        except Exception:
                            subjects = []
                    for s in subjects:
                        if isinstance(s, dict):
                            cand = sk_to_cand.get(s.get("subject_key", ""))
                            if cand:
                                break
                seen[key] = _make_result(
                    doc,
                    tier_name=tier_name,
                    tier_idx=tier_idx,
                    matched_on=plan.normalized_query,
                    subject_candidate=cand,
                )

    # FUZZY_FALLBACK (§25): only when upper tiers are insufficient
    if len(seen) <= fuzzy_trigger_threshold and TIER_FUZZY_FALLBACK in plan.active_tiers:
        fuzzy_docs = reader.run_fuzzy(plan.normalized_query, object_types=ot, visibility=vis)
        tier_idx   = TIER_PRECEDENCE.index(TIER_FUZZY_FALLBACK)
        if fuzzy_docs:
            active_tiers_hit.append(TIER_FUZZY_FALLBACK)
        for doc in fuzzy_docs:
            key = (doc.get("object_type", ""), doc.get("canonical_id", ""))
            if key not in seen:
                seen[key] = _make_result(
                    doc,
                    tier_name=TIER_FUZZY_FALLBACK,
                    tier_idx=tier_idx,
                    matched_on=plan.normalized_query,
                )

    # Global sort
    all_results = sorted(
        seen.values(),
        key=lambda r: (
            r.rank_tier,
            -(r.opensearch_score or 0),
            -(len(r.source_updated_at or "")),
            (r.source_updated_at or "")[::-1],
            r.object_type,
            r.canonical_id,
        ),
    )

    total = len(all_results)
    offset = (plan.page - 1) * plan.page_size
    page_results = all_results[offset: offset + plan.page_size]

    return SearchResponse(
        query      = plan.raw_query,
        page       = plan.page,
        page_size  = plan.page_size,
        total      = total,
        items      = page_results,
        active_tiers = active_tiers_hit,
        status     = "ok" if total > 0 else "empty",
    )


# ---------------------------------------------------------------------------
# SharedRetrievalEngine — convenience wrapper
# ---------------------------------------------------------------------------

class SharedRetrievalEngine:
    """Convenience wrapper: build_query_plan + retrieve.

    Public/SaaS/Paid pass different visibility_scopes.
    F4 reuses this class without modification.
    """

    def __init__(self, reader: Any):
        self._reader = reader

    def search(
        self,
        q: str,
        *,
        visibility_scopes: Optional[list[str]] = None,
        object_types: Optional[list[str]] = None,
        page: int = 1,
        page_size: int = 10,
        fuzzy_trigger_threshold: int = 0,
    ) -> SearchResponse:
        """End-to-end retrieval. Raises ValueError on blank query (§35)."""
        plan = build_query_plan(
            q,
            object_types      = object_types,
            visibility_scopes = visibility_scopes or ["PUBLIC"],
            page              = page,
            page_size         = min(max(1, page_size), 50),
        )
        return retrieve(plan, self._reader,
                        fuzzy_trigger_threshold=fuzzy_trigger_threshold)
