"""REFERENCE_FORM adapter — WO-020.

Source of truth: `reference_form_public_view` (PUBLISHED + approved_content_hash gate)
                 + `reference_form_sources` (rights CLEARED gate, same as detail API)
                 + `reference_form_content` (body_html for full-text search)

Publication gate:  view WHERE clause — PUBLISHED + content_hash = approved_content_hash
Rights gate:       all active sources must have rights_status = 'CLEARED';
                   any REVIEW_REQUIRED/BLOCKED source → form excluded (fail-closed)
Body:              reference_form_content.body_html injected as _body_html by the binding

Canonical detail route: /reference-form/{canonical_slug}
"""
from __future__ import annotations

import re
from typing import Callable, Iterable, Iterator, Optional

from services.shared_search.adapters._common import (
    MISSING_TIMESTAMP, as_str_list,
    expected_hashes_from_documents, first_present_iso,
)


Fetcher = Callable[[], Iterable[dict]]

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(value: Optional[str]) -> str:
    if not value:
        return ""
    return _TAG_RE.sub(" ", value)


class ReferenceFormAdapter:
    domain_name = "REFERENCE_FORM"
    object_type = "REFERENCE_FORM"

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
            payload = _normalize(row)
            if payload is not None:
                yield payload

    def iter_expected_hashes(self) -> Iterator[dict]:
        yield from expected_hashes_from_documents(self.iter_documents)

    def object_reindex_payload(self, canonical_id: str) -> Optional[dict]:
        row = self._fetch_by_id(canonical_id)
        return _normalize(row) if row is not None else None


def _normalize(row: dict) -> Optional[dict]:
    form_id = row.get("id")
    title = row.get("title")
    canonical_slug = row.get("canonical_slug")
    if not form_id or not title or not canonical_slug:
        return None
    ts = first_present_iso(row.get("updated_at"), row.get("published_at"))
    if ts is MISSING_TIMESTAMP:
        return None
    description = row.get("description") or ""
    # legacy_codes (list[str] | None) add acronym/code-style aliases.
    legacy_codes: list[str] = list(row.get("legacy_codes") or [])
    # _body_html is injected by the production binding after rights check.
    body_text = _strip_html(row.get("_body_html") or "").strip()
    return {
        "object_type": ReferenceFormAdapter.object_type,
        "canonical_id": str(form_id),
        "source_id": "TAI_REFERENCE_FORM",
        "source_key": str(canonical_slug),
        "title": str(title),
        "summary": description or None,
        "search_text": " ".join(as_str_list([title, description, body_text] + legacy_codes)),
        "aliases": legacy_codes,
        "keywords": [],
        "subjects": [],
        "context": [],
        "public_url": f"/reference-form/{canonical_slug}",
        "saas_url": None,
        "publication_status": "PUBLISHED",
        "visibility_scopes": ["PUBLIC"],
        "source_updated_at": ts,
    }
