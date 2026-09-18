"""CHEM adapter — WO-TAI-SHARED-SEARCH-F2 §19, §20.

Reads the Domain's already-published current read model (SEO preview
OR FULL). Search NEVER re-runs `cutover.is_full_ready`. Public
visibility is gated by `KOSHA_MSDS_PUBLIC_MODE` — an env value the
adapter reads but never sets.
"""
from __future__ import annotations

import os
from typing import Callable, Iterable, Iterator, Optional

from services.shared_search.adapters._common import (
    as_str_list, coerce_iso, expected_hashes_from_documents,
)


Fetcher = Callable[[], Iterable[dict]]


def _public_mode() -> str:
    # Duplicated env-name reuse of the Domain's own contract
    # (services.kosha_msds.contract.PUBLIC_MODE_ENV_VAR). We do NOT
    # import from there to avoid a cross-package dep at Foundation
    # level; the env var name is stable + Domain-authored.
    return (os.environ.get("KOSHA_MSDS_PUBLIC_MODE") or "off").strip().lower()


class ChemAdapter:
    domain_name = "CHEM"
    object_type = "CHEM"

    def __init__(
        self,
        *,
        fetch_current: Fetcher,
        fetch_by_id: Optional[Callable[[str], Optional[dict]]] = None,
        public_mode_getter: Callable[[], str] = _public_mode,
    ):
        # fetch_current yields rows joined from
        # kosha_msds_seo_preview_current or kosha_msds_full_current —
        # the Domain's authoritative published views.
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
        return _normalize_chem(row, public_allowed=(self._public_mode()
                                                   in ("seo_preview", "full")))


def _normalize_chem(row: dict, *, public_allowed: bool) -> Optional[dict]:
    chem_uuid = row.get("id")
    chem_id = row.get("source_key") or row.get("chem_id")
    ko = row.get("chemical_name_ko")
    if not chem_uuid or not chem_id or not ko:
        return None
    en = row.get("chemical_name_en")
    cas = row.get("cas_no")
    ke = row.get("ke_no")
    en_no = row.get("en_no")
    un = row.get("un_no")
    aliases = as_str_list([en, cas, ke, en_no, un])
    scopes = ["SAAS", "PAID"]
    if public_allowed:
        scopes.insert(0, "PUBLIC")
    return {
        "object_type": ChemAdapter.object_type,
        "canonical_id": str(chem_uuid),
        "source_id": "KOSHA_MSDS",
        "source_key": str(chem_id),
        "title": str(ko),
        "summary": str(en) if en else None,
        "search_text": " ".join(as_str_list([ko, en, cas, ke, en_no, un])),
        "aliases": aliases,
        "keywords": [],
        "subjects": [],   # CHEM_TERM per-chemical assignment is deferred
                          # (F2 WO §19; per-row evidence not yet gathered)
        "context": [{"context_type": "chemical", "context_key": str(chem_id)}],
        "public_url": f"/public/kosha/msds/{chem_uuid}" if public_allowed else None,
        "saas_url": f"/saas/chemical/{chem_uuid}",
        "publication_status": "PUBLISHED",
        "visibility_scopes": scopes,
        "source_updated_at": coerce_iso(row.get("last_date")
                                        or row.get("updated_at")),
    }
