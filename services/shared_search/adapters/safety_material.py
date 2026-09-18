"""SAFETY_MATERIAL adapter — WO-TAI-SHARED-SEARCH-F2 §17."""
from __future__ import annotations

from typing import Callable, Iterable, Iterator, Optional

from services.shared_search.adapters._common import (
    as_str_list, coerce_iso, expected_hashes_from_documents,
)


Fetcher = Callable[[], Iterable[dict]]


class SafetyMaterialAdapter:
    domain_name = "SAFETY_MATERIAL"
    object_type = "SAFETY_MATERIAL"

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
            payload = _normalize_material(row)
            if payload is not None:
                yield payload

    def iter_expected_hashes(self) -> Iterator[dict]:
        yield from expected_hashes_from_documents(self.iter_documents)

    def object_reindex_payload(self, canonical_id: str) -> Optional[dict]:
        row = self._fetch_by_id(canonical_id)
        return _normalize_material(row) if row is not None else None


def _normalize_material(row: dict) -> Optional[dict]:
    mid = row.get("id")
    title = row.get("title")
    if not mid or not title:
        return None
    # Storage hold policy collapses UNAVAILABLE / oversize / review
    # into HOLD (Document Contract §6).
    storage_hold = bool(row.get("storage_hold"))
    if storage_hold:
        return {
            "object_type": SafetyMaterialAdapter.object_type,
            "canonical_id": str(mid),
            "source_id": "KOSHA_OFFICIAL_MATERIAL",
            "source_key": (str(row["source_med_seq"])
                           if row.get("source_med_seq") is not None else None),
            "title": str(title),
            "summary": None,
            "search_text": str(title),
            "aliases": [],
            "keywords": [],
            "subjects": [],
            "context": [],
            "public_url": None,
            "saas_url": None,
            "publication_status": "HOLD",
            "visibility_scopes": [],
            "source_updated_at": coerce_iso(row.get("updated_at")),
        }
    summary = row.get("summary")
    category = row.get("category")
    industry = row.get("industry_category") or row.get("industry")
    accident = row.get("accident_type")
    return {
        "object_type": SafetyMaterialAdapter.object_type,
        "canonical_id": str(mid),
        "source_id": "KOSHA_OFFICIAL_MATERIAL",
        "source_key": (str(row["source_med_seq"])
                       if row.get("source_med_seq") is not None else None),
        "title": str(title),
        "summary": str(summary) if summary else None,
        "search_text": " ".join(as_str_list([title, summary, category, industry, accident])),
        "aliases": [],
        "keywords": as_str_list([category, industry, accident]),
        "subjects": [],
        "context": [],
        "public_url": row.get("url"),
        "saas_url": f"/saas/material/{mid}",
        "publication_status": "PUBLISHED",
        "visibility_scopes": ["PUBLIC", "SAAS", "PAID"],
        "source_updated_at": coerce_iso(row.get("updated_at")
                                        or row.get("collected_at")),
    }
