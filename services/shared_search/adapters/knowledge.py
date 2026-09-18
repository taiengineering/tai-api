"""KNOWLEDGE (help center) adapter — WO-TAI-SHARED-SEARCH-F2 §21 + F2 CO §22-§24.

Source of truth: `public.safe_help_content` (verified via
services/safe_help_svc.py; safe_help_svc reads columns:
question, answer_short, body, steps, sectors, min_level,
related_pages, menu_group, doc_id, slug, title, status, updated_at).

Publication gate: `status = 'PUBLISHED'`.

Public/SaaS HTML routes not verified in tai-www today — returning
null on both URL fields (F2 CO §24).
"""
from __future__ import annotations

import re
from typing import Callable, Iterable, Iterator, Optional

from services.shared_search.adapters._common import (
    MISSING_TIMESTAMP, as_str_list, coerce_iso,
    expected_hashes_from_documents, first_present_iso,
)


Fetcher = Callable[[], Iterable[dict]]


_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(value: Optional[str]) -> str:
    if not value:
        return ""
    return _TAG_RE.sub(" ", value)


class KnowledgeAdapter:
    domain_name = "KNOWLEDGE"
    object_type = "KNOWLEDGE"

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
            payload = _normalize_help(row)
            if payload is not None:
                yield payload

    def iter_expected_hashes(self) -> Iterator[dict]:
        yield from expected_hashes_from_documents(self.iter_documents)

    def object_reindex_payload(self, canonical_id: str) -> Optional[dict]:
        row = self._fetch_by_id(canonical_id)
        return _normalize_help(row) if row is not None else None


def _normalize_help(row: dict) -> Optional[dict]:
    doc_id = row.get("doc_id")
    title = row.get("title")
    if not doc_id or not title:
        return None
    if row.get("status") != "PUBLISHED":
        return None
    ts = first_present_iso(row.get("updated_at"))
    if ts is MISSING_TIMESTAMP:
        return None
    # F2 CO §23: real columns are body / question / answer_short (not
    # body_text / body_stripped).
    body_html = row.get("body") or ""
    body_text = _strip_html(body_html).strip()
    question = row.get("question")
    answer_short = row.get("answer_short")
    menu_group = row.get("menu_group")
    return {
        "object_type": KnowledgeAdapter.object_type,
        "canonical_id": str(doc_id),
        "source_id": "TAI_HELP_CENTER",
        "source_key": str(doc_id),
        "title": str(title),
        "summary": (answer_short or (body_text[:200] if body_text else None)),
        "search_text": " ".join(as_str_list([
            title, question, answer_short, body_text,
        ])),
        "aliases": [],
        "keywords": as_str_list([menu_group]),
        "subjects": [],
        "context": [],
        # F2 CO §24: no verified tai-www help route today.
        "public_url": None,
        "saas_url": None,
        "publication_status": "PUBLISHED",
        "visibility_scopes": ["PUBLIC", "SAAS", "PAID"],
        "source_updated_at": ts,
    }
