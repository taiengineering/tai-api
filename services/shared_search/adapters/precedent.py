"""PRECEDENT adapter — WO-TAI-SHARED-SEARCH-F2 §22 + F2 CO §25-§26.

Source of truth: `public.industrial_accident_precedents`
(verified via scripts/collect_precedents.py + routers/precedent_api.py).

Real columns include: id, case_number, case_name, court_name,
decision_date, sector, hazard_type, summary, source_url, prec_seq,
source, is_active, collected_at.

Public detail route: tai-www `src/pages/precedent/[id].astro` reads
`industrial_accident_precedents` directly — same SoT as this adapter.
Route key: `id` (exact match with adapter canonical_id).
Coverage: 849/849 is_active=True records have full_text (verified 2026-09-21).
"""
from __future__ import annotations

from typing import Callable, Iterable, Iterator, Optional

from services.shared_search.adapters._common import (
    MISSING_TIMESTAMP, as_str_list, coerce_iso,
    expected_hashes_from_documents, first_present_iso,
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
    title = (row.get("case_name") or row.get("title")
             or row.get("case_number"))
    summary = row.get("summary")
    if not title:
        return None
    ts = first_present_iso(
        row.get("collected_at"),
        row.get("decision_date"),
    )
    if ts is MISSING_TIMESTAMP:
        return None
    prec_seq = row.get("prec_seq")
    court = row.get("court_name")
    sector = row.get("sector")
    hazard = row.get("hazard_type")
    case_number = row.get("case_number")
    return {
        "object_type": PrecedentAdapter.object_type,
        "canonical_id": str(pid),
        "source_id": (str(row.get("source")) if row.get("source") else "law_go_kr"),
        "source_key": (str(prec_seq) if prec_seq else None),
        "title": str(title),
        "summary": str(summary) if summary else None,
        "search_text": " ".join(as_str_list([
            title, summary, court, sector, hazard, case_number,
        ])),
        "aliases": as_str_list([case_number]),
        "keywords": as_str_list([sector, hazard]),
        "subjects": [],
        "context": ([{"context_type": "sector", "context_key": sector}]
                    if sector else []),
        # Public detail route: tai-www /precedent/{pid} — verified 2026-09-21.
        "public_url": f"/precedent/{pid}",
        "saas_url": None,
        "publication_status": "PUBLISHED",
        "visibility_scopes": ["PUBLIC", "SAAS", "PAID"],
        "source_updated_at": ts,
    }
