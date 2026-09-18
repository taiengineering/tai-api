"""PRECEDENT adapter — WO-TAI-SHARED-SEARCH-F2 §22."""
from __future__ import annotations

from typing import Callable, Iterable, Iterator, Optional

from services.shared_search.adapters._common import (
    as_str_list, coerce_iso, expected_hashes_from_documents,
)


Fetcher = Callable[[], Iterable[dict]]


class PrecedentAdapter:
    domain_name = "PRECEDENT"
    object_type = "PRECEDENT"

    def __init__(
        self,
        *,
        fetch_current: Fetcher,
        fetch_by_id: Optional[Callable[[str], Optional[dict]]] = None,
    ):
        # fetch_current yields industrial_accident_precedents rows with
        # is_active=true. Legacy `posts` merge is deliberately NOT
        # attempted here (F2 WO §22 forbids identity merging).
        self._fetch_current = fetch_current
        self._fetch_by_id = fetch_by_id or (lambda _id: None)

    def iter_documents(self) -> Iterator[dict]:
        for row in self._fetch_current():
            payload = _normalize_precedent(row)
            if payload is not None:
                yield payload

    def iter_expected_hashes(self) -> Iterator[dict]:
        yield from expected_hashes_from_documents(self.iter_documents)

    def object_reindex_payload(self, canonical_id: str) -> Optional[dict]:
        row = self._fetch_by_id(canonical_id)
        return _normalize_precedent(row) if row is not None else None


def _normalize_precedent(row: dict) -> Optional[dict]:
    pid = row.get("id")
    if not pid or not row.get("is_active", False):
        return None
    title = row.get("case_name") or row.get("title") or row.get("case_number")
    summary = row.get("summary")
    if not title:
        return None
    prec_seq = row.get("prec_seq")
    court = row.get("court_name")
    sector = row.get("sector")
    hazard = row.get("hazard_type")
    return {
        "object_type": PrecedentAdapter.object_type,
        "canonical_id": str(pid),
        "source_id": "law_go_kr",
        "source_key": (str(prec_seq) if prec_seq else None),
        "title": str(title),
        "summary": str(summary) if summary else None,
        "search_text": " ".join(as_str_list([title, summary, court, sector, hazard])),
        "aliases": [],
        "keywords": as_str_list([sector, hazard]),
        "subjects": [],
        "context": ([{"context_type": "sector", "context_key": sector}]
                    if sector else []),
        # Detail resolver DEFERRED_TO_DOMAIN_ADAPTER — the legacy
        # /precedents/{id} posts route is NOT the IAP resolver.
        "public_url": None,
        "saas_url": None,
        "publication_status": "PUBLISHED",
        "visibility_scopes": ["PUBLIC", "SAAS", "PAID"],
        "source_updated_at": coerce_iso(row.get("collected_at")
                                        or row.get("decision_date")),
    }
