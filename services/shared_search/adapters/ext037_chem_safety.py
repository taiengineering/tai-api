"""EXT-037 화학물질 안전정보 Shared Search adapter.

Source of truth: ext037_chemical_safety_snapshot_items.
Snapshot: is_current=True, status=COMPLETED (no collect_scope gate).

canonical_id  = datano
object_type   = "CHEM_SAFETY"
source_id     = EXT037_CHEMICAL_SAFETY
visibility_scopes = ["PUBLIC"]
public_url    = null (no dedicated detail page in WP-04 scope)

title fallback: chemKo → chemEn → "dataNo {datano}"
source_updated_at = _snapshot_completed_at (injected by production binding)
MISSING_TIMESTAMP rows are skipped.
"""
from __future__ import annotations

from typing import Callable, Iterable, Iterator, Optional

from services.ext037_chemical_safety.contract import SOURCE_ID as _SOURCE_ID
from services.shared_search.adapters._common import (
    MISSING_TIMESTAMP,
    as_str_list,
    expected_hashes_from_documents,
    first_present_iso,
)


Fetcher = Callable[[], Iterable[dict]]


class ChemSafetyAdapter:
    domain_name = "CHEM_SAFETY"
    object_type = "CHEM_SAFETY"

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
            payload = _normalize_chem_safety(row)
            if payload is not None:
                yield payload

    def iter_expected_hashes(self) -> Iterator[dict]:
        yield from expected_hashes_from_documents(self.iter_documents)

    def object_reindex_payload(self, canonical_id: str) -> Optional[dict]:
        row = self._fetch_by_id(canonical_id)
        if row is None:
            return None
        return _normalize_chem_safety(row)


def _normalize_chem_safety(row: dict) -> Optional[dict]:
    raw = row.get("raw") or {}
    datano = (row.get("datano") or raw.get("dataNo") or "").strip()
    if not datano:
        return None

    chem_ko = (raw.get("chemKo") or "").strip()
    chem_en = (raw.get("chemEn") or "").strip()
    cas_no = (raw.get("casNo") or "").strip()

    if chem_ko:
        title = chem_ko
    elif chem_en:
        title = chem_en
    else:
        title = f"dataNo {datano}"

    ts = first_present_iso(row.get("_snapshot_completed_at"))
    if ts is MISSING_TIMESTAMP:
        return None

    symptom = (raw.get("symptom") or "").strip()
    oral = (raw.get("oral") or "").strip()
    skin = (raw.get("skin") or "").strip()
    inhale = (raw.get("inhale") or "").strip()
    eyeball = (raw.get("eyeball") or "").strip()
    etc = (raw.get("etc") or "").strip()

    search_parts = as_str_list(
        [chem_ko, chem_en, cas_no, symptom, oral, skin, inhale, eyeball, etc]
    )

    return {
        "object_type": ChemSafetyAdapter.object_type,
        "canonical_id": str(datano),
        "source_id": _SOURCE_ID,
        "source_key": str(datano),
        "title": str(title),
        "summary": symptom or None,
        "search_text": " ".join(search_parts),
        "aliases": as_str_list([chem_en, cas_no]),
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
