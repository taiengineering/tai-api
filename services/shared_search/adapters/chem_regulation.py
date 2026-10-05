"""CHEM_REGULATION adapter — KECO chemical regulation data.

Source of truth: msds_ref.keco_chemicals + msds_ref.keco_regulatory_facts.
Public URL resolved via msds_ref.identity_projection (CAS→KOSHA chem_id).

canonical_id  = source_record_id (KECO sbstnId).
object_type   = "CHEM_REGULATION".
source_id     = KECO_15149420 (services.keco_chemical.contract.SOURCE_ID).
visibility_scopes = ["PUBLIC", "SAAS", "PAID"] always (no mode gate).

public_url logic (injected via _cas_to_chem_ids):
  0 KOSHA matches → null
  1 match         → /msds/{chem_id}#keco
  ≥2 matches      → /msds?q={cas}

title fallback: chemical_name_ko → chemical_name_en → "CAS {cas}" → drop.
source_updated_at = first_present_iso(updated_at, last_seen_at).
MISSING_TIMESTAMP rows are skipped (Foundation §34).

Production binding injects two extra keys per row before yielding:
  _cas_to_chem_ids: dict[str, list[str]]  — full CAS→[chem_id, ...] map
  _regulatory_facts: list[dict]           — facts for this chemical
"""
from __future__ import annotations

from typing import Callable, Iterable, Iterator, Optional
from urllib.parse import quote

from services.keco_chemical.contract import SOURCE_ID as _KECO_SOURCE_ID
from services.shared_search.adapters._common import (
    MISSING_TIMESTAMP,
    as_str_list,
    expected_hashes_from_documents,
    first_present_iso,
)


Fetcher = Callable[[], Iterable[dict]]


class ChemRegulationAdapter:
    domain_name = "CHEM_REGULATION"
    object_type = "CHEM_REGULATION"

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
            payload = _normalize_chem_regulation(row)
            if payload is not None:
                yield payload

    def iter_expected_hashes(self) -> Iterator[dict]:
        yield from expected_hashes_from_documents(self.iter_documents)

    def object_reindex_payload(self, canonical_id: str) -> Optional[dict]:
        row = self._fetch_by_id(canonical_id)
        if row is None:
            return None
        return _normalize_chem_regulation(row)


def _normalize_chem_regulation(row: dict) -> Optional[dict]:
    source_record_id = row.get("source_record_id")
    if not source_record_id:
        return None

    ko = (row.get("chemical_name_ko") or "").strip() or None
    en = (row.get("chemical_name_en") or "").strip() or None
    cas = row.get("cas_no")

    # Title fallback: ko → en → "CAS {cas}" → drop
    if ko:
        title = ko
    elif en:
        title = en
    elif cas:
        title = f"CAS {cas}"
    else:
        return None

    ts = first_present_iso(row.get("updated_at"), row.get("last_seen_at"))
    if ts is MISSING_TIMESTAMP:
        return None

    korexst = row.get("korexst_raw")
    alias_ko = row.get("alias_name_ko")
    alias_en = row.get("alias_name_en")
    formula = row.get("molecular_formula")

    facts = row.get("_regulatory_facts") or []

    # aliases: name variants + CAS + korexst + unique_no + classification_type per fact
    reg_alias_parts = []
    for f in facts:
        reg_alias_parts.append(f.get("unique_no"))
        reg_alias_parts.append(f.get("classification_type"))
    aliases = as_str_list([en, alias_ko, alias_en, cas, korexst] + reg_alias_parts)

    # search_text: name fields + all regulatory text fields (deterministic concat)
    search_parts = as_str_list([title, ko, en, alias_ko, alias_en, cas, korexst, formula])
    for f in facts:
        search_parts.extend(as_str_list([
            f.get("classification_type"),
            f.get("unique_no"),
            f.get("content_info"),
            f.get("exception_info"),
            f.get("notice_info"),
        ]))

    public_url: Optional[str] = None
    cas_to_chem_ids: dict = row.get("_cas_to_chem_ids") or {}
    if cas:
        matched_ids = cas_to_chem_ids.get(cas, [])
        if len(matched_ids) == 1:
            public_url = f"/msds/{quote(str(matched_ids[0]), safe='')}#keco"
        elif len(matched_ids) >= 2:
            public_url = f"/msds?q={quote(cas, safe='')}"

    return {
        "object_type": ChemRegulationAdapter.object_type,
        "canonical_id": str(source_record_id),
        "source_id": _KECO_SOURCE_ID,
        "source_key": str(source_record_id),
        "title": str(title),
        "summary": str(en) if en else None,
        "search_text": " ".join(search_parts),
        "aliases": aliases,
        "keywords": [],
        "subjects": [],
        "context": (
            [{"context_type": "chemical", "context_key": cas}] if cas else []
        ),
        "public_url": public_url,
        "saas_url": None,
        "publication_status": "PUBLISHED",
        "visibility_scopes": ["PUBLIC", "SAAS", "PAID"],
        "source_updated_at": ts,
    }
