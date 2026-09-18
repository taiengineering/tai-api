"""Shared helpers for Domain adapters.

WO-TAI-SHARED-SEARCH-F2. Any helper that TWO adapters need lives
here (per the shared-use modularization rule).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Iterable, Iterator


def coerce_iso(value: Any) -> str:
    """Coerce a Domain timestamp value into an ISO 8601 string.

    Domain adapters normalize timestamps at the boundary so the
    Common Writer sees a uniform shape. Falls back to the epoch if
    no meaningful timestamp is available — the writer requires
    source_updated_at to be present.
    """
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str) and value:
        return value
    # Domain rows that don't carry a timestamp use the epoch marker.
    # Reconciliation still functions; freshness scoring in F3 can
    # de-weight these if it wants.
    return "1970-01-01T00:00:00+00:00"


def as_str_list(values: Iterable[Any]) -> list[str]:
    """Filter to non-empty strings; used before handing lists to the
    normalizer's `_canonical_str_list`."""
    out: list[str] = []
    if not values:
        return out
    for v in values:
        if v is None:
            continue
        if isinstance(v, str):
            v = v.strip()
            if v:
                out.append(v)
    return out


def expected_hashes_from_documents(
    iter_documents: Callable[[], Iterable[dict]],
) -> Iterator[dict]:
    """Recompute {canonical_id, content_hash} for every payload the
    adapter's `iter_documents` yields.

    Every Domain adapter's reconciliation feed follows the same
    shape — normalize then hash. Rather than repeat the loop in each
    of the 7 adapters (which would violate the shared-use rule),
    they all call this helper.
    """
    # Local imports to avoid a top-level circular dep with document.py
    # (document.py is used by many other modules too).
    from services.shared_search.document import normalize_document
    from services.shared_search.hash_utils import content_hash
    for payload in iter_documents():
        try:
            doc = normalize_document(payload)
        except Exception:
            # A payload the writer would reject cannot participate in
            # reconciliation either; skip.
            continue
        yield {
            "canonical_id": doc.canonical_id,
            "content_hash": content_hash(doc),
        }
