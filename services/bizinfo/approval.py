"""OBJ-BZI-005 — Bizinfo Publication Approval Gate.

Pure functions — no DB, no network, no storage.

Six conditions must ALL be met before a record is eligible for public display:
  1. Industrial-safety relevance confirmed (selector/analyzer verdict)
  2. Official source and origin link verified
  3. Announcement status and last-checked timestamp present
  4. TAI editorial content exists (self-authored, not raw copy)
  5. Source rights confirmed for reuse
  6. Explicit content-approval record exists

Failure of any condition → NOT_ELIGIBLE (not published).
Condition result is a code-level check only — editorial and rights
decisions are made by humans; this module enforces that the records
of those decisions are present before publication is allowed.

RIGHTS_GATE: creating or reading actual approval records from DB
requires separate Owner approval.  Until then, the stub
ApprovalRecord dataclass defines the expected contract.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional

from services.bizinfo.normalizer import NormalizedSourceRecord
from services.bizinfo.status import ChangeRecord, EventStatus, ProgramStatus

# ---------------------------------------------------------------------------
# Approval record contract (STORAGE_GATE boundary)
# ---------------------------------------------------------------------------
# This dataclass defines what an approval record must contain.
# Actual creation and DB persistence require RIGHTS_GATE + STORAGE_GATE.
# Tests and stubs inject instances directly.


@dataclass(frozen=True)
class EditorialContent:
    """TAI-authored content for a bizinfo announcement.

    Must NOT be a copy of the raw API summary.  Must contain at least
    a TAI explanation and practical guidance.
    """
    source_key:   str
    source_kind:  Literal["PROGRAM", "EVENT"]
    explanation:  str    # TAI 자체 해설 (not raw copy of API content)
    guidance:     str    # 사업장이 확인할 실무 사항
    authored_at:  datetime
    # Optional link to related TAI Safe feature (risk assessment, checklist, etc.)
    tai_link:     Optional[str] = None


@dataclass(frozen=True)
class RightsRecord:
    """Confirmation that the source content may be reused.

    기업마당 공공저작물 출처 표시 조건 충족 여부를 나타낸다.
    Actual verification requires RIGHTS_GATE Owner approval.
    """
    source_key:    str
    rights_basis:  str    # e.g. "공공저작물 자유이용허락 (KOGL 제1유형)"
    confirmed_at:  datetime
    confirmed_by:  str    # human reviewer identifier (not email)


@dataclass(frozen=True)
class ContentApprovalRecord:
    """Explicit approval to publish one announcement on the customer site.

    Must be issued by an authorised human reviewer.
    Requires RIGHTS_GATE Owner approval to create.
    """
    source_key:   str
    source_kind:  Literal["PROGRAM", "EVENT"]
    approved_at:  datetime
    approved_by:  str    # human reviewer identifier


# ---------------------------------------------------------------------------
# Eligibility verdict
# ---------------------------------------------------------------------------

EligibilityCode = Literal[
    "ELIGIBLE",           # all 6 conditions met — may be shown to customers
    "NOT_ELIGIBLE",       # one or more conditions failed
]


@dataclass(frozen=True)
class PublicationEligibility:
    """Result of check_publication_eligibility().

    eligible=True only when ALL 6 conditions pass.
    failed_conditions lists the condition codes that did not pass.
    """
    source_key:        str
    source_kind:       Literal["PROGRAM", "EVENT"]
    eligible:          bool
    failed_conditions: tuple[str, ...]   # empty when eligible=True
    checked_at:        datetime


# Condition codes (used in failed_conditions)
COND_RELEVANCE        = "relevance_unconfirmed"   # C-1
COND_SOURCE_LINK      = "source_link_missing"     # C-2
COND_STATUS_PRESENT   = "status_not_present"      # C-3
COND_EDITORIAL        = "editorial_missing"       # C-4
COND_RIGHTS           = "rights_unconfirmed"      # C-5
COND_APPROVAL_RECORD  = "approval_record_missing" # C-6


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def check_publication_eligibility(
    record:          NormalizedSourceRecord,
    status:          ProgramStatus | EventStatus,
    change:          ChangeRecord,
    editorial:       Optional[EditorialContent],
    rights:          Optional[RightsRecord],
    approval:        Optional[ContentApprovalRecord],
    *,
    relevance_verdict: Literal["IN_SCOPE", "OUT_OF_SCOPE", "REVIEW_REQUIRED",
                                "INCLUDE", "EXCLUDE", "HOLD"],
    checked_at:      Optional[datetime] = None,
) -> PublicationEligibility:
    """Evaluate all 6 publication conditions for one announcement.

    relevance_verdict accepts both selector verdicts (IN_SCOPE / OUT_OF_SCOPE /
    REVIEW_REQUIRED) and analyzer verdicts (INCLUDE / EXCLUDE / HOLD).

    Returns PublicationEligibility.  Does NOT publish anything.
    Does NOT create approval records.  Does NOT access DB.
    """
    now = checked_at or record.retrieved_at
    failed: list[str] = []

    # C-1: relevance confirmed by selector or analyzer
    if relevance_verdict not in ("IN_SCOPE", "INCLUDE"):
        failed.append(COND_RELEVANCE)

    # C-2: official source and origin link present
    if not record.bizinfo_url and not record.origin_url:
        failed.append(COND_SOURCE_LINK)

    # C-3: status present and last_checked_at available
    # status.last_checked_at is always set (from retrieved_at)
    # but we also require that at least some date info was available
    if isinstance(status, ProgramStatus):
        if not status.has_dates and status.application_status == "UNKNOWN":
            failed.append(COND_STATUS_PRESENT)
    else:  # EventStatus
        if not status.has_reception_dates and not status.has_event_dates:
            failed.append(COND_STATUS_PRESENT)

    # C-4: TAI editorial content (self-authored, non-empty)
    if editorial is None or not editorial.explanation.strip() or not editorial.guidance.strip():
        failed.append(COND_EDITORIAL)

    # C-5: source rights confirmed
    if rights is None:
        failed.append(COND_RIGHTS)

    # C-6: explicit content approval record
    if approval is None:
        failed.append(COND_APPROVAL_RECORD)

    return PublicationEligibility(
        source_key=record.source_key,
        source_kind=record.source_kind,
        eligible=len(failed) == 0,
        failed_conditions=tuple(failed),
        checked_at=now,
    )
