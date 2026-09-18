"""CSI_ACCIDENT adapter — WO-TAI-SHARED-SEARCH-F2 §18.

Uses the SEARCH-02 canonical contract verbatim:
    canonical_id = csi_accident_cases.content_id  ('CSI:<uuid>')
    source_id    = 'CSI'
    source_key   = NULL  (CSI file has no source-native id)
Publication gate = latest COMPLETED snapshot_items.identity_status = READY.
"""
from __future__ import annotations

from typing import Callable, Iterable, Iterator, Optional

from services.shared_search.adapters._common import (
    as_str_list, coerce_iso, expected_hashes_from_documents,
)


Fetcher = Callable[[], Iterable[dict]]


class CsiAccidentAdapter:
    domain_name = "CSI_ACCIDENT"
    object_type = "CSI_ACCIDENT"

    def __init__(
        self,
        *,
        fetch_current: Fetcher,
        fetch_by_content_id: Optional[Callable[[str], Optional[dict]]] = None,
    ):
        # fetch_current yields the join of csi_accident_cases with the
        # latest COMPLETED csi_accident_snapshot_items — the Domain gate.
        self._fetch_current = fetch_current
        self._fetch_by_content_id = fetch_by_content_id or (lambda _id: None)

    def iter_documents(self) -> Iterator[dict]:
        for row in self._fetch_current():
            payload = _normalize_csi(row)
            if payload is not None:
                yield payload

    def iter_expected_hashes(self) -> Iterator[dict]:
        yield from expected_hashes_from_documents(self.iter_documents)

    def object_reindex_payload(self, canonical_id: str) -> Optional[dict]:
        row = self._fetch_by_content_id(canonical_id)
        return _normalize_csi(row) if row is not None else None


def _normalize_csi(row: dict) -> Optional[dict]:
    content_id = row.get("content_id")
    if not content_id or not str(content_id).startswith("CSI:"):
        return None
    # Membership gate: READY under the current snapshot_items.
    # Adapter callers already join to snapshot_items and set this
    # field on the yielded row.
    identity_status = row.get("identity_status")
    if identity_status != "READY":
        return None
    title = row.get("title") or row.get("case_title")
    summary = row.get("summary") or row.get("accident_summary")
    if not title:
        return None
    uuid_part = str(content_id)[len("CSI:"):]
    accident_type = row.get("accident_type")
    work_type = row.get("work_type")
    return {
        "object_type": CsiAccidentAdapter.object_type,
        "canonical_id": str(content_id),
        "source_id": "CSI",
        "source_key": None,  # CSI file has no source-native id
        "title": str(title),
        "summary": str(summary) if summary else None,
        "search_text": " ".join(as_str_list(
            [title, summary, accident_type, work_type])),
        "aliases": [],
        "keywords": as_str_list([accident_type, work_type]),
        "subjects": [],
        "context": [],
        "public_url": f"/public/accidents/csi/{uuid_part}",
        "saas_url": f"/saas/accident/{uuid_part}",
        "publication_status": "PUBLISHED",
        "visibility_scopes": ["PUBLIC", "SAAS", "PAID"],
        "source_updated_at": coerce_iso(row.get("updated_at")
                                        or row.get("first_seen_at")),
    }
