"""OBJ-CHEM-09 CHEM search adapter (thin composition over existing assets).

Reuses:
    tools/search_dict/normalize.py    - deterministic normalization
                                        (same functions the shared dictionary
                                        uses for term_normalized / term_compact)
    services/safe_help_kiwi.py        - Kiwi tokenizer with kiwipiepy-optional
                                        graceful fallback
    services/search_query_svc.lookup  - OPTIONAL terminology-dictionary
                                        expansion (synonyms/aliases). Failure
                                        is silent - the adapter still functions
                                        without it.

This module does NOT own Kiwi and does NOT own the terminology dictionary.
It is a domain adapter that turns a raw user query into a deterministic set
of candidate terms, then routes them into CHEM-06's read service.

Hard boundaries (WO §2):
- Search enrichment MUST NOT mutate canonical identity, CAS, or any DB row.
- No LLM. No new search engine. No new migration.
- Identifiers (chem_id / CAS / KE / EN / UN) are detected FIRST and bypass
  Kiwi entirely (§8). Identifier tokens are never morphologically split.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Optional

from services import safe_help_kiwi
from tools.search_dict import normalize as N

# ---------------------------------------------------------------------------
# Identifier patterns (WO §8)
# ---------------------------------------------------------------------------

IDENTIFIER_CHEM_ID = "chem_id"
IDENTIFIER_CAS = "cas_no"
IDENTIFIER_KE = "ke_no"
IDENTIFIER_EN = "en_no"
IDENTIFIER_UN = "un_no"

# 6-digit KOSHA chemId (leading zeros preserved). Matches "001008".
_CHEM_ID_RE = re.compile(r"^\d{6}$")
# CAS: N-N-N with 2..7 digits / 2 digits / 1 digit. Matches "71-43-2".
_CAS_RE = re.compile(r"^\d{2,7}-\d{2}-\d$")
# KE-N... / EN-N... / UN[- optional]NNNN
_KE_RE = re.compile(r"^KE-?\d{3,7}$", re.IGNORECASE)
_EN_RE = re.compile(r"^EN-?\d{3,7}$", re.IGNORECASE)
_UN_RE = re.compile(r"^UN-?\d{4}$", re.IGNORECASE)


def _detect_identifier(q_normalized: str) -> tuple[Optional[str], Optional[str]]:
    """Return (kind, value) if q looks like a stable identifier, else (None, None).

    Detection is exact-match over the normalized query — identifiers must
    stand alone. A query containing free text alongside an identifier is
    treated as free text (Kiwi path).
    """
    if _CHEM_ID_RE.match(q_normalized):
        return IDENTIFIER_CHEM_ID, q_normalized
    if _CAS_RE.match(q_normalized):
        return IDENTIFIER_CAS, q_normalized
    if _KE_RE.match(q_normalized):
        return IDENTIFIER_KE, q_normalized.upper()
    if _EN_RE.match(q_normalized):
        return IDENTIFIER_EN, q_normalized.upper()
    if _UN_RE.match(q_normalized):
        return IDENTIFIER_UN, q_normalized.upper()
    return None, None


# ---------------------------------------------------------------------------
# Search plan
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SearchPlan:
    original_query: str
    normalized_query: str
    compact_query: str
    identifier_kind: Optional[str]     # one of IDENTIFIER_* or None
    identifier_value: Optional[str]
    tokens: tuple                      # Kiwi morphology tokens (lowercased)
    expanded_terms: tuple              # dictionary-derived synonyms/aliases
    is_empty: bool

    def to_dict(self) -> dict:
        return {
            "original_query": self.original_query,
            "normalized_query": self.normalized_query,
            "compact_query": self.compact_query,
            "identifier_kind": self.identifier_kind,
            "identifier_value": self.identifier_value,
            "tokens": list(self.tokens),
            "expanded_terms": list(self.expanded_terms),
            "is_empty": self.is_empty,
        }


def _dictionary_expand(
    q: str,
    *,
    dictionary_lookup: Optional[Callable[..., dict]] = None,
    limit: int = 5,
) -> list[str]:
    """Optional term expansion via the shared TAI dictionary.

    Callers may inject a custom `dictionary_lookup(q, limit=...)` for tests;
    production defaults to services.search_query_svc.lookup. Any failure
    (missing runtime projection, network hiccup, unavailable Kiwi user
    dict) returns [] silently — the adapter still functions with just the
    Kiwi tokens.
    """
    if dictionary_lookup is None:
        try:
            from services.search_query_svc import lookup as _lookup
            dictionary_lookup = _lookup
        except Exception:
            return []
    try:
        result = dictionary_lookup(q, limit=limit)
    except Exception:
        return []
    items = (result or {}).get("items") or []
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        for key in ("subject_key", "matched_term", "display_name"):
            term = item.get(key)
            if not isinstance(term, str):
                continue
            term = term.strip()
            if not term or term == q or term in seen:
                continue
            seen.add(term)
            out.append(term)
    return out


def build_search_plan(
    q: str,
    *,
    dictionary_lookup: Optional[Callable[..., dict]] = None,
) -> SearchPlan:
    """Deterministic normalization + identifier detection + optional expansion.

    Never touches the DB. Never calls an LLM.
    """
    q = (q or "").strip()
    if not q:
        return SearchPlan(
            original_query="", normalized_query="", compact_query="",
            identifier_kind=None, identifier_value=None,
            tokens=(), expanded_terms=(), is_empty=True,
        )

    normalized = N.normalize_basic(q)
    compact_q = N.compact(q)

    ident_kind, ident_value = _detect_identifier(normalized)
    if ident_kind is not None:
        # WO §8: identifiers are NEVER morphologically tokenized.
        return SearchPlan(
            original_query=q,
            normalized_query=normalized,
            compact_query=compact_q,
            identifier_kind=ident_kind,
            identifier_value=ident_value,
            tokens=(),
            expanded_terms=(),
            is_empty=False,
        )

    # Free-text path. Kiwi tokens + dictionary expansion.
    kiwi_tokens = tuple(safe_help_kiwi.tokens(normalized))
    expanded = tuple(_dictionary_expand(
        normalized, dictionary_lookup=dictionary_lookup,
    ))
    return SearchPlan(
        original_query=q,
        normalized_query=normalized,
        compact_query=compact_q,
        identifier_kind=None,
        identifier_value=None,
        tokens=kiwi_tokens,
        expanded_terms=expanded,
        is_empty=False,
    )


# ---------------------------------------------------------------------------
# Search dispatch
# ---------------------------------------------------------------------------


MATCH_IDENTIFIER_EXACT = "IDENTIFIER_EXACT"
MATCH_NORMALIZED_EXACT = "NORMALIZED_EXACT"
MATCH_DICTIONARY = "DICTIONARY_EXPANSION"
MATCH_KIWI_TOKEN = "KIWI_TOKEN"


def _clamp_pagination(limit: int, offset: int) -> tuple[int, int]:
    # Delegate to CHEM-06 read defaults / cap.
    from services.kosha_msds.read import DEFAULT_LIMIT, MAX_LIMIT
    lim = int(limit) if limit is not None else DEFAULT_LIMIT
    off = int(offset) if offset is not None else 0
    if lim <= 0:
        lim = DEFAULT_LIMIT
    if lim > MAX_LIMIT:
        lim = MAX_LIMIT
    if off < 0:
        off = 0
    return lim, off


def search_by_q(
    *,
    q: str,
    store,
    limit: int = 20,
    offset: int = 0,
    dictionary_lookup: Optional[Callable[..., dict]] = None,
    scope: Optional[str] = None,
) -> dict:
    """Free-text search entrypoint. Delegates to CHEM-06 read.search.

    Returns the CHEM-06 envelope with an additional `match_metadata` field
    that carries the plan's derived tokens and expansions (WO §17). Each
    item is annotated with `match_type` and `matched_term`.

    Preserves CHEM-06's canonical identity and provenance shape verbatim.
    No DB mutation. `scope` selects the publication view (default FULL);
    results are always constrained to the scoped membership so preview
    mode never leaks non-preview chemicals (WO-CHEM-SEO-PREVIEW-LIVE-001 §7).
    """
    from services.kosha_msds import read

    lim, off = _clamp_pagination(limit, offset)
    plan = build_search_plan(q, dictionary_lookup=dictionary_lookup)
    match_meta = {
        "normalized_query": plan.normalized_query,
        "compact_query": plan.compact_query,
        "identifier_kind": plan.identifier_kind,
        "tokens": list(plan.tokens),
        "expanded_terms": list(plan.expanded_terms),
    }

    if plan.is_empty:
        result = read.list_current(store=store, limit=lim, offset=off, scope=scope)
        result["match_metadata"] = match_meta
        return result

    if plan.identifier_kind is not None:
        # Identifier: exact-match filter via CHEM-06 search.
        kwargs = {plan.identifier_kind: plan.identifier_value}
        result = read.search(store=store, limit=lim, offset=off, scope=scope, **kwargs)
        for item in result["items"]:
            item["match_type"] = MATCH_IDENTIFIER_EXACT
            item["matched_term"] = plan.identifier_value
        result["match_metadata"] = match_meta
        return result

    # Free-text: OR multiple candidates via multiple CHEM-06 search calls,
    # then de-dupe by chem_id preserving priority order.
    seen: set[str] = set()
    hits: list[dict] = []

    def _run(term: str, match_type: str) -> None:
        if not term:
            return
        # Deterministic candidate matching: exact/partial name against
        # both KO and EN fields. Read service returns identity envelope
        # + provenance; no canonical mutation happens on the DB side.
        for kw in ("name_ko", "name_en"):
            envelope = read.search(
                store=store,
                limit=lim,
                offset=0,
                scope=scope,
                **{kw: term},
            )
            for row in envelope.get("items") or []:
                cid = row.get("chem_id")
                if cid in seen:
                    continue
                seen.add(cid)
                out = dict(row)
                out["match_type"] = match_type
                out["matched_term"] = term
                hits.append(out)

    # Priority: normalized-query exact > dictionary expansion > Kiwi tokens.
    _run(plan.normalized_query, MATCH_NORMALIZED_EXACT)
    for t in plan.expanded_terms:
        _run(t, MATCH_DICTIONARY)
    for t in plan.tokens:
        _run(t, MATCH_KIWI_TOKEN)

    total = len(hits)
    page = hits[off : off + lim]
    return {
        "items": page,
        "total": total,
        "limit": lim,
        "offset": off,
        "match_metadata": match_meta,
    }
