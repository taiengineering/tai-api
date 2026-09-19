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
"""
from __future__ import annotations

from typing import Callable, Iterable, Iterator, Optional

from services.shared_search.adapters._common import (
    MISSING_TIMESTAMP, as_str_list, coerce_iso,
    expected_hashes_from_documents, first_present_iso,
)
from services.shared_search.adapters.base import AdapterBlockedSubtype


Fetcher = Callable[[], Iterable[dict]]


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
    ):
        # Production binding supplies rows already filtered to
        # "currently published" (per §29 join predicate). Each row
        # carries `record_kind` so the adapter can select subtype.
        self._fetch_current = fetch_current
        self._fetch_by_id = fetch_by_id or (lambda _id: None)
        self._blocked_seen: set[str] = set()

    def iter_documents(self) -> Iterator[dict]:
        for row in self._fetch_current():
            kind = (row.get("record_kind") or "").strip()
            if kind in BLOCKED_SUBTYPES:
                self._blocked_seen.add(kind)
                continue
            if kind not in SUPPORTED_SUBTYPES:
                self._blocked_seen.add(kind or "UNKNOWN")
                continue
            payload = _normalize_legal(row)
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
        return _normalize_legal(row)


def _normalize_legal(row: dict) -> Optional[dict]:
    kind = (row.get("record_kind") or "").strip()
    if kind != "law_article":
        return None
    # F2 FINAL §7: canonical_id MUST be the Domain PK
    # (`law_article.id`). `article_internal_key` has ~7,642 distinct
    # values across ~35,412 current-eligible articles and
    # `law_id + article_internal_key` still collides (~33,482 distinct)
    # — so neither is a valid canonical identity. Cross-version
    # semantic continuity is Legal Domain governance, not something
    # Search invents.
    canonical_id = row.get("id")
    if not canonical_id:
        return None
    law_name = row.get("law_name")
    article_no = row.get("article_no")
    article_sub_no = row.get("article_sub_no")
    article_title = row.get("article_title")
    article_text = row.get("article_text")
    # Compose a canonical title such as "산업안전보건법 제12조" or
    # "산업안전보건법 제12조의2 (안전보건관리책임자)". Adapter never
    # invents Korean; it only concatenates real Domain columns.
    if law_name and article_no:
        title_parts = [law_name, f"제{article_no}조"]
        if article_sub_no:
            title_parts[-1] = title_parts[-1] + f"의{article_sub_no}"
        if article_title:
            title_parts.append(f"({article_title})")
        title = " ".join(title_parts)
    else:
        title = article_title or f"law_article/{canonical_id}"
    # F2 FINAL §14: real law_article columns (verified via
    # information_schema on production) are `enforcement_date` +
    # `updated_at`. `published_at` / `version_effective_at` do not
    # exist. Adapter never invents timestamps — if both are absent
    # the row is skipped.
    ts = first_present_iso(
        row.get("enforcement_date"),
        row.get("updated_at"),
    )
    if ts is MISSING_TIMESTAMP:
        return None
    # source_key: NULL rather than a synthetic composite (F2 FINAL §8).
    return {
        "object_type": LegalAdapter.object_type,
        "canonical_id": str(canonical_id),
        "source_id": row.get("source_id") or "LEG_OFFICIAL",
        "source_key": (str(row["source_key"])
                       if row.get("source_key") is not None else None),
        "title": title,
        "summary": None,
        "search_text": " ".join(as_str_list([
            title, article_text,
        ])),
        "aliases": as_str_list([article_no, article_sub_no]),
        "keywords": as_str_list([law_name]),
        "subjects": ([{"subject_type": "LEGAL_TERM",
                        "subject_key": str(law_name)}] if law_name else []),
        "context": [],
        "public_url": None,
        "saas_url": None,
        "publication_status": "PUBLISHED",
        "visibility_scopes": ["PUBLIC", "SAAS", "PAID"],
        "source_updated_at": ts,
    }
