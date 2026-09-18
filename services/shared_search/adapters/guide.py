"""GUIDE adapter.

WO-TAI-SHARED-SEARCH-F2 §16. Reads `public.kosha_guide` rows +
their latest COMPLETED snapshot membership. Yields one
SearchDocument per catalog row that is in the current membership.
"""
from __future__ import annotations

from typing import Callable, Iterable, Iterator, Optional

from services.shared_search.adapters._common import (
    as_str_list, coerce_iso, expected_hashes_from_documents,
)


# Fetcher = zero-arg callable returning an iterable of Domain rows.
# Tests inject in-memory lists; production wires it to
# `paginate_supabase(...)` over `public.kosha_guide` joined with the
# latest COMPLETED snapshot_items.
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
        # fetch_current -> rows that pass Domain publication gate
        # (catalog row + snapshot COMPLETED).
        self._fetch_current = fetch_current
        self._fetch_by_id = fetch_by_id or (lambda _id: None)

    def iter_documents(self) -> Iterator[dict]:
        for row in self._fetch_current():
            doc = _normalize_guide(row)
            if doc is not None:
                yield doc

    def iter_expected_hashes(self) -> Iterator[dict]:
        # Shared helper; identical across all 7 adapters.
        yield from expected_hashes_from_documents(self.iter_documents)

    def object_reindex_payload(self, canonical_id: str) -> Optional[dict]:
        row = self._fetch_by_id(canonical_id)
        if row is None:
            return None
        return _normalize_guide(row)


def _normalize_guide(row: dict) -> Optional[dict]:
    """Map a `kosha_guide`-shaped row into a SearchDocument payload."""
    guide_id = row.get("id")
    title = row.get("title") or row.get("guide_title")
    if not guide_id or not title:
        return None
    summary = row.get("description") or row.get("summary")
    category_name = row.get("category_name")
    return {
        "object_type": GuideAdapter.object_type,
        "canonical_id": str(guide_id),
        "source_id": "KOSHA_OFFICIAL_GUIDE",
        "source_key": str(guide_id),
        "title": str(title),
        "summary": str(summary) if summary else None,
        "search_text": " ".join(as_str_list([title, summary, category_name])),
        "aliases": [],
        "keywords": as_str_list([category_name]),
        "subjects": [],
        "context": [],
        "public_url": row.get("official_url") or row.get("url"),
        "saas_url": f"/saas/guide/{guide_id}",
        "publication_status": "PUBLISHED",
        "visibility_scopes": ["PUBLIC", "SAAS", "PAID"],
        "source_updated_at": coerce_iso(row.get("last_seen_at")
                                        or row.get("first_seen_at")),
    }
