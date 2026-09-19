"""Shared Search Result Contract — WO-TAI-SHARED-SEARCH-F3 §30-§31.

Defines `SearchResult` (one hit) and `SearchResponse` (paginated
page) that ALL consumers — Public, SaaS, Paid — use without
modification.  No per-consumer shaping happens here.

QA / logging: every result carries enough explanation to answer
"why was this returned?" without exposing internal SQL or scoring
coefficients.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SearchResult:
    """One retrieval hit.

    Null-tolerant: callers may leave optional fields None.
    """
    object_type:          str
    canonical_id:         str
    title:                str

    # Provenance
    source_id:            str
    source_key:           Optional[str]
    source_updated_at:    Optional[str]  # ISO-8601 string as stored

    # Presentation
    summary:              Optional[str] = None
    public_url:           Optional[str] = None
    saas_url:             Optional[str] = None

    # Retrieval explanation (§31): preserved for QA/logging.
    # Consumers decide which of these to surface to end-users.
    match_type:           str = ""        # winning tier name
    matched_on:           Optional[str] = None   # e.g. the actual term matched
    rank_tier:            int = 0         # tier precedence index (0 = highest)

    # Subject evidence when match came via SUBJECT tier
    subject_type:         Optional[str] = None
    subject_key:          Optional[str] = None
    subject_match_type:   Optional[str] = None   # EXACT / SYNONYM_OF / TOKEN …
    matched_term:         Optional[str] = None

    # Internal scoring detail (available for logging; not part of public API)
    score_detail:         dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "object_type":        self.object_type,
            "canonical_id":       self.canonical_id,
            "title":              self.title,
            "source_id":          self.source_id,
            "source_key":         self.source_key,
            "source_updated_at":  self.source_updated_at,
            "summary":            self.summary,
            "public_url":         self.public_url,
            "saas_url":           self.saas_url,
            "match_type":         self.match_type,
            "matched_on":         self.matched_on,
            "rank_tier":          self.rank_tier,
            "subject_type":       self.subject_type,
            "subject_key":        self.subject_key,
            "subject_match_type": self.subject_match_type,
            "matched_term":       self.matched_term,
        }


@dataclass
class SearchResponse:
    """Paginated retrieval response. Shape is stable across Public/SaaS/Paid."""
    query:               str
    page:                int
    page_size:           int
    total:               int
    items:               list[SearchResult] = field(default_factory=list)

    # Active tiers that produced at least one hit (for diagnostics/UI).
    active_tiers:        list[str] = field(default_factory=list)

    # Dictionary snapshot (§34): last-built / current version string,
    # or None if unavailable.
    dictionary_snapshot: Optional[str] = None

    status:              str = "ok"   # "ok" | "empty" | "error"

    def to_dict(self) -> dict:
        return {
            "query":               self.query,
            "page":                self.page,
            "page_size":           self.page_size,
            "total":               self.total,
            "items":               [r.to_dict() for r in self.items],
            "active_tiers":        self.active_tiers,
            "dictionary_snapshot": self.dictionary_snapshot,
            "status":              self.status,
        }
