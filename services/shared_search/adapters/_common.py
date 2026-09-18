"""Shared helpers for Domain adapters.

WO-TAI-SHARED-SEARCH-F2. Any helper that TWO adapters need lives
here (per the shared-use modularization rule).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Iterable, Iterator


MISSING_TIMESTAMP = object()   # sentinel for "no authoritative timestamp"


def coerce_iso(value: Any) -> Any:
    """Coerce a Domain timestamp value into an ISO 8601 string.

    Returns:
        - ISO 8601 str if the input carries a valid timestamp
        - `MISSING_TIMESTAMP` sentinel when no authoritative
          timestamp is available. Adapters MUST NOT hide the miss
          behind an epoch — Foundation §34 forbids fake epoch dates.
          Callers should skip the row or classify it in a census.

    WO-TAI-SHARED-SEARCH-F2 CO §34: previously this helper returned
    `1970-01-01T00:00:00+00:00` whenever the source lacked a
    timestamp. That masked real Domain-side data quality issues.
    Adapters now surface the missing case explicitly.
    """
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str) and value.strip():
        return value.strip()
    return MISSING_TIMESTAMP


def first_present_iso(*candidates: Any) -> Any:
    """Return the first non-empty ISO timestamp among candidates,
    or `MISSING_TIMESTAMP` if none exist. Used by adapters that have
    multiple candidate timestamp columns (e.g. GUIDE `regist_date`
    then snapshot `completed_at`)."""
    for c in candidates:
        result = coerce_iso(c)
        if result is not MISSING_TIMESTAMP:
            return result
    return MISSING_TIMESTAMP


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
