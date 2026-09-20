"""OpenSearchSearchReader — WO-TAI-SHARED-SEARCH-F3 §19-§29.

Production READ-only backend for SharedRetrievalEngine.
Replaces SupabaseSearchReader completely.

10-tier retrieval using OpenSearch `_msearch` (§22):
  T0  SOURCE_KEY_EXACT   — keyword exact on source_key
  T1  CANONICAL_ID_EXACT — keyword exact on canonical_id
  T2  DICTIONARY_EXACT   — nested subject_key exact (EXACT match type)
  T3  DICTIONARY_EXPANSION — nested subject_key exact (EXPANSION match type)
  T4  TITLE_EXACT        — title.raw keyword exact
  T5  ALIAS_EXACT        — aliases.raw keyword exact
  T6  SUBJECT_EXACT      — nested subject_key term
  T7  CONTEXT_EXACT      — nested context_key term
  T8  BM25_NORI          — multi-field BM25 with Nori
  T9  FUZZY_FALLBACK     — fuzzy on title (only when upper tiers empty)

All tiers apply a common visibility filter (§27):
  publication_status = PUBLISHED
  AND scope ∈ visibility_scopes

No legal applicability fields produced (§29).
CHEM public mode is controlled by the adapter layer (§28).
"""
from __future__ import annotations

import copy
import json
import logging
from typing import Any, Optional

from opensearchpy import OpenSearch

from services.shared_search.opensearch_client import CURRENT_ALIAS, get_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TIER_FETCH_SIZE = 200          # max docs fetched per tier per _msearch call
FUZZY_TRIGGER_THRESHOLD = 0    # trigger FUZZY only when all other tiers total ≤ this


# ---------------------------------------------------------------------------
# Visibility filter (§27) — applied to every tier
# ---------------------------------------------------------------------------

def _visibility_filter(visibility: list[str]) -> list[dict]:
    """Build OpenSearch filter clauses for publication + scope."""
    filters: list[dict] = [
        {"term": {"publication_status": "PUBLISHED"}}
    ]
    for scope in visibility:
        filters.append({"term": {"visibility_scopes": scope}})
    return filters


def _type_filter(object_types: list[str]) -> list[dict]:
    if not object_types:
        return []
    return [{"terms": {"object_type": object_types}}]


def _base_filter(visibility: list[str], object_types: list[str]) -> list[dict]:
    return _visibility_filter(visibility) + _type_filter(object_types)


def _within_filter(within_query: str) -> list[dict]:
    """Filter-context clauses for within search: each token must appear
    in at least one of the text fields (AND across tokens, zero score contribution).
    """
    tokens = [t for t in within_query.strip().split() if t]
    if not tokens:
        return []
    _fields = ["title", "aliases", "keywords", "summary", "search_text"]
    clauses = []
    for token in tokens:
        clauses.append({
            "bool": {
                "should": [
                    {"match": {f: {"query": token, "analyzer": "tai_nori_search"}}}
                    for f in _fields
                ],
                "minimum_should_match": 1,
            }
        })
    return clauses


def _inject_within(query_body: dict, within_query: Optional[str]) -> dict:
    """Inject within filter clauses into an existing bool query. No score contribution."""
    if not within_query or not within_query.strip():
        return query_body
    clauses = _within_filter(within_query)
    if not clauses:
        return query_body
    q = copy.deepcopy(query_body)
    bool_q = q.get("query", {}).get("bool", {})
    bool_q["filter"] = bool_q.get("filter", []) + clauses
    q["query"]["bool"] = bool_q
    return q


# ---------------------------------------------------------------------------
# Per-tier query builders
# ---------------------------------------------------------------------------

def _q_source_key_exact(q: str, vis: list[str], ot: list[str]) -> dict:
    return {
        "query": {
            "bool": {
                "must": [{"term": {"source_key": q}}],
                "filter": _base_filter(vis, ot),
            }
        },
        "size": TIER_FETCH_SIZE,
    }


def _q_canonical_id_exact(q: str, vis: list[str], ot: list[str]) -> dict:
    return {
        "query": {
            "bool": {
                "must": [{"term": {"canonical_id": q}}],
                "filter": _base_filter(vis, ot),
            }
        },
        "size": TIER_FETCH_SIZE,
    }


def _q_title_exact(q: str, vis: list[str], ot: list[str]) -> dict:
    return {
        "query": {
            "bool": {
                "must": [{"term": {"title.raw": q}}],
                "filter": _base_filter(vis, ot),
            }
        },
        "size": TIER_FETCH_SIZE,
    }


def _q_alias_exact(q: str, vis: list[str], ot: list[str]) -> dict:
    return {
        "query": {
            "bool": {
                "must": [{"term": {"aliases.raw": q}}],
                "filter": _base_filter(vis, ot),
            }
        },
        "size": TIER_FETCH_SIZE,
    }


def _q_subject_exact(subject_key: str, vis: list[str], ot: list[str]) -> dict:
    """SUBJECT_EXACT: nested query on subjects.subject_key."""
    return {
        "query": {
            "bool": {
                "must": [
                    {
                        "nested": {
                            "path": "subjects",
                            "query": {
                                "term": {"subjects.subject_key": subject_key}
                            },
                        }
                    }
                ],
                "filter": _base_filter(vis, ot),
            }
        },
        "size": TIER_FETCH_SIZE,
    }


def _q_context_exact(context_key: str, vis: list[str], ot: list[str]) -> dict:
    """CONTEXT_EXACT: nested query on context.context_key."""
    return {
        "query": {
            "bool": {
                "must": [
                    {
                        "nested": {
                            "path": "context",
                            "query": {
                                "term": {"context.context_key": context_key}
                            },
                        }
                    }
                ],
                "filter": _base_filter(vis, ot),
            }
        },
        "size": TIER_FETCH_SIZE,
    }


def _q_bm25(q: str, vis: list[str], ot: list[str]) -> dict:
    """BM25_NORI: multi-field BM25 with Nori (§24 field boosts)."""
    return {
        "query": {
            "bool": {
                "must": [
                    {
                        "multi_match": {
                            "query": q,
                            "fields": [
                                "title^5",
                                "aliases^4",
                                "keywords^3",
                                "summary^2",
                                "search_text^1",
                            ],
                            "type": "best_fields",
                            "analyzer": "tai_nori_search",
                        }
                    }
                ],
                "filter": _base_filter(vis, ot),
            }
        },
        "size": TIER_FETCH_SIZE,
    }


def _q_fuzzy(q: str, vis: list[str], ot: list[str]) -> dict:
    """FUZZY_FALLBACK: fuzzy on title only (§25)."""
    return {
        "query": {
            "bool": {
                "must": [
                    {
                        "fuzzy": {
                            "title": {
                                "value": q,
                                "fuzziness": "AUTO",
                                "prefix_length": 1,
                            }
                        }
                    }
                ],
                "filter": _base_filter(vis, ot),
            }
        },
        "size": TIER_FETCH_SIZE,
    }


# ---------------------------------------------------------------------------
# OpenSearchSearchReader
# ---------------------------------------------------------------------------

class OpenSearchSearchReader:
    """READ-only OpenSearch backend for SharedRetrievalEngine.

    Uses `_msearch` to send all non-fuzzy tier queries in ONE HTTP
    round-trip (§22), then optionally fires FUZZY if needed (§25).
    """

    def __init__(self, client: Optional[OpenSearch] = None, index: str = CURRENT_ALIAS):
        self._client = client or get_client()
        self._index  = index

    def run_msearch(
        self,
        *,
        normalized_query: str,
        identifier_candidates: list[str],
        subject_candidates: list[Any],    # SubjectCandidate objects
        object_types: list[str],
        visibility: list[str],
        within_query: Optional[str] = None,
    ) -> dict[str, list[dict]]:
        """Fire one _msearch with all eager tiers.

        ``within_query`` is injected as a filter-context clause on every tier.
        It narrows the result set but does not contribute to scores.

        Returns dict mapping tier_name → list of raw OS hit docs.
        """
        ot = object_types
        vis = visibility
        q   = normalized_query

        # Build the flat _msearch body:
        # [header, query, header, query, ...]
        requests: list[tuple[str, dict]] = []  # (tier_name, query_body)

        # T0: source_key exact (per identifier candidate)
        for ident in identifier_candidates:
            requests.append(("SOURCE_KEY_EXACT", _q_source_key_exact(ident, vis, ot)))

        # T1: canonical_id exact (per identifier candidate)
        for ident in identifier_candidates:
            requests.append(("CANONICAL_ID_EXACT", _q_canonical_id_exact(ident, vis, ot)))

        # T2: DICTIONARY_EXACT subjects (subject_candidates with EXACT match types)
        # T3: DICTIONARY_EXPANSION subjects (non-EXACT expansion match types)
        _dict_exact_types = {
            "EXACT", "NORMALIZED_EXACT", "PUNCTUATION",
            "EXACT_ALIAS",
        }
        for cand in subject_candidates:
            tier = ("DICTIONARY_EXACT"
                    if cand.match_type in _dict_exact_types
                    else "DICTIONARY_EXPANSION")
            requests.append((tier, _q_subject_exact(cand.subject_key, vis, ot)))

        # T4: title exact
        requests.append(("TITLE_EXACT", _q_title_exact(q, vis, ot)))

        # T5: alias exact
        requests.append(("ALIAS_EXACT", _q_alias_exact(q, vis, ot)))

        # T6: subject exact (raw query as subject_key)
        if q and " " not in q.strip():
            requests.append(("SUBJECT_EXACT", _q_subject_exact(q.strip(), vis, ot)))

        # T7: context exact
        if q and " " not in q.strip():
            requests.append(("CONTEXT_EXACT", _q_context_exact(q.strip(), vis, ot)))

        # T8: BM25 Nori
        requests.append(("BM25_NORI", _q_bm25(q, vis, ot)))

        if not requests:
            return {}

        # Inject within filter into every tier (filter context = zero score contribution)
        if within_query and within_query.strip():
            requests = [
                (tier, _inject_within(qbody, within_query))
                for tier, qbody in requests
            ]

        # Flatten to _msearch body (alternating header + body lines)
        msearch_body: list[dict] = []
        for _tier, qbody in requests:
            msearch_body.append({"index": self._index})
            msearch_body.append(qbody)

        resp = self._client.msearch(body=msearch_body)
        responses = resp.get("responses", [])

        # Map results back to tier names
        result: dict[str, list[dict]] = {}
        for i, (tier_name, _) in enumerate(requests):
            if i >= len(responses):
                break
            r = responses[i]
            if r.get("error"):
                logger.warning("msearch tier %s error: %s", tier_name, r["error"])
                continue
            hits = r.get("hits", {}).get("hits", [])
            docs = [_hit_to_doc(h) for h in hits]
            if docs:
                if tier_name not in result:
                    result[tier_name] = docs
                else:
                    result[tier_name].extend(docs)

        return result

    def run_fuzzy(
        self,
        normalized_query: str,
        *,
        object_types: list[str],
        visibility: list[str],
        within_query: Optional[str] = None,
    ) -> list[dict]:
        """FUZZY_FALLBACK — separate round-trip (§25, only when needed)."""
        qbody = _q_fuzzy(normalized_query, visibility, object_types)
        if within_query and within_query.strip():
            qbody = _inject_within(qbody, within_query)
        resp = self._client.search(index=self._index, body=qbody)
        return [_hit_to_doc(h) for h in resp.get("hits", {}).get("hits", [])]


# ---------------------------------------------------------------------------
# Hit → doc dict
# ---------------------------------------------------------------------------

def _hit_to_doc(hit: dict) -> dict:
    """Flatten an OpenSearch hit to the same dict shape as search_documents."""
    source = hit.get("_source", {})
    doc = dict(source)
    doc["_opensearch_score"] = hit.get("_score")
    return doc
