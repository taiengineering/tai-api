"""LEGAL adapter — WO-TAI-SHARED-SEARCH-F2 §23.

**Safety boundary**: LEGAL SearchResult is discovery only. Legal
Engine remains the sole applicability authority. This adapter
never writes / reads applicability decisions.

LEGAL SoT has multiple record kinds:

    obligation_atom  — deterministic canonical unit (SEARCH-F2 supported)
    law_article       — deterministic subject id (SEARCH-F2 supported)
    norm_cluster      — needs additional evidence (BLOCKED subtype)

The adapter yields only the kinds whose canonical identity is
deterministically provable today; the rest raise
`AdapterBlockedSubtype` so the Indexer records the block without
failing the whole F2 run.
"""
from __future__ import annotations

from typing import Callable, Iterable, Iterator, Optional

from services.shared_search.adapters._common import (
    as_str_list, coerce_iso, expected_hashes_from_documents,
)
from services.shared_search.adapters.base import AdapterBlockedSubtype


Fetcher = Callable[[], Iterable[dict]]


SUPPORTED_SUBTYPES = frozenset({"obligation_atom", "law_article"})
BLOCKED_SUBTYPES = frozenset({"norm_cluster"})


class LegalAdapter:
    domain_name = "LEGAL"
    object_type = "LEGAL"

    def __init__(
        self,
        *,
        fetch_current: Fetcher,
        fetch_by_id: Optional[Callable[[str], Optional[dict]]] = None,
    ):
        # fetch_current yields LEG-published rows tagged with a
        # `record_kind` field (obligation_atom / law_article / norm_cluster).
        # SoT-side selection of "which rows count as PUBLISHED"
        # remains the Domain's authority.
        self._fetch_current = fetch_current
        self._fetch_by_id = fetch_by_id or (lambda _id: None)
        self._blocked_seen: set[str] = set()

    def iter_documents(self) -> Iterator[dict]:
        # Iterate once; raise AdapterBlockedSubtype AFTER we've yielded
        # every supported doc so the caller records the block but keeps
        # the run's partial-success semantics intact.
        for row in self._fetch_current():
            kind = (row.get("record_kind") or "").strip()
            if kind in BLOCKED_SUBTYPES:
                self._blocked_seen.add(kind)
                continue
            if kind not in SUPPORTED_SUBTYPES:
                # Unknown subtype = safe skip; write it up as a block.
                self._blocked_seen.add(kind or "UNKNOWN")
                continue
            payload = _normalize_legal(row)
            if payload is not None:
                yield payload
        if self._blocked_seen:
            raise AdapterBlockedSubtype(
                f"LEGAL subtypes blocked: {sorted(self._blocked_seen)}"
            )

    def iter_expected_hashes(self) -> Iterator[dict]:
        yield from expected_hashes_from_documents(self.iter_documents)

    def object_reindex_payload(self, canonical_id: str) -> Optional[dict]:
        row = self._fetch_by_id(canonical_id)
        if row is None:
            return None
        kind = (row.get("record_kind") or "").strip()
        if kind not in SUPPORTED_SUBTYPES:
            return None
        return _normalize_legal(row)


def _normalize_legal(row: dict) -> Optional[dict]:
    kind = (row.get("record_kind") or "").strip()
    if kind == "obligation_atom":
        canonical_id = row.get("obligation_atom_id")
    elif kind == "law_article":
        canonical_id = row.get("article_id")
    else:
        return None
    if not canonical_id:
        return None
    title = row.get("title")
    if not title:
        return None
    summary = row.get("summary")
    body = row.get("body") or ""
    subjects: list[dict] = []
    subject_key = row.get("subject_key")
    if subject_key:
        subjects.append({
            "subject_type": "LEGAL_TERM",
            "subject_key": str(subject_key),
        })
    context: list[dict] = []
    if kind == "obligation_atom":
        context.append({
            "context_type": "legal_obligation",
            "context_key": str(canonical_id),
        })
    return {
        "object_type": LegalAdapter.object_type,
        "canonical_id": str(canonical_id),
        "source_id": row.get("source_id") or "LEG_OFFICIAL",
        "source_key": (str(row["source_key"])
                       if row.get("source_key") is not None else None),
        "title": str(title),
        "summary": str(summary) if summary else None,
        "search_text": " ".join(as_str_list([title, summary, body])),
        "aliases": [],
        "keywords": [],
        "subjects": subjects,
        "context": context,
        "public_url": row.get("public_url"),
        "saas_url": row.get("saas_url"),
        "publication_status": "PUBLISHED",
        "visibility_scopes": ["PUBLIC", "SAAS", "PAID"],
        "source_updated_at": coerce_iso(row.get("published_at")
                                        or row.get("updated_at")),
    }
