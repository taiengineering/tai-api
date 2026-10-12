"""EXT-165 화학사고 Shared Search adapter.

Source of truth: ext165_chemical_accident_snapshot_items.
Snapshot: is_current=True, status=COMPLETED, collect_scope IS NULL.

canonical_id  = datano
object_type   = "CHEM_ACCIDENT"
source_id     = EXT165_CHEMICAL_ACCIDENT
visibility_scopes = ["PUBLIC"]
public_url    = /accident/chemical/{datano}  (WP-03 detail page)

title: first non-empty from [chemical, area, accident_type] joined with space;
       fallback "사고 {datano}".
summary: raw.summary
source_updated_at = _snapshot_completed_at (injected by production binding)
MISSING_TIMESTAMP rows are skipped.
"""
from __future__ import annotations

from typing import Callable, Iterable, Iterator, Optional
from urllib.parse import quote

from services.ext165_chemical_accident.contract import SOURCE_ID as _SOURCE_ID
from services.shared_search.adapters._common import (
    MISSING_TIMESTAMP,
    as_str_list,
    expected_hashes_from_documents,
    first_present_iso,
)


Fetcher = Callable[[], Iterable[dict]]


class ChemAccidentAdapter:
    domain_name = "CHEM_ACCIDENT"
    object_type = "CHEM_ACCIDENT"

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
            payload = _normalize_chem_accident(row)
            if payload is not None:
                yield payload

    def iter_expected_hashes(self) -> Iterator[dict]:
        yield from expected_hashes_from_documents(self.iter_documents)

    def object_reindex_payload(self, canonical_id: str) -> Optional[dict]:
        row = self._fetch_by_id(canonical_id)
        if row is None:
            return None
        return _normalize_chem_accident(row)


def _normalize_chem_accident(row: dict) -> Optional[dict]:
    raw = row.get("raw") or {}
    datano = (
        row.get("datano") or raw.get("dataNo") or raw.get("datano") or ""
    ).strip()
    if not datano:
        return None

    accident_type = (raw.get("cscTy") or "").strip()
    area = (raw.get("area") or "").strip()
    place = (raw.get("place") or "").strip()
    chemical = (raw.get("chem") or "").strip()
    cause = (raw.get("cause") or "").strip()
    summary = (raw.get("summary") or "").strip()
    acc_date = (raw.get("cscDe") or "").strip()

    title_parts = [p for p in [chemical, area, accident_type] if p]
    title = " ".join(title_parts) if title_parts else f"사고 {datano}"

    ts = first_present_iso(row.get("_snapshot_completed_at"))
    if ts is MISSING_TIMESTAMP:
        return None

    search_parts = as_str_list(
        [chemical, area, accident_type, place, cause, summary, acc_date]
    )

    return {
        "object_type": ChemAccidentAdapter.object_type,
        "canonical_id": str(datano),
        "source_id": _SOURCE_ID,
        "source_key": str(datano),
        "title": str(title),
        "summary": summary or None,
        "search_text": " ".join(search_parts),
        "aliases": [],
        "keywords": [],
        "subjects": [],
        "context": [],
        "public_url": "/accident/chemical/" + quote(str(datano), safe=""),
        "saas_url": None,
        "publication_status": "PUBLISHED",
        "visibility_scopes": ["PUBLIC"],
        "source_updated_at": ts,
    }
