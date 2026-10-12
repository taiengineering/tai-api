"""EXT-132 위험물안전관리 Shared Search adapter.

Source of truth: ext132_hazardous_material_snapshot_items.
Snapshot: is_current=True, status=COMPLETED (no collect_scope gate).

canonical_id  = chemicalno
object_type   = "HAZARDOUS_MATERIAL"
source_id     = EXT132_HAZARDOUS_MATERIAL
visibility_scopes = ["PUBLIC"]
public_url    = null (no dedicated detail page in WP-04 scope)

title fallback: chemical_name → "No {chemicalno}"
source_updated_at = _snapshot_completed_at (injected by production binding)
MISSING_TIMESTAMP rows are skipped.
"""
from __future__ import annotations

from typing import Callable, Iterable, Iterator, Optional

from services.ext132_hazardous_material.contract import SOURCE_ID as _SOURCE_ID
from services.shared_search.adapters._common import (
    MISSING_TIMESTAMP,
    as_str_list,
    expected_hashes_from_documents,
    first_present_iso,
)


Fetcher = Callable[[], Iterable[dict]]


class HazardousMaterialAdapter:
    domain_name = "HAZARDOUS_MATERIAL"
    object_type = "HAZARDOUS_MATERIAL"

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
            payload = _normalize_hazardous(row)
            if payload is not None:
                yield payload

    def iter_expected_hashes(self) -> Iterator[dict]:
        yield from expected_hashes_from_documents(self.iter_documents)

    def object_reindex_payload(self, canonical_id: str) -> Optional[dict]:
        row = self._fetch_by_id(canonical_id)
        if row is None:
            return None
        return _normalize_hazardous(row)


def _normalize_hazardous(row: dict) -> Optional[dict]:
    raw = row.get("raw") or {}
    chemicalno = (row.get("chemicalno") or raw.get("chemaicalno") or "").strip()
    if not chemicalno:
        return None

    chemical_name = (raw.get("chemicalname") or "").strip()
    cas_no = (raw.get("casno") or "").strip()
    un_no = (raw.get("unno") or "").strip()
    hazard_class = (raw.get("hazardmaterialclass") or "").strip()

    title = chemical_name or f"No {chemicalno}"

    ts = first_present_iso(row.get("_snapshot_completed_at"))
    if ts is MISSING_TIMESTAMP:
        return None

    search_parts = as_str_list([chemical_name, cas_no, un_no, hazard_class])

    return {
        "object_type": HazardousMaterialAdapter.object_type,
        "canonical_id": str(chemicalno),
        "source_id": _SOURCE_ID,
        "source_key": str(chemicalno),
        "title": str(title),
        "summary": hazard_class or None,
        "search_text": " ".join(search_parts),
        "aliases": as_str_list([cas_no, un_no]),
        "keywords": [],
        "subjects": [],
        "context": (
            [{"context_type": "chemical", "context_key": cas_no}] if cas_no else []
        ),
        "public_url": None,
        "saas_url": None,
        "publication_status": "PUBLISHED",
        "visibility_scopes": ["PUBLIC"],
        "source_updated_at": ts,
    }
