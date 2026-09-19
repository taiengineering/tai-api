"""CHEM adapter — WO-TAI-SHARED-SEARCH-F2 §19-§21 + F2 CO §18-§21.

Source of truth: `public.kosha_msds_seo_preview_current` and
`public.kosha_msds_current` (verified in
supabase/migrations/20260914_kosha_msds_catalog.sql and
20260918_kosha_msds_seo_preview.sql).

Real columns: id, content_id, source_id, source_key, chem_id,
identity_status, chemical_name_ko, chemical_name_en, cas_no, ke_no,
en_no, un_no, source_content_hash, source_dataset_url, snapshot_id.

The view has NO timestamp column. Production binding joins to
`kosha_msds_snapshots.completed_at` via `snapshot_id` and the reader
surfaces it as `_snapshot_completed_at`.

Public URL: no verified tai-www HTML route for MSDS today.
Foundation returns `public_url = null`; the `/public/kosha/msds/*`
tai-api endpoint is a JSON API, not a public HTML page.
"""
from __future__ import annotations

import os
from typing import Callable, Iterable, Iterator, Optional

from services.shared_search.adapters._common import (
    MISSING_TIMESTAMP, as_str_list, coerce_iso,
    expected_hashes_from_documents, first_present_iso,
)


Fetcher = Callable[[], Iterable[dict]]


def _default_public_mode() -> str:
    """Reads the env var name used by the Domain
    (services.kosha_msds.contract.PUBLIC_MODE_ENV_VAR). We inline
    the name to avoid a cross-package dep here."""
    return (os.environ.get("KOSHA_MSDS_PUBLIC_MODE") or "off").strip().lower()


class ChemAdapter:
    domain_name = "CHEM"
    object_type = "CHEM"

    def __init__(
        self,
        *,
        fetch_current: Fetcher,
        fetch_by_id: Optional[Callable[[str], Optional[dict]]] = None,
        public_mode_getter: Callable[[], str] = _default_public_mode,
    ):
        # fetch_current yields rows from the Domain's authoritative
        # published current view (SEO preview OR FULL). Production
        # binding picks the right view based on live publish state.
        self._fetch_current = fetch_current
        self._fetch_by_id = fetch_by_id or (lambda _id: None)
        self._public_mode = public_mode_getter

    def iter_documents(self) -> Iterator[dict]:
        mode = self._public_mode()
        public_allowed = mode in ("seo_preview", "full")
        for row in self._fetch_current():
            payload = _normalize_chem(row, public_allowed=public_allowed)
            if payload is not None:
                yield payload

    def iter_expected_hashes(self) -> Iterator[dict]:
        yield from expected_hashes_from_documents(self.iter_documents)

    def object_reindex_payload(self, canonical_id: str) -> Optional[dict]:
        row = self._fetch_by_id(canonical_id)
        if row is None:
            return None
        return _normalize_chem(row,
                               public_allowed=(self._public_mode()
                                               in ("seo_preview", "full")))


def _normalize_chem(row: dict, *, public_allowed: bool) -> Optional[dict]:
    chem_uuid = row.get("id")
    chem_id = row.get("source_key") or row.get("chem_id")
    ko = row.get("chemical_name_ko")
    # Official Section 1 A02 product name, attached by the CHEM
    # Domain binding. Identity remains chemical UUID / chem_id;
    # this is display-name only. No synthetic "MSDS-NNNNNN" title.
    product_name = row.get("product_name")
    title = ko or product_name
    if not chem_uuid or not chem_id or not title:
        return None
    # F2 CO §21: the view has no per-chemical timestamp. The reader
    # surfaces `_snapshot_completed_at` from the snapshot join. If it
    # isn't present, the row is skipped (no fake epoch).
    ts = first_present_iso(row.get("_snapshot_completed_at"))
    if ts is MISSING_TIMESTAMP:
        return None
    en = row.get("chemical_name_en")
    cas = row.get("cas_no")
    ke = row.get("ke_no")
    en_no = row.get("en_no")
    un = row.get("un_no")
    aliases = as_str_list([en, product_name, cas, ke, en_no, un])
    scopes = ["SAAS", "PAID"]
    if public_allowed:
        scopes.insert(0, "PUBLIC")
    return {
        "object_type": ChemAdapter.object_type,
        "canonical_id": str(chem_uuid),
        "source_id": "KOSHA_MSDS",
        "source_key": str(chem_id),
        "title": str(title),
        "summary": str(en) if en else None,
        "search_text": " ".join(as_str_list([title, ko, product_name, en, cas, ke, en_no, un])),
        "aliases": aliases,
        "keywords": [],
        "subjects": [],   # CHEM_TERM per-chemical subject assignment deferred
        "context": [{"context_type": "chemical", "context_key": str(chem_id)}],
        # F2 CO §19-§20: no verified HTML public/saas routes for CHEM.
        # `/public/kosha/msds/*` is a tai-api JSON endpoint, NOT a
        # public HTML page. Returning null avoids fabricating a route
        # that the retrieval engine would then present as a link.
        "public_url": None,
        "saas_url": None,
        "publication_status": "PUBLISHED",
        "visibility_scopes": scopes,
        "source_updated_at": ts,
    }
