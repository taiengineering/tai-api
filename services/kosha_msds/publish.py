"""OBJ-CHEM-10 KOSHA MSDS publish promoter (pure logic).

Validates whether a given kosha_msds_snapshot is eligible for promotion
from `publish_state = NOT_PUBLISHED` to `PUBLISHED_FULL`. This module
is fixture-only under WO-CHEM-10: no production DB connection is
opened, no publication is executed. A future execution WO must set
PRODUCTION_PUBLISH_ALLOWED = True to open the write path.

Publication is visibility-only. This module NEVER deletes chemicals,
sections, snapshot_items, or old snapshots (WO §19). Historical
snapshots stay in place; the view kosha_msds_current picks the most
recent PUBLISHED_FULL snapshot by completed_at.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional

from services.kosha_msds.contract import (
    DETAIL_COMPLETE,
    DETAIL_EMPTY_BUT_VALID,
    DETAIL_INCOMPLETE,
    ENUMERATION_FULL_OFFICIAL,
    PUBLISH_NOT_PUBLISHED,
    PUBLISH_PUBLISHED_FULL,
    SNAPSHOT_COMPLETED,
)

# ---------------------------------------------------------------------------
# WO scope gate — the load-bearing safety fence for this WO.
# WO-CHEM-10 forbids ALL production publication. A future execution WO
# flips this to True; there is no CLI flag under this WO that can.
# ---------------------------------------------------------------------------
WO_SCOPE = "WO-CHEM-10-PUBLISH-PROMOTER-001"
PRODUCTION_PUBLISH_ALLOWED = False

# Full-corpus expectations (aligned with CHEM-05 / CHEM-08).
FULL_OFFICIAL_CHEMICAL_COUNT = 20568
FULL_OFFICIAL_SECTION_COUNT = 329088

# Allowed detail_status values on snapshot_items when publishing.
PUBLISHABLE_DETAIL_STATUSES = frozenset({DETAIL_COMPLETE, DETAIL_EMPTY_BUT_VALID})

# ---------------------------------------------------------------------------
# Block reason vocabulary (WO §27)
# ---------------------------------------------------------------------------
BLOCK_SNAPSHOT_NOT_FOUND = "SNAPSHOT_NOT_FOUND"
BLOCK_SNAPSHOT_NOT_COMPLETED = "SNAPSHOT_NOT_COMPLETED"
BLOCK_NOT_FULL_OFFICIAL = "NOT_FULL_OFFICIAL"
BLOCK_ALREADY_PUBLISHED = "ALREADY_PUBLISHED"
BLOCK_EXPECTED_COUNT_MISMATCH = "EXPECTED_COUNT_MISMATCH"
BLOCK_DISCOVERED_COUNT_MISMATCH = "DISCOVERED_COUNT_MISMATCH"
BLOCK_SNAPSHOT_ITEM_COUNT_MISMATCH = "SNAPSHOT_ITEM_COUNT_MISMATCH"
BLOCK_INCOMPLETE_MEMBERSHIP = "INCOMPLETE_MEMBERSHIP"
BLOCK_SECTION_COUNT_MISMATCH = "SECTION_COUNT_MISMATCH"
BLOCK_DUPLICATE_MEMBERSHIP = "DUPLICATE_MEMBERSHIP"
BLOCK_DUPLICATE_SECTION = "DUPLICATE_SECTION"
BLOCK_MATERIALIZE_BINDING_MISMATCH = "MATERIALIZE_BINDING_MISMATCH"
BLOCK_OWNER_AUTHORIZATION_MISSING = "OWNER_AUTHORIZATION_MISSING"
BLOCK_WO_SCOPE_FORBIDS_PUBLICATION = "WO_SCOPE_FORBIDS_PUBLICATION"


class PublicationForbidden(Exception):
    """Any promotion path that reaches production write raises this.

    Under WO-CHEM-10, PRODUCTION_PUBLISH_ALLOWED is False and this is
    the load-bearing safety fence.
    """


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class PublishReport:
    snapshot_id: str
    snapshot_exists: bool
    snapshot_status: Optional[str] = None
    enumeration_mode: Optional[str] = None
    publish_state: Optional[str] = None
    expected_count: Optional[int] = None
    discovered_count: Optional[int] = None
    snapshot_item_count: Optional[int] = None
    incomplete_memberships: int = 0
    section_count: Optional[int] = None
    duplicate_memberships: int = 0
    duplicate_sections: int = 0
    existing_published_snapshot_id: Optional[str] = None
    materialize_binding_mismatch: bool = False
    block_reasons: tuple = field(default_factory=tuple)
    eligible: bool = False

    def to_dict(self) -> dict:
        return {
            "snapshot_id": self.snapshot_id,
            "snapshot_exists": self.snapshot_exists,
            "snapshot_status": self.snapshot_status,
            "enumeration_mode": self.enumeration_mode,
            "publish_state": self.publish_state,
            "expected_count": self.expected_count,
            "discovered_count": self.discovered_count,
            "snapshot_item_count": self.snapshot_item_count,
            "incomplete_memberships": self.incomplete_memberships,
            "section_count": self.section_count,
            "duplicate_memberships": self.duplicate_memberships,
            "duplicate_sections": self.duplicate_sections,
            "existing_published_snapshot_id": self.existing_published_snapshot_id,
            "materialize_binding_mismatch": self.materialize_binding_mismatch,
            "block_reasons": list(self.block_reasons),
            "eligible": self.eligible,
        }


# ---------------------------------------------------------------------------
# Store interface
# ---------------------------------------------------------------------------


class MemoryPublishStore:
    """In-memory fixture store. Read + fixture-only write.

    Even the promote() write method is fixture-only under WO-CHEM-10;
    the module never wires this store against a live DB.
    """

    def __init__(
        self,
        *,
        snapshots: Optional[Iterable[dict]] = None,
        snapshot_items: Optional[Iterable[dict]] = None,
        sections: Optional[Iterable[dict]] = None,
    ):
        self._snapshots: list[dict] = [dict(s) for s in (snapshots or [])]
        self._items: list[dict] = [dict(i) for i in (snapshot_items or [])]
        self._sections: list[dict] = [dict(s) for s in (sections or [])]

    # -- read side --
    def get_snapshot(self, snapshot_id: str) -> Optional[dict]:
        for s in self._snapshots:
            if str(s.get("id")) == str(snapshot_id):
                return dict(s)
        return None

    def snapshot_items(self, snapshot_id: str) -> list[dict]:
        return [
            dict(i) for i in self._items
            if str(i.get("snapshot_id")) == str(snapshot_id)
            and i.get("in_snapshot", True) is True
        ]

    def section_count_for_snapshot(self, snapshot_id: str) -> int:
        """Count of distinct (chemical_id, section_no) rows for the
        chemicals whose UUIDs are in this snapshot's membership."""
        chem_uuids = {str(i.get("chemical_id"))
                      for i in self._items
                      if str(i.get("snapshot_id")) == str(snapshot_id)
                      and i.get("in_snapshot", True) is True}
        pairs = set()
        for row in self._sections:
            cid = str(row.get("chemical_id"))
            if cid not in chem_uuids:
                continue
            pairs.add((cid, int(row.get("section_no"))))
        return len(pairs)

    def duplicate_section_pairs_for_snapshot(self, snapshot_id: str) -> int:
        chem_uuids = {str(i.get("chemical_id"))
                      for i in self._items
                      if str(i.get("snapshot_id")) == str(snapshot_id)}
        seen: dict[tuple[str, int], int] = {}
        for row in self._sections:
            cid = str(row.get("chemical_id"))
            if cid not in chem_uuids:
                continue
            k = (cid, int(row.get("section_no")))
            seen[k] = seen.get(k, 0) + 1
        return sum(1 for c in seen.values() if c > 1)

    def latest_published_snapshot(self) -> Optional[dict]:
        pub = [s for s in self._snapshots
               if s.get("publish_state") == PUBLISH_PUBLISHED_FULL
               and s.get("status") == SNAPSHOT_COMPLETED
               and s.get("enumeration_mode") == ENUMERATION_FULL_OFFICIAL]
        if not pub:
            return None
        pub.sort(key=lambda s: (s.get("completed_at") or "",
                                s.get("started_at") or ""), reverse=True)
        return dict(pub[0])

    # -- fixture-only write side --
    def promote_to_published_full(self, snapshot_id: str) -> None:
        for s in self._snapshots:
            if str(s.get("id")) == str(snapshot_id):
                s["publish_state"] = PUBLISH_PUBLISHED_FULL
                return
        raise KeyError(f"snapshot not found: {snapshot_id}")

    def demote_snapshot(self, snapshot_id: str) -> None:
        """Only used by fixture tests to model rollback."""
        for s in self._snapshots:
            if str(s.get("id")) == str(snapshot_id):
                s["publish_state"] = PUBLISH_NOT_PUBLISHED
                return


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------


def preflight_publish(
    snapshot_id: str,
    *,
    store: MemoryPublishStore,
    expected_materialize_binding: Optional[Mapping[str, Any]] = None,
) -> PublishReport:
    """Read-only preflight over a MemoryPublishStore.

    `expected_materialize_binding` is an optional dict of expected
    metrics_json fields (e.g. {"adapter_version": "CHEM05_V1",
    "materialize_plan_sha256": ..., "responses_sha256": ...}). Any
    mismatch produces BLOCK_MATERIALIZE_BINDING_MISMATCH.
    """
    reasons: list[str] = []
    snap = store.get_snapshot(snapshot_id)
    existing_pub = store.latest_published_snapshot()
    existing_pub_id = str(existing_pub["id"]) if existing_pub else None

    if snap is None:
        reasons.append(BLOCK_SNAPSHOT_NOT_FOUND)
        return PublishReport(
            snapshot_id=snapshot_id,
            snapshot_exists=False,
            existing_published_snapshot_id=existing_pub_id,
            block_reasons=tuple(reasons),
            eligible=False,
        )

    status = snap.get("status")
    enum_mode = snap.get("enumeration_mode")
    publish_state = snap.get("publish_state")
    expected_count = snap.get("expected_count")
    discovered_count = snap.get("discovered_count")

    if status != SNAPSHOT_COMPLETED:
        reasons.append(BLOCK_SNAPSHOT_NOT_COMPLETED)
    if enum_mode != ENUMERATION_FULL_OFFICIAL:
        reasons.append(BLOCK_NOT_FULL_OFFICIAL)
    if publish_state == PUBLISH_PUBLISHED_FULL:
        reasons.append(BLOCK_ALREADY_PUBLISHED)
    if expected_count != FULL_OFFICIAL_CHEMICAL_COUNT:
        reasons.append(BLOCK_EXPECTED_COUNT_MISMATCH)
    if discovered_count != FULL_OFFICIAL_CHEMICAL_COUNT:
        reasons.append(BLOCK_DISCOVERED_COUNT_MISMATCH)

    items = store.snapshot_items(snapshot_id)
    snapshot_item_count = len(items)
    incomplete_memberships = sum(
        1 for i in items
        if i.get("detail_status") not in PUBLISHABLE_DETAIL_STATUSES
        and i.get("detail_status") is not None
    )
    # Membership duplicates: same (snapshot_id, chemical_id) more than once.
    seen: dict[str, int] = {}
    for i in items:
        seen[str(i.get("chemical_id"))] = seen.get(str(i.get("chemical_id")), 0) + 1
    duplicate_memberships = sum(1 for c in seen.values() if c > 1)

    if snapshot_item_count != FULL_OFFICIAL_CHEMICAL_COUNT:
        reasons.append(BLOCK_SNAPSHOT_ITEM_COUNT_MISMATCH)
    if incomplete_memberships > 0:
        reasons.append(BLOCK_INCOMPLETE_MEMBERSHIP)
    if duplicate_memberships > 0:
        reasons.append(BLOCK_DUPLICATE_MEMBERSHIP)

    section_count = store.section_count_for_snapshot(snapshot_id)
    duplicate_sections = store.duplicate_section_pairs_for_snapshot(snapshot_id)
    if section_count != FULL_OFFICIAL_SECTION_COUNT:
        reasons.append(BLOCK_SECTION_COUNT_MISMATCH)
    if duplicate_sections > 0:
        reasons.append(BLOCK_DUPLICATE_SECTION)

    materialize_mismatch = False
    if expected_materialize_binding is not None:
        metrics = (snap.get("metrics_json") or {})
        for k, expected_v in expected_materialize_binding.items():
            if metrics.get(k) != expected_v:
                materialize_mismatch = True
                break
        if materialize_mismatch:
            reasons.append(BLOCK_MATERIALIZE_BINDING_MISMATCH)

    # De-dup preserving order.
    dedup: list[str] = []
    _seen: set[str] = set()
    for r in reasons:
        if r not in _seen:
            _seen.add(r)
            dedup.append(r)

    return PublishReport(
        snapshot_id=snapshot_id,
        snapshot_exists=True,
        snapshot_status=status,
        enumeration_mode=enum_mode,
        publish_state=publish_state,
        expected_count=expected_count,
        discovered_count=discovered_count,
        snapshot_item_count=snapshot_item_count,
        incomplete_memberships=incomplete_memberships,
        section_count=section_count,
        duplicate_memberships=duplicate_memberships,
        duplicate_sections=duplicate_sections,
        existing_published_snapshot_id=existing_pub_id,
        materialize_binding_mismatch=materialize_mismatch,
        block_reasons=tuple(dedup),
        eligible=len(dedup) == 0,
    )


# ---------------------------------------------------------------------------
# Safety fence
# ---------------------------------------------------------------------------


def assert_can_execute_publish(
    *,
    report: PublishReport,
    owner_approved: bool,
    wo_scope_allows_publish: bool = PRODUCTION_PUBLISH_ALLOWED,
) -> None:
    """Three gates in order. Called BEFORE any store mutation.

      Gate A  report.eligible must be True.
      Gate B  owner_approved must be True.
      Gate C  wo_scope_allows_publish must be True.

    Under WO-CHEM-10, Gate C is hard-wired False. A separate future
    execution WO must flip PRODUCTION_PUBLISH_ALLOWED.
    """
    if not report.eligible:
        raise PublicationForbidden(
            f"preflight blocked: {list(report.block_reasons) or ['<unknown>']}"
        )
    if not owner_approved:
        raise PublicationForbidden(
            f"{BLOCK_OWNER_AUTHORIZATION_MISSING}: owner_approved=False"
        )
    if not wo_scope_allows_publish:
        raise PublicationForbidden(
            f"{BLOCK_WO_SCOPE_FORBIDS_PUBLICATION}: {WO_SCOPE} does not allow "
            f"production publication. A future execution WO must set "
            f"PRODUCTION_PUBLISH_ALLOWED=True."
        )


# ---------------------------------------------------------------------------
# Promotion (fixture-only under WO-CHEM-10)
# ---------------------------------------------------------------------------


def promote_to_published_full(
    snapshot_id: str,
    *,
    store: MemoryPublishStore,
    owner_approved: bool,
    expected_materialize_binding: Optional[Mapping[str, Any]] = None,
    wo_scope_allows_publish: bool = PRODUCTION_PUBLISH_ALLOWED,
) -> PublishReport:
    """Attempt to promote a snapshot to PUBLISHED_FULL.

    Under WO-CHEM-10 the third gate refuses, so this function ONLY
    mutates a store when `wo_scope_allows_publish=True` is passed
    explicitly (used by fixture tests to model a successful promotion).
    In production this parameter is not overridden; only the future
    execution WO flips the module-level constant.
    """
    report = preflight_publish(
        snapshot_id, store=store,
        expected_materialize_binding=expected_materialize_binding,
    )
    assert_can_execute_publish(
        report=report,
        owner_approved=owner_approved,
        wo_scope_allows_publish=wo_scope_allows_publish,
    )
    # Atomic transition: single-field update on the target snapshot.
    # Historical snapshots stay untouched (WO §19).
    # The DB-side atomicity is one UPDATE; kosha_msds_current's
    # ORDER BY completed_at picks the newest PUBLISHED_FULL, so the
    # switch is instantaneous from the view's perspective (WO §17).
    prior_state = None
    snap = store.get_snapshot(snapshot_id)
    if snap is not None:
        prior_state = snap.get("publish_state")
    try:
        store.promote_to_published_full(snapshot_id)
    except Exception:
        # Rollback the fixture-side write attempt if it partially
        # succeeded. The read/write helpers on MemoryPublishStore are
        # single-field so this is a no-op in practice; kept for
        # symmetry with a future Supabase adapter.
        if prior_state is not None and snap is not None:
            store.demote_snapshot(snapshot_id)
        raise
    # Re-read the post-state to include in the returned report.
    post = store.get_snapshot(snapshot_id) or {}
    return PublishReport(
        snapshot_id=snapshot_id,
        snapshot_exists=True,
        snapshot_status=post.get("status"),
        enumeration_mode=post.get("enumeration_mode"),
        publish_state=post.get("publish_state"),
        expected_count=post.get("expected_count"),
        discovered_count=post.get("discovered_count"),
        snapshot_item_count=report.snapshot_item_count,
        incomplete_memberships=report.incomplete_memberships,
        section_count=report.section_count,
        duplicate_memberships=report.duplicate_memberships,
        duplicate_sections=report.duplicate_sections,
        existing_published_snapshot_id=report.existing_published_snapshot_id,
        materialize_binding_mismatch=report.materialize_binding_mismatch,
        block_reasons=(),
        eligible=True,
    )


# ---------------------------------------------------------------------------
# Dry-run helper (never mutates, never opens a live DB)
# ---------------------------------------------------------------------------


def dry_run(
    snapshot_id: str,
    *,
    store: MemoryPublishStore,
    expected_materialize_binding: Optional[Mapping[str, Any]] = None,
    owner_approved: bool = False,
) -> dict:
    report = preflight_publish(
        snapshot_id, store=store,
        expected_materialize_binding=expected_materialize_binding,
    )
    return {
        "wo_scope": WO_SCOPE,
        "production_publish_allowed": PRODUCTION_PUBLISH_ALLOWED,
        "owner_approved": bool(owner_approved),
        "report": report.to_dict(),
    }
