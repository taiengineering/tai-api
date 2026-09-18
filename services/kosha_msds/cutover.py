"""OBJ-CHEM-FULL-READINESS-002 cutover-readiness composer.

Thin orchestration over the existing CHEM-10 publish preflight
(`services.kosha_msds.publish.preflight_publish`) and the existing
public-mode router (`routers.kosha_public_msds`).

This module does NOT introduce a new eligibility engine — the
canonical readiness check is `preflight_publish(scope=FULL)`. The
helper here just packages the "is this snapshot ready to become
PUBLISHED_FULL?" question as a single call so tests and future
execution WOs can consult one shape.

No live DB. No production publish. No env mutation. No new schema.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from services.kosha_msds.contract import (
    PUBLIC_MODE_FULL,
    PUBLIC_MODE_OFF,
    PUBLIC_MODE_SEO_PREVIEW,
    PUBLICATION_SCOPE_FULL,
    PUBLICATION_SCOPE_SEO_PREVIEW,
)
from services.kosha_msds.publish import preflight_publish


@dataclass(frozen=True)
class FullReadyReport:
    """Compact summary of whether a snapshot is ready to become
    PUBLISHED_FULL. Wraps the underlying CHEM-10 PublishReport."""
    snapshot_id: str
    ready: bool
    block_reasons: tuple
    expected_count: Optional[int]
    discovered_count: Optional[int]
    snapshot_item_count: Optional[int]
    section_count: Optional[int]
    incomplete_memberships: int
    duplicate_memberships: int
    duplicate_sections: int
    materialize_binding_mismatch: bool

    def to_dict(self) -> dict:
        return {
            "snapshot_id": self.snapshot_id,
            "ready": self.ready,
            "block_reasons": list(self.block_reasons),
            "expected_count": self.expected_count,
            "discovered_count": self.discovered_count,
            "snapshot_item_count": self.snapshot_item_count,
            "section_count": self.section_count,
            "incomplete_memberships": self.incomplete_memberships,
            "duplicate_memberships": self.duplicate_memberships,
            "duplicate_sections": self.duplicate_sections,
            "materialize_binding_mismatch": self.materialize_binding_mismatch,
        }


def is_full_ready(
    snapshot_id: str,
    *,
    store,
    expected_materialize_binding: Optional[Mapping[str, Any]] = None,
) -> FullReadyReport:
    """Canonical readiness check for the PUBLISHED_FULL cutover.

    Delegates to `services.kosha_msds.publish.preflight_publish` with
    `publication_scope=FULL`. Returns a FullReadyReport wrapper that
    surfaces the answer without exposing the full PublishReport
    surface — tests and CLIs can consult a single boolean and the
    canonical block-reason vocabulary. Zero DB mutation.
    """
    report = preflight_publish(
        snapshot_id,
        store=store,
        publication_scope=PUBLICATION_SCOPE_FULL,
        expected_materialize_binding=expected_materialize_binding,
    )
    return FullReadyReport(
        snapshot_id=snapshot_id,
        ready=report.eligible,
        block_reasons=report.block_reasons,
        expected_count=report.expected_count,
        discovered_count=report.discovered_count,
        snapshot_item_count=report.snapshot_item_count,
        section_count=report.section_count,
        incomplete_memberships=report.incomplete_memberships,
        duplicate_memberships=report.duplicate_memberships,
        duplicate_sections=report.duplicate_sections,
        materialize_binding_mismatch=report.materialize_binding_mismatch,
    )


# ---------------------------------------------------------------------------
# Rollback contract (documentation constants; NOT a runtime demote helper).
#
# WO-CHEM-FULL-READINESS-002 §5 / §9:
#   L1  public mode flip: KOSHA_MSDS_PUBLIC_MODE=full → seo_preview
#       This is the ONLY rollback path this WO covers. It changes
#       the router's read pointer, not any DB state.
#
#   L2  publication-state demote (would flip a snapshot's publish_state
#       away from PUBLISHED_FULL) is EXPLICITLY out of scope. A future
#       owner-approved WO handles that after L1 has bought time for
#       incident analysis.
#
# There is deliberately no code path in this module that mutates a
# publication row. That's the whole point of §5 — rollback is a public
# read-pointer change, so demotes never race against pending traffic.
# ---------------------------------------------------------------------------

L1_ROLLBACK_ACTION = "public mode flip: KOSHA_MSDS_PUBLIC_MODE=full → seo_preview"
L2_ROLLBACK_ACTION = "publication-state demote (out of scope for this WO)"

L1_ROLLBACK_MUTATES_DB = False
L2_ROLLBACK_AUTHORIZED_UNDER_THIS_WO = False


def rollback_contract() -> dict:
    """Return the frozen rollback contract as a data object for tests /
    receipts. This is documentation — it does not perform any rollback.
    Calling a runtime helper for L2 requires a separate owner-approved
    execution WO."""
    return {
        "l1": {
            "action": L1_ROLLBACK_ACTION,
            "mutates_db": L1_ROLLBACK_MUTATES_DB,
            "authorized_here": True,
            "from_mode": PUBLIC_MODE_FULL,
            "to_mode": PUBLIC_MODE_SEO_PREVIEW,
        },
        "l2": {
            "action": L2_ROLLBACK_ACTION,
            "mutates_db": True,
            "authorized_here": L2_ROLLBACK_AUTHORIZED_UNDER_THIS_WO,
            "reason": (
                "DELETE / TRUNCATE / demote publish_state stays out of "
                "scope; L1 preserves both the FULL snapshot as evidence "
                "and the SEO preview snapshot as continued serving."
            ),
        },
        "off_failsafe": {
            "action": "unknown / misconfigured env → route as PUBLIC_MODE_OFF",
            "response": "HTTP 503 MSDS_PUBLIC_DORMANT",
            "mutates_db": False,
        },
    }
