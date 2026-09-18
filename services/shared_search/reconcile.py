"""Nightly reconciliation — READ-only Domain SoT ↔ current projection.

WO-TAI-SHARED-SEARCH-F1. Contract source:
- Document Contract §11.3 (NIGHTLY RECONCILIATION)
- §11 requires that reconcile NEVER mutates state.

The reconciler compares a Domain adapter's declared "expected PUBLISHED
rows" against what the current Shared Search projection contains and
reports 4 discrete outcomes: MATCH / MISSING / EXTRA / STALE_HASH.

The Domain SoT feed is provided by the caller (F2 adapter). No
Domain-side query is issued from this module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Optional

from services.shared_search.writer import MemoryStore


@dataclass
class ReconcileReport:
    object_type: str
    expected_count: int = 0
    current_count: int = 0
    match: int = 0
    missing: tuple = ()          # canonical_ids in SoT but not current
    extra: tuple = ()            # canonical_ids in current but not SoT
    stale_by_hash: tuple = ()    # canonical_ids present both sides but content_hash differs
    ok: bool = False

    def to_dict(self) -> dict:
        return {
            "object_type": self.object_type,
            "expected_count": self.expected_count,
            "current_count": self.current_count,
            "match": self.match,
            "missing": list(self.missing),
            "extra": list(self.extra),
            "stale_by_hash": list(self.stale_by_hash),
            "ok": self.ok,
        }


def reconcile(
    store: MemoryStore,
    object_type: str,
    expected: Iterable[Mapping[str, str]],
) -> ReconcileReport:
    """Compare `expected` (Domain SoT declaration) against the
    current projection for `object_type`.

    `expected` is an iterable of dicts with at least:
        canonical_id: str
        content_hash: str

    Reconcile is strictly READ-only — does not touch `store`.
    """
    expected_index: dict[str, str] = {}
    for row in expected:
        cid = row.get("canonical_id")
        if not cid:
            continue
        h = row.get("content_hash")
        if h is None:
            raise ValueError("expected row missing content_hash")
        expected_index[cid] = h

    current_index: dict[str, str] = {}
    for row in store.iter_current(object_type=object_type):
        current_index[row["canonical_id"]] = row["content_hash"]

    expected_ids = set(expected_index)
    current_ids = set(current_index)

    missing = sorted(expected_ids - current_ids)
    extra = sorted(current_ids - expected_ids)

    stale: list[str] = []
    match = 0
    for cid in sorted(expected_ids & current_ids):
        if expected_index[cid] != current_index[cid]:
            stale.append(cid)
        else:
            match += 1

    report = ReconcileReport(
        object_type=object_type,
        expected_count=len(expected_index),
        current_count=len(current_index),
        match=match,
        missing=tuple(missing),
        extra=tuple(extra),
        stale_by_hash=tuple(stale),
    )
    report.ok = (
        not report.missing
        and not report.extra
        and not report.stale_by_hash
    )
    return report
