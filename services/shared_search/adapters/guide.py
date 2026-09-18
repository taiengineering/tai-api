"""GUIDE adapter — WO-TAI-SHARED-SEARCH-F2 §16 + F2 CO §8-§9.

Source of truth: `public.kosha_guide_current` (verified in
supabase/migrations/20260913_kosha_guide_current_snapshot.sql).

Real columns: id, guide_no, guide_title, category_code, category_name,
guide_url, regist_date, content_hash, metadata_license,
original_rights_mode, binary_storage_allowed, snapshot_id.

Public detail route: tai-www `/safety-guide/{id}` (verified in
tai-www main src/pages/safety-guide/[id].astro).
"""
from __future__ import annotations

from typing import Callable, Iterable, Iterator, Optional

from services.shared_search.adapters._common import (
    MISSING_TIMESTAMP, as_str_list, coerce_iso,
    expected_hashes_from_documents, first_present_iso,
)


Fetcher = Callable[[], Iterable[dict]]


class GuideAdapter:
    domain_name = "GUIDE"
    object_type = "GUIDE"

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
            payload = _normalize_guide(row)
            if payload is not None:
                yield payload

    def iter_expected_hashes(self) -> Iterator[dict]:
        yield from expected_hashes_from_documents(self.iter_documents)

    def object_reindex_payload(self, canonical_id: str) -> Optional[dict]:
        row = self._fetch_by_id(canonical_id)
        return _normalize_guide(row) if row is not None else None


def _normalize_guide(row: dict) -> Optional[dict]:
    """Map `kosha_guide_current` → SearchDocument payload."""
    guide_id = row.get("id")
    title = row.get("guide_title")
    if not guide_id or not title:
        return None
    ts = first_present_iso(row.get("regist_date"),
                           row.get("_snapshot_completed_at"))
    if ts is MISSING_TIMESTAMP:
        return None
    guide_no = row.get("guide_no")
    category_name = row.get("category_name")
    category_code = row.get("category_code")
    return {
        "object_type": GuideAdapter.object_type,
        "canonical_id": str(guide_id),
        "source_id": "KOSHA_OFFICIAL_GUIDE",
        "source_key": str(guide_no) if guide_no else str(guide_id),
        "title": str(title),
        "summary": None,
        "search_text": " ".join(as_str_list([title, guide_no, category_name])),
        "aliases": as_str_list([guide_no]),
        "keywords": as_str_list([category_name, category_code]),
        "subjects": [],
        "context": [],
        # Public detail route in tai-www — verified.
        "public_url": f"/safety-guide/{guide_id}",
        "saas_url": None,   # no verified SaaS route today
        "publication_status": "PUBLISHED",
        "visibility_scopes": ["PUBLIC", "SAAS", "PAID"],
        "source_updated_at": ts,
    }
