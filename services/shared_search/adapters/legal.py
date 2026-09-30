"""LEGAL adapter — WO-TAI-SHARED-SEARCH-F2 §23 + F2 CO §27-§32.

Domain reality:
- `legal_obligations` table exists but has ZERO rows today
  (F2 CO §27). The adapter therefore treats obligation_atom as
  a BLOCKED subtype until Domain evidence lands.
- `law_article` has ~35,412 raw rows; the adapter supports the
  law_article subtype when the production binding hands over a
  Domain-side "is currently published" filter (law_master.is_active
  = true AND law_master.current_version_id = law_article.law_version_id
  AND law_article.is_deleted_in_version = false, per F2 FINAL §3-§10).

Canonical identity for law articles is `law_article.id` (Domain PK).
`article_internal_key` and `law_id + article_internal_key` are NEVER
used as canonical_id — production has 7,642 distinct article_internal_key
values across 35,412 current-eligible rows (33,482 distinct composite);
both collide and are explicitly forbidden (F2 FINAL §7).

Legal Engine remains the sole applicability authority. This adapter
never sets `legal_applicable` / `is_required` / any applicability
field — the writer's `FORBIDDEN_DOCUMENT_KEYS` guard rejects those
by construction.

Search text uses full projection resolution when `fetch_attachments_batch`
is supplied:
  ARTICLE_TEXT   → title + article_text
  ATTACHMENT_BODY → title + resolved attachment body
  ATTACHMENT_INDEX → title + attachment titles
  INLINE_MEDIA   → title + img-stripped prose
  SOURCE_CONTENT_UNRESOLVED → title only
"""
from __future__ import annotations

from typing import Callable, Iterable, Iterator, Optional
from urllib.parse import quote

from services.shared_search.adapters._common import (
    MISSING_TIMESTAMP, as_str_list, coerce_iso,
    expected_hashes_from_documents, first_present_iso,
)
from services.shared_search.adapters.base import AdapterBlockedSubtype


Fetcher = Callable[[], Iterable[dict]]
AttachmentBatchFetcher = Callable[[list[str]], dict[str, list[dict]]]


SUPPORTED_SUBTYPES = frozenset({"law_article"})
BLOCKED_SUBTYPES = frozenset({"obligation_atom", "norm_cluster"})


class LegalAdapter:
    domain_name = "LEGAL"
    object_type = "LEGAL"

    def __init__(
        self,
        *,
        fetch_current: Fetcher,
        fetch_by_id: Optional[Callable[[str], Optional[dict]]] = None,
        fetch_attachments_batch: Optional[AttachmentBatchFetcher] = None,
    ):
        # Production binding supplies rows already filtered to
        # "currently published" (per §29 join predicate). Each row
        # carries `record_kind` so the adapter can select subtype.
        self._fetch_current = fetch_current
        self._fetch_by_id = fetch_by_id or (lambda _id: None)
        # Optional: Callable[list[version_id], dict[version_id, list[attachment_dict]]]
        # When supplied, iter_documents does a two-pass: identifies stub rows, batch-fetches
        # attachments, and uses full projection for search_text.
        self._fetch_attachments_batch = fetch_attachments_batch
        self._blocked_seen: set[str] = set()

    def iter_documents(self) -> Iterator[dict]:
        from services.legal_content_projection import _classify_article_text

        rows = list(self._fetch_current())  # buffer for two-pass

        # Pass 1: identify law_version_ids of stub rows for batch attachment fetch
        attachment_map: dict[str, list[dict]] = {}
        if self._fetch_attachments_batch:
            stub_version_ids: set[str] = set()
            for row in rows:
                kind = (row.get("record_kind") or "").strip()
                if kind not in SUPPORTED_SUBTYPES:
                    continue
                text = row.get("article_text") or ""
                cls = _classify_article_text(text)
                if cls in ("SOURCE_UI_STUB", "RAW_SOURCE_LINK", "EMPTY"):
                    vid = row.get("law_version_id")
                    if vid:
                        stub_version_ids.add(vid)
            if stub_version_ids:
                attachment_map = self._fetch_attachments_batch(list(stub_version_ids))

        # Pass 2: yield documents with resolved projections
        for row in rows:
            kind = (row.get("record_kind") or "").strip()
            if kind in BLOCKED_SUBTYPES:
                self._blocked_seen.add(kind)
                continue
            if kind not in SUPPORTED_SUBTYPES:
                self._blocked_seen.add(kind or "UNKNOWN")
                continue
            vid = row.get("law_version_id")
            attachments = attachment_map.get(vid, []) if vid else []
            payload = _normalize_legal(row, attachments=attachments)
            if payload is not None:
                yield payload

        if self._blocked_seen:
            raise AdapterBlockedSubtype(
                f"LEGAL subtypes blocked: {sorted(self._blocked_seen)}"
            )

    def iter_expected_hashes(self) -> Iterator[dict]:
        yield from expected_hashes_from_documents(self.iter_documents)

    def object_reindex_payload(self, canonical_id: str) -> Optional[dict]:
        row = self._fetch_by_id(canonical_id)
        if row is None:
            return None
        kind = (row.get("record_kind") or "").strip()
        if kind not in SUPPORTED_SUBTYPES:
            return None
        attachments: list[dict] = []
        if self._fetch_attachments_batch:
            vid = row.get("law_version_id")
            if vid:
                att_map = self._fetch_attachments_batch([vid])
                attachments = att_map.get(vid, [])
        return _normalize_legal(row, attachments=attachments)


def _normalize_legal(row: dict, attachments: list[dict] = None) -> Optional[dict]:
    kind = (row.get("record_kind") or "").strip()
    if kind != "law_article":
        return None
    # F2 FINAL §7: canonical_id MUST be the Domain PK (`law_article.id`).
    canonical_id = row.get("id")
    if not canonical_id:
        return None
    law_name = row.get("law_name")
    article_no = row.get("article_no")
    article_sub_no = row.get("article_sub_no")
    article_text = row.get("article_text")

    from services.legal_content_projection import (
        build_public_legal_title,
        resolve_legal_content,
        search_text_from_projection,
    )

    title = build_public_legal_title(row)["title"]

    # Resolve content projection (includes attachment body for ATTACHMENT_BODY rows)
    projection = resolve_legal_content(article_text, attachments or [])
    clean_search_text = search_text_from_projection(projection, title)

    # F2 FINAL §14: real columns are `enforcement_date` + `updated_at`.
    ts = first_present_iso(
        row.get("enforcement_date"),
        row.get("updated_at"),
    )
    if ts is MISSING_TIMESTAMP:
        return None

    return {
        "object_type": LegalAdapter.object_type,
        "canonical_id": str(canonical_id),
        "source_id": row.get("source_id") or "LEG_OFFICIAL",
        "source_key": (str(row["source_key"])
                       if row.get("source_key") is not None else None),
        "title": title,
        "summary": None,
        "search_text": clean_search_text,
        "aliases": as_str_list([article_no, article_sub_no]),
        "keywords": as_str_list([law_name]),
        "subjects": ([{"subject_type": "LEGAL_TERM",
                        "subject_key": str(law_name)}] if law_name else []),
        "context": [],
        "public_url": f"/safety-search/legal/{quote(str(canonical_id), safe='')}",
        "saas_url": None,
        "publication_status": "PUBLISHED",
        "visibility_scopes": ["PUBLIC", "SAAS", "PAID"],
        "source_updated_at": ts,
    }
