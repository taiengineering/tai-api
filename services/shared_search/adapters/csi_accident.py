"""CSI_ACCIDENT adapter — WO-TAI-SHARED-SEARCH-F2 §18 + F2 CO §14-§17.

Source of truth: `public.csi_accident_current` (verified in
supabase/migrations/20260913_csi_accident_catalog.sql).

Real columns: content_id, source_id, source_key, identity_fingerprint,
identity_status, identity_reason, title, occurred_at, construction_type,
process_major, process_minor, object_major, object_minor,
work_process, accident_type_major, accident_type, cause_major,
cause_mid, cause_minor, cause_detail, summary, death_count,
injury_count, source_dataset_url, source_item_url,
source_content_hash, snapshot_id.

Public detail route: tai-www `/accident/csi/{uuid}` (verified in
tai-www main src/pages/accident/csi/[uuid].astro).
"""
from __future__ import annotations

from typing import Callable, Iterable, Iterator, Optional

from services.shared_search.adapters._common import (
    MISSING_TIMESTAMP, as_str_list, coerce_iso,
    expected_hashes_from_documents, first_present_iso,
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
        # fetch_current yields rows from csi_accident_current (view).
        # The view already carries snapshot_items.identity_status —
        # this adapter still filters to READY as a defense-in-depth.
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
    if row.get("identity_status") != "READY":
        return None
    title = row.get("title")
    summary = row.get("summary")
    if not title:
        return None
    ts = first_present_iso(
        row.get("occurred_at"),
        row.get("_snapshot_completed_at"),
    )
    if ts is MISSING_TIMESTAMP:
        return None
    uuid_part = str(content_id)[len("CSI:"):]
    work_process = row.get("work_process")
    accident_type = row.get("accident_type")
    accident_type_major = row.get("accident_type_major")
    process_major = row.get("process_major")
    process_minor = row.get("process_minor")
    object_major = row.get("object_major")
    cause_major = row.get("cause_major")
    construction_type = row.get("construction_type")
    return {
        "object_type": CsiAccidentAdapter.object_type,
        "canonical_id": str(content_id),
        "source_id": "CSI",
        "source_key": None,   # CSI file has no source-native id
        "title": str(title),
        "summary": str(summary) if summary else None,
        "search_text": " ".join(as_str_list([
            title, summary, work_process, accident_type,
            accident_type_major, process_major, process_minor,
            object_major, cause_major, construction_type,
        ])),
        "aliases": [],
        "keywords": as_str_list([accident_type, work_process, construction_type]),
        "subjects": [],
        "context": [],
        # Public detail route in tai-www — verified.
        "public_url": f"/accident/csi/{uuid_part}",
        "saas_url": None,
        "publication_status": "PUBLISHED",
        "visibility_scopes": ["PUBLIC", "SAAS", "PAID"],
        "source_updated_at": ts,
    }
