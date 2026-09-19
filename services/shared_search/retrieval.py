"""Shared Retrieval Engine — WO-TAI-SHARED-SEARCH-F3 §21-§29.

ONE engine used by Public, SaaS, and Paid.  F4 MUST NOT copy this;
it passes different `visibility_scopes` instead.

Architecture
------------
`SharedRetrievalEngine` accepts a `SearchDocumentReader` Protocol.
Two implementations are provided:

  MemorySearchReader   — for unit tests (no DB).
  SupabaseSearchReader — production (Supabase-py client against
                         search_documents after GATE-1 apply).

Query plan comes from `query.py` (which wraps search_query_svc).
Result contract is in `result.py`.

Tier precedence (§22, fixed):
  1. IDENTIFIER_EXACT
  2. CANONICAL_EXACT
  3. SUBJECT
  4. TITLE_EXACT
  5. ALIAS_EXACT
  6. CONTEXT
  7. FTS
  8. TRIGRAM

Ranking within a tier (§24):
  tier precedence → source_updated_at DESC → object_type ASC → canonical_id ASC

Dedup (§25): (object_type, canonical_id); highest tier wins.
Pagination (§26): stable offset pagination with deterministic ordering.
Visibility (§27): publication_status=PUBLISHED AND scope ∈ visibility_scopes.
Legal authority (§29): no applicability fields produced here.
"""
from __future__ import annotations

import json
from typing import Any, Callable, Iterable, Optional, Protocol, runtime_checkable

from services.shared_search.query import (
    SearchQueryPlan,
    SubjectCandidate,
    TIER_ALIAS_EXACT,
    TIER_CANONICAL_EXACT,
    TIER_CONTEXT,
    TIER_FTS,
    TIER_IDENTIFIER_EXACT,
    TIER_PRECEDENCE,
    TIER_SUBJECT,
    TIER_TITLE_EXACT,
    TIER_TRIGRAM,
    build_query_plan,
)
from services.shared_search.result import SearchResponse, SearchResult


# ---------------------------------------------------------------------------
# Reader Protocol — abstraction over DB / memory (testable without DB)
# ---------------------------------------------------------------------------

@runtime_checkable
class SearchDocumentReader(Protocol):
    """Read-only access to the search_documents projection.

    Every method returns raw dicts from the projection (same keys as
    the SQL table). The engine normalises them into `SearchResult`.

    `object_types` — if non-empty, restrict results to these types.
    `visibility`   — list of required scopes (e.g. ["PUBLIC"]).
    """

    def query_identifier_exact(
        self, q: str, *, object_types: list[str], visibility: list[str]
    ) -> list[dict]: ...

    def query_canonical_exact(
        self, q: str, *, object_types: list[str], visibility: list[str]
    ) -> list[dict]: ...

    def query_subject(
        self, subject_key: str, *, object_types: list[str], visibility: list[str]
    ) -> list[dict]: ...

    def query_title_exact(
        self, title: str, *, object_types: list[str], visibility: list[str]
    ) -> list[dict]: ...

    def query_alias_exact(
        self, alias: str, *, object_types: list[str], visibility: list[str]
    ) -> list[dict]: ...

    def query_context(
        self, context_key: str, *, object_types: list[str], visibility: list[str]
    ) -> list[dict]: ...

    def query_fts(
        self, q: str, *, object_types: list[str], visibility: list[str]
    ) -> list[dict]: ...

    def query_trigram(
        self, q: str, *, object_types: list[str], visibility: list[str],
        similarity_threshold: float,
    ) -> list[dict]: ...


# ---------------------------------------------------------------------------
# MemorySearchReader — in-process store for unit tests
# ---------------------------------------------------------------------------

class MemorySearchReader:
    """Implements SearchDocumentReader against an in-process list.

    Accepts dicts matching the search_documents schema.
    Used exclusively in tests — never in production paths.
    """

    def __init__(self, documents: list[dict]):
        self._docs = list(documents)

    # --- helpers ---

    def _visible(self, doc: dict, visibility: list[str]) -> bool:
        if doc.get("publication_status") != "PUBLISHED":
            return False
        scopes = doc.get("visibility_scopes") or []
        return all(s in scopes for s in visibility)

    def _filter_type(self, docs: list[dict], object_types: list[str]) -> list[dict]:
        if not object_types:
            return docs
        return [d for d in docs if d.get("object_type") in object_types]

    def _base(self, object_types: list[str], visibility: list[str]) -> list[dict]:
        return self._filter_type(
            [d for d in self._docs if self._visible(d, visibility)],
            object_types,
        )

    # --- tier implementations ---

    def query_identifier_exact(
        self, q: str, *, object_types: list[str], visibility: list[str]
    ) -> list[dict]:
        q_lower = q.lower()
        return [
            d for d in self._base(object_types, visibility)
            if (d.get("source_key") or "").lower() == q_lower
        ]

    def query_canonical_exact(
        self, q: str, *, object_types: list[str], visibility: list[str]
    ) -> list[dict]:
        q_lower = q.lower()
        return [
            d for d in self._base(object_types, visibility)
            if (d.get("canonical_id") or "").lower() == q_lower
        ]

    def query_subject(
        self, subject_key: str, *, object_types: list[str], visibility: list[str]
    ) -> list[dict]:
        key_lower = subject_key.lower()
        result = []
        for d in self._base(object_types, visibility):
            subjects = d.get("subjects") or []
            if isinstance(subjects, str):
                try:
                    subjects = json.loads(subjects)
                except Exception:
                    subjects = []
            for s in subjects:
                if isinstance(s, dict) and (s.get("subject_key") or "").lower() == key_lower:
                    result.append(d)
                    break
        return result

    def query_title_exact(
        self, title: str, *, object_types: list[str], visibility: list[str]
    ) -> list[dict]:
        t_lower = title.lower()
        return [
            d for d in self._base(object_types, visibility)
            if (d.get("title") or "").lower() == t_lower
        ]

    def query_alias_exact(
        self, alias: str, *, object_types: list[str], visibility: list[str]
    ) -> list[dict]:
        a_lower = alias.lower()
        return [
            d for d in self._base(object_types, visibility)
            if any(
                (a or "").lower() == a_lower
                for a in (d.get("aliases") or [])
            )
        ]

    def query_context(
        self, context_key: str, *, object_types: list[str], visibility: list[str]
    ) -> list[dict]:
        ck_lower = context_key.lower()
        result = []
        for d in self._base(object_types, visibility):
            ctx = d.get("context") or []
            if isinstance(ctx, str):
                try:
                    ctx = json.loads(ctx)
                except Exception:
                    ctx = []
            for c in ctx:
                if isinstance(c, dict) and (c.get("context_key") or "").lower() == ck_lower:
                    result.append(d)
                    break
        return result

    def query_fts(
        self, q: str, *, object_types: list[str], visibility: list[str]
    ) -> list[dict]:
        """Simple substring FTS fallback for tests.
        Production uses to_tsvector(simple, search_text) @@ plainto_tsquery."""
        tokens = q.lower().split()
        if not tokens:
            return []
        result = []
        for d in self._base(object_types, visibility):
            text = (d.get("search_text") or "").lower()
            if all(t in text for t in tokens):
                result.append(d)
        return result

    def query_trigram(
        self, q: str, *, object_types: list[str], visibility: list[str],
        similarity_threshold: float = 0.3,
    ) -> list[dict]:
        """Simple prefix trigram fallback for tests.
        Production uses title % $q (pg_trgm)."""
        q_lower = q.lower()
        result = []
        for d in self._base(object_types, visibility):
            title = (d.get("title") or "").lower()
            if q_lower in title or title in q_lower:
                result.append(d)
        return result


# ---------------------------------------------------------------------------
# SupabaseSearchReader — production reader (SQL against search_documents)
# ---------------------------------------------------------------------------

class SupabaseSearchReader:
    """Production SearchDocumentReader backed by Supabase-py.

    All queries are READ-only SELECT statements. Zero write / RPC mutation.
    Index shapes must match 20260919_shared_search_retrieval.sql.
    """

    # Maximum rows fetched per tier query. The engine deduplicates
    # across tiers so over-fetching a little avoids losing results.
    _TIER_LIMIT = 500

    def __init__(self, client: Any):
        self._client = client

    def _visibility_filter(self, q: Any, visibility: list[str]) -> Any:
        """Apply publication_status + all required visibility_scopes."""
        q = q.eq("publication_status", "PUBLISHED")
        for scope in visibility:
            q = q.contains("visibility_scopes", [scope])
        return q

    def _type_filter(self, q: Any, object_types: list[str]) -> Any:
        if object_types:
            q = q.in_("object_type", object_types)
        return q

    def _select(self) -> Any:
        return self._client.table("search_documents").select(
            "object_type,canonical_id,title,summary,source_id,source_key,"
            "source_updated_at,public_url,saas_url,subjects,context,aliases,"
            "keywords,publication_status,visibility_scopes,content_hash"
        )

    def _run(self, q: Any) -> list[dict]:
        r = q.limit(self._TIER_LIMIT).execute()
        return list(getattr(r, "data", None) or [])

    def query_identifier_exact(
        self, q: str, *, object_types: list[str], visibility: list[str]
    ) -> list[dict]:
        query = self._select().eq("source_key", q)
        query = self._visibility_filter(query, visibility)
        query = self._type_filter(query, object_types)
        return self._run(query)

    def query_canonical_exact(
        self, q: str, *, object_types: list[str], visibility: list[str]
    ) -> list[dict]:
        query = self._select().eq("canonical_id", q)
        query = self._visibility_filter(query, visibility)
        query = self._type_filter(query, object_types)
        return self._run(query)

    def query_subject(
        self, subject_key: str, *, object_types: list[str], visibility: list[str]
    ) -> list[dict]:
        # subjects @> '[{"subject_key": "X"}]'::jsonb
        payload = json.dumps([{"subject_key": subject_key}])
        query = self._select().contains("subjects", payload)
        query = self._visibility_filter(query, visibility)
        query = self._type_filter(query, object_types)
        return self._run(query)

    def query_title_exact(
        self, title: str, *, object_types: list[str], visibility: list[str]
    ) -> list[dict]:
        # Case-insensitive exact via lower() index
        query = self._select().ilike("title", title)
        query = self._visibility_filter(query, visibility)
        query = self._type_filter(query, object_types)
        return self._run(query)

    def query_alias_exact(
        self, alias: str, *, object_types: list[str], visibility: list[str]
    ) -> list[dict]:
        query = self._select().contains("aliases", [alias])
        query = self._visibility_filter(query, visibility)
        query = self._type_filter(query, object_types)
        return self._run(query)

    def query_context(
        self, context_key: str, *, object_types: list[str], visibility: list[str]
    ) -> list[dict]:
        payload = json.dumps([{"context_key": context_key}])
        query = self._select().contains("context", payload)
        query = self._visibility_filter(query, visibility)
        query = self._type_filter(query, object_types)
        return self._run(query)

    def query_fts(
        self, q: str, *, object_types: list[str], visibility: list[str]
    ) -> list[dict]:
        # Uses FTS index: to_tsvector('simple', search_text) @@ ...
        # Supabase-py textSearch uses `@@` operator.
        query = self._select().text_search("search_text", q, config="simple")
        query = self._visibility_filter(query, visibility)
        query = self._type_filter(query, object_types)
        return self._run(query)

    def query_trigram(
        self, q: str, *, object_types: list[str], visibility: list[str],
        similarity_threshold: float = 0.3,
    ) -> list[dict]:
        # pg_trgm: title % $q — must use raw filter via Supabase-py
        # The GT filter on similarity() requires a raw SQL RPC or a
        # custom function. We use a Supabase RPC wrapper.
        # Fallback: if RPC unavailable, return empty (trigram is last resort).
        try:
            r = self._client.rpc(
                "search_by_trigram",
                {
                    "p_q": q,
                    "p_similarity": similarity_threshold,
                    "p_visibility": visibility,
                    "p_object_types": object_types or [],
                    "p_limit": self._TIER_LIMIT,
                },
            ).execute()
            return list(getattr(r, "data", None) or [])
        except Exception:
            return []


# ---------------------------------------------------------------------------
# Shared Retrieval Engine (§21-§29)
# ---------------------------------------------------------------------------

def _doc_sort_key(row: dict, tier_idx: int) -> tuple:
    """Deterministic sort key within a tier (§24):
    tier_precedence → source_updated_at DESC → object_type ASC → canonical_id ASC
    """
    # Negate ts so that DESC sort works with a natural sort.
    ts = row.get("source_updated_at") or ""
    return (tier_idx, -len(ts), ts[::-1], row.get("object_type", ""), row.get("canonical_id", ""))


def _make_result(
    row: dict,
    *,
    tier_name: str,
    tier_idx: int,
    matched_on: Optional[str] = None,
    subject_candidate: Optional[SubjectCandidate] = None,
) -> SearchResult:
    r = SearchResult(
        object_type=row.get("object_type", ""),
        canonical_id=row.get("canonical_id", ""),
        title=row.get("title", ""),
        source_id=row.get("source_id", ""),
        source_key=row.get("source_key"),
        source_updated_at=row.get("source_updated_at"),
        summary=row.get("summary"),
        public_url=row.get("public_url"),
        saas_url=row.get("saas_url"),
        match_type=tier_name,
        matched_on=matched_on,
        rank_tier=tier_idx,
    )
    if subject_candidate is not None:
        r.subject_type = subject_candidate.subject_type
        r.subject_key = subject_candidate.subject_key
        r.subject_match_type = subject_candidate.match_type
        r.matched_term = subject_candidate.matched_term
    return r


def retrieve(
    plan: SearchQueryPlan,
    reader: SearchDocumentReader,
) -> SearchResponse:
    """Execute the retrieval plan against `reader`.

    Tier precedence: IDENTIFIER_EXACT → … → TRIGRAM (§22).
    Dedup: (object_type, canonical_id); highest-priority tier wins (§25).
    Sort within tier: source_updated_at DESC, object_type ASC, canonical_id ASC (§24).
    Pagination: stable offset (§26).
    Legal authority: no applicability fields produced (§29).
    CHEM public mode: visibility_scopes filter enforces PUBLIC (§27-§28).
    """
    seen: dict[tuple[str, str], SearchResult] = {}   # (object_type, canonical_id) → result
    active_tiers_hit: list[str] = []

    ot  = plan.object_types
    vis = plan.visibility_scopes

    def _try_tier(tier_name: str, rows: list[dict], **kwargs: Any) -> None:
        tier_idx = TIER_PRECEDENCE.index(tier_name)
        if not rows:
            return
        if tier_name not in active_tiers_hit:
            active_tiers_hit.append(tier_name)
        sorted_rows = sorted(rows, key=lambda r: _doc_sort_key(r, tier_idx))
        for row in sorted_rows:
            key = (row.get("object_type", ""), row.get("canonical_id", ""))
            if key not in seen:
                seen[key] = _make_result(row, tier_name=tier_name, tier_idx=tier_idx, **kwargs)

    # Tier 1 — IDENTIFIER_EXACT
    if TIER_IDENTIFIER_EXACT in plan.active_tiers:
        for ident in plan.identifier_candidates:
            _try_tier(TIER_IDENTIFIER_EXACT,
                      reader.query_identifier_exact(ident, object_types=ot, visibility=vis),
                      matched_on=ident)

    # Tier 2 — CANONICAL_EXACT
    if TIER_CANONICAL_EXACT in plan.active_tiers:
        for ident in plan.identifier_candidates:
            _try_tier(TIER_CANONICAL_EXACT,
                      reader.query_canonical_exact(ident, object_types=ot, visibility=vis),
                      matched_on=ident)

    # Tier 3 — SUBJECT (one query per dictionary candidate)
    if TIER_SUBJECT in plan.active_tiers:
        for cand in plan.subject_candidates:
            rows = reader.query_subject(cand.subject_key, object_types=ot, visibility=vis)
            _try_tier(TIER_SUBJECT, rows,
                      matched_on=cand.subject_key,
                      subject_candidate=cand)

    # Tier 4 — TITLE_EXACT
    if TIER_TITLE_EXACT in plan.active_tiers:
        _try_tier(TIER_TITLE_EXACT,
                  reader.query_title_exact(plan.normalized_query, object_types=ot, visibility=vis),
                  matched_on=plan.normalized_query)

    # Tier 5 — ALIAS_EXACT
    if TIER_ALIAS_EXACT in plan.active_tiers:
        _try_tier(TIER_ALIAS_EXACT,
                  reader.query_alias_exact(plan.normalized_query, object_types=ot, visibility=vis),
                  matched_on=plan.normalized_query)

    # Tier 6 — CONTEXT (reuse identifier candidates as context keys)
    if TIER_CONTEXT in plan.active_tiers:
        for ident in plan.identifier_candidates:
            _try_tier(TIER_CONTEXT,
                      reader.query_context(ident, object_types=ot, visibility=vis),
                      matched_on=ident)
        # Also check dictionary subject keys as context keys
        for cand in plan.subject_candidates:
            _try_tier(TIER_CONTEXT,
                      reader.query_context(cand.subject_key, object_types=ot, visibility=vis),
                      matched_on=cand.subject_key)

    # Tier 7 — FTS
    if TIER_FTS in plan.active_tiers:
        _try_tier(TIER_FTS,
                  reader.query_fts(plan.normalized_query, object_types=ot, visibility=vis),
                  matched_on=plan.normalized_query)

    # Tier 8 — TRIGRAM (last resort)
    if TIER_TRIGRAM in plan.active_tiers:
        _try_tier(TIER_TRIGRAM,
                  reader.query_trigram(plan.normalized_query, object_types=ot, visibility=vis,
                                       similarity_threshold=0.3),
                  matched_on=plan.normalized_query)

    # Global sort across all tiers: by tier_idx ASC, then within-tier keys
    all_results = sorted(
        seen.values(),
        key=lambda r: (r.rank_tier, -(len(r.source_updated_at or "")),
                       (r.source_updated_at or "")[::-1],
                       r.object_type, r.canonical_id),
    )

    total = len(all_results)

    # Pagination (§26): stable offset
    offset = (plan.page - 1) * plan.page_size
    page_results = all_results[offset: offset + plan.page_size]

    return SearchResponse(
        query=plan.raw_query,
        page=plan.page,
        page_size=plan.page_size,
        total=total,
        items=page_results,
        active_tiers=active_tiers_hit,
        status="ok" if total > 0 else "empty",
    )


class SharedRetrievalEngine:
    """Convenience wrapper that combines `build_query_plan` + `retrieve`.

    Public, SaaS, and Paid callers pass different `visibility_scopes`.
    F4 reuses this class without modification.
    """

    def __init__(self, reader: SearchDocumentReader):
        self._reader = reader

    def search(
        self,
        q: str,
        *,
        visibility_scopes: Optional[list[str]] = None,
        object_types: Optional[list[str]] = None,
        page: int = 1,
        page_size: int = 10,
    ) -> SearchResponse:
        """Run end-to-end retrieval.

        Raises ``ValueError`` on blank query (§35).
        Returns ``SearchResponse`` with status="empty" when no hits.
        Does NOT raise on zero results — that is not an error.
        """
        plan = build_query_plan(
            q,
            object_types=object_types,
            visibility_scopes=visibility_scopes or ["PUBLIC"],
            page=page,
            page_size=min(max(1, page_size), 50),
        )
        return retrieve(plan, self._reader)
