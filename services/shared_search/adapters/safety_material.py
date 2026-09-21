"""SAFETY_MATERIAL adapter — WO-TAI-SHARED-SEARCH-F2 §17 + F2 CO §10-§13.

Domain SoT is spread across several tables:

    kosha_safety_materials                    catalog (id, title, url,
                                              category, industry_category,
                                              accident_type, product_type,
                                              raw_json)
    kosha_safety_material_snapshots           run metadata
    kosha_safety_material_snapshot_items      per-snapshot membership
    kosha_safety_material_details             per-material rich payload
                                              (source_med_seq, source_title,
                                              source_description,
                                              source_published_at, source_url)
    kosha_safety_material_storage_holds       storage-hold policy

The production binding pre-assembles a Domain read-model dict per
material (the shared source_reader isn't asked to do multi-way
joins). The adapter accepts that assembled dict — Foundation §17
"공통 시스템으로 이동 금지" prevents pushing domain-specific joins
into the adapter itself.

Expected dict keys (from production binding assembly):

    id                — catalog primary key
    title             — catalog.title
    url               — catalog.url
    category
    industry_category
    accident_type
    source_med_seq    — details.source_med_seq (NULLABLE — F2 CO §11)
    source_title      — details.source_title
    source_description
    source_url        — details.source_url
    source_published_at
    source_updated_at
    storage_hold      — bool, True when any unresolved hold exists
    _snapshot_completed_at — reader-supplied authoritative timestamp
"""
from __future__ import annotations

from typing import Callable, Iterable, Iterator, Optional
from urllib.parse import quote

from services.shared_search.adapters._common import (
    MISSING_TIMESTAMP, as_str_list, coerce_iso,
    expected_hashes_from_documents, first_present_iso,
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
    title = row.get("title") or row.get("source_title")
    if not mid or not title:
        return None
    ts = first_present_iso(
        row.get("source_updated_at"),
        row.get("source_published_at"),
        row.get("_snapshot_completed_at"),
    )
    if ts is MISSING_TIMESTAMP:
        return None
    med_seq = row.get("source_med_seq")
    source_key = str(med_seq) if med_seq is not None else None
    if row.get("storage_hold") is True:
        return {
            "object_type": SafetyMaterialAdapter.object_type,
            "canonical_id": str(mid),
            "source_id": "KOSHA_OFFICIAL_MATERIAL",
            "source_key": source_key,
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
            "source_updated_at": ts,
        }
    summary = row.get("source_description")
    category = row.get("category")
    industry = row.get("industry_category")
    accident = row.get("accident_type")
    return {
        "object_type": SafetyMaterialAdapter.object_type,
        "canonical_id": str(mid),
        "source_id": "KOSHA_OFFICIAL_MATERIAL",
        "source_key": source_key,
        "title": str(title),
        "summary": str(summary) if summary else None,
        "search_text": " ".join(as_str_list([
            title, summary, category, industry, accident,
        ])),
        "aliases": [],
        "keywords": as_str_list([category, industry, accident]),
        "subjects": [],
        "context": ([{"context_type": "sector", "context_key": industry}]
                    if industry else []),
        "public_url": f"/safety-news/{quote(str(mid), safe='')}",
        "saas_url": None,
        "publication_status": "PUBLISHED",
        "visibility_scopes": ["PUBLIC", "SAAS", "PAID"],
        "source_updated_at": ts,
    }
