"""KNOWLEDGE (help center) adapter — WO-TAI-SHARED-SEARCH-F2 §21."""
from __future__ import annotations

from typing import Callable, Iterable, Iterator, Optional

from services.shared_search.adapters._common import (
    as_str_list, coerce_iso, expected_hashes_from_documents,
)


Fetcher = Callable[[], Iterable[dict]]


class KnowledgeAdapter:
    domain_name = "KNOWLEDGE"
    object_type = "KNOWLEDGE"

    def __init__(
        self,
        *,
        fetch_current: Fetcher,
        fetch_by_id: Optional[Callable[[str], Optional[dict]]] = None,
    ):
        # fetch_current yields safe_help_content rows with status='PUBLISHED'.
        # /help/search operational endpoint stays intact — this
        # adapter only mirrors content into the Shared Projection.
        self._fetch_current = fetch_current
        self._fetch_by_id = fetch_by_id or (lambda _id: None)

    def iter_documents(self) -> Iterator[dict]:
        for row in self._fetch_current():
            payload = _normalize_help(row)
            if payload is not None:
                yield payload

    def iter_expected_hashes(self) -> Iterator[dict]:
        yield from expected_hashes_from_documents(self.iter_documents)

    def object_reindex_payload(self, canonical_id: str) -> Optional[dict]:
        row = self._fetch_by_id(canonical_id)
        return _normalize_help(row) if row is not None else None


def _normalize_help(row: dict) -> Optional[dict]:
    doc_id = row.get("doc_id")
    title = row.get("title")
    if not doc_id or not title:
        return None
    status = row.get("status")
    if status != "PUBLISHED":
        return None
    slug = row.get("slug") or str(doc_id)
    body = row.get("body_text") or row.get("body_stripped") or ""
    menu_group = row.get("menu_group")
    return {
        "object_type": KnowledgeAdapter.object_type,
        "canonical_id": str(doc_id),
        "source_id": "TAI_HELP_CENTER",
        "source_key": str(doc_id),
        "title": str(title),
        "summary": (body[:200] if body else None),
        "search_text": " ".join(as_str_list([title, body])),
        "aliases": [],
        "keywords": as_str_list([menu_group]),
        "subjects": [],
        "context": [],
        "public_url": f"/help/{slug}",
        "saas_url": f"/saas/help/{slug}",
        "publication_status": "PUBLISHED",
        "visibility_scopes": ["PUBLIC", "SAAS", "PAID"],
        "source_updated_at": coerce_iso(row.get("updated_at")),
    }
