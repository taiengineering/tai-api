"""MARKETING_KNOWLEDGE adapter — WO-MKT-KNOWLEDGE-OPENSEARCH-AUTO-INDEX-001.

Source of truth:
  45cm-mkt-db / public.marketing_content  (engine_code='know', status='PUBLISHED')
  45cm-mkt-db / public.marketing_content_version  (latest version per content_id)

domain_name  = MARKETING_KNOWLEDGE
object_type  = KNOWLEDGE  (same bucket as TAI_HELP_CENTER; UI shows one "지식" section)
source_id    = TAI_MARKETING_KNOWLEDGE
canonical_id = MKTKNOW:{content.id}  (prefix prevents collision with help-center IDs)
public_url   = /knowledge/{content.slug}
"""
from __future__ import annotations

import re
from typing import Callable, Iterable, Iterator, Optional

from services.shared_search.adapters._common import (
    MISSING_TIMESTAMP,
    as_str_list,
    expected_hashes_from_documents,
    first_present_iso,
)

_TAG_RE = re.compile(r"<[^>]+>")

CANONICAL_PREFIX = "MKTKNOW:"
_ENGINE_CODE = "know"
SOURCE_ID = "TAI_MARKETING_KNOWLEDGE"

CONTENT_SELECT = (
    "id,title,slug,subject,category,law_name,article,status,updated_at,engine_code"
)
VERSION_SELECT = "content_id,title,body,meta_description,rules_snapshot,version"
PAGE_SIZE = 500


def _strip_html(value: Optional[str]) -> str:
    if not value:
        return ""
    return _TAG_RE.sub(" ", value).strip()


def to_canonical(content_id: str) -> str:
    return f"{CANONICAL_PREFIX}{content_id}"


def from_canonical(canonical_id: str) -> Optional[str]:
    if canonical_id.startswith(CANONICAL_PREFIX):
        return canonical_id[len(CANONICAL_PREFIX):]
    return None


class MarketingKnowledgeAdapter:
    domain_name = "MARKETING_KNOWLEDGE"
    object_type = "KNOWLEDGE"

    def __init__(
        self,
        *,
        fetch_current: Callable[[], Iterable[dict]],
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
    """Map a marketing_content row (with _version injected) to a SearchDocument payload."""
    content_id = row.get("id")
    title = row.get("title")
    if not content_id or not title:
        return None
    if row.get("status") != "PUBLISHED":
        return None
    slug = (row.get("slug") or "").strip()
    if not slug:
        return None
    ts = first_present_iso(row.get("updated_at"))
    if ts is MISSING_TIMESTAMP:
        return None

    canonical_id = to_canonical(content_id)

    ver = row.get("_version") or {}
    body_text = _strip_html(ver.get("body") or "")
    meta_description = (ver.get("meta_description") or "").strip()

    summary = meta_description or (body_text[:200] if body_text else None)

    rules_kw = (ver.get("rules_snapshot") or {}).get("keyword")
    keywords = as_str_list([
        row.get("category"),
        row.get("law_name"),
        row.get("article"),
        rules_kw,
    ])

    subject = (row.get("subject") or "").strip()
    search_text = " ".join(as_str_list([
        title,
        subject,
        row.get("law_name"),
        row.get("article"),
        meta_description,
        body_text,
    ]))

    aliases: list[str] = [subject] if subject and subject != title else []

    return {
        "object_type": MarketingKnowledgeAdapter.object_type,
        "canonical_id": canonical_id,
        "source_id": SOURCE_ID,
        "source_key": slug,
        "title": str(title),
        "summary": summary,
        "search_text": search_text,
        "aliases": aliases,
        "keywords": keywords,
        "subjects": [],
        "context": [],
        "public_url": f"/knowledge/{slug}",
        "saas_url": None,
        "publication_status": "PUBLISHED",
        "visibility_scopes": ["PUBLIC", "SAAS", "PAID"],
        "source_updated_at": ts,
    }
