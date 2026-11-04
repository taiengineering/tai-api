"""OBJ-BZI-004 — Bizinfo Announcement Status.

Pure functions — no DB, no network, no storage.

PROGRAM and EVENT have distinct status models:
  PROGRAM: application period relative to today
  EVENT:   two independent axes — reception status + event progress status

Change detection compares two NormalizedSourceRecord snapshots.
First observation (no prior snapshot) is explicitly represented as
CHANGE_UNKNOWN rather than fabricated.

API fetch failure is NOT treated as cancellation or expiry.
Missing dates → UNKNOWN status (never inferred from absence).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Literal, Optional

from services.bizinfo.normalizer import DateRange, NormalizedSourceRecord

# ---------------------------------------------------------------------------
# PROGRAM status
# ---------------------------------------------------------------------------

ProgramApplicationStatus = Literal[
    "UPCOMING",          # 접수 예정 — start date in the future
    "OPEN",              # 접수 중
    "CLOSED",            # 접수 마감 — end date passed
    "CANCELLED",         # 공식 근거 있는 취소·예산소진 (source field 기반)
    "UNKNOWN",           # 날짜 없음 / 불명확
]

# ---------------------------------------------------------------------------
# EVENT status (two axes)
# ---------------------------------------------------------------------------

EventReceptionStatus = Literal[
    "UPCOMING",          # 신청 예정
    "OPEN",              # 접수 중
    "CLOSED",            # 접수 마감
    "UNKNOWN",
]

EventProgressStatus = Literal[
    "UPCOMING",          # 행사 예정
    "ONGOING",           # 진행 중
    "ENDED",             # 종료
    "UNKNOWN",
]

# ---------------------------------------------------------------------------
# Change detection
# ---------------------------------------------------------------------------

ChangeVerdict = Literal[
    "CHANGED",           # detectable field difference between snapshots
    "UNCHANGED",         # no detectable difference
    "CHANGE_UNKNOWN",    # no prior snapshot — cannot determine
]

# ---------------------------------------------------------------------------
# Public contracts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProgramStatus:
    """State of one PROGRAM announcement at a point in time."""
    source_key:          str
    application_status:  ProgramApplicationStatus
    last_checked_at:     datetime
    source_updated_at:   Optional[datetime]
    # Whether application start/end dates were available for status derivation
    has_dates:           bool


@dataclass(frozen=True)
class EventStatus:
    """State of one EVENT announcement at a point in time (two axes)."""
    source_key:          str
    reception_status:    EventReceptionStatus
    progress_status:     EventProgressStatus
    last_checked_at:     datetime
    source_updated_at:   Optional[datetime]
    has_reception_dates: bool
    has_event_dates:     bool


@dataclass(frozen=True)
class ChangeRecord:
    """Result of comparing two snapshots of the same announcement."""
    source_key:   str
    source_kind:  Literal["PROGRAM", "EVENT"]
    verdict:      ChangeVerdict
    changed_fields: tuple[str, ...]  # empty when UNCHANGED or CHANGE_UNKNOWN
    # Timestamps from the *newer* snapshot
    checked_at:   datetime
    source_updated_at: Optional[datetime]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _today_utc() -> date:
    return datetime.now(tz=timezone.utc).date()


def _date_status(
    dr: Optional[DateRange],
    today: date,
) -> Literal["UPCOMING", "OPEN", "CLOSED", "UNKNOWN"]:
    if dr is None:
        return "UNKNOWN"
    start = dr.start
    end   = dr.end
    if start is None and end is None:
        return "UNKNOWN"
    if end is not None and today > end:
        return "CLOSED"
    if start is not None and today < start:
        return "UPCOMING"
    # OPEN only when both dates bracket today — missing end date is not proof of ongoing
    if start is not None and end is not None and start <= today <= end:
        return "OPEN"
    return "UNKNOWN"


def _comparable_fields(rec: NormalizedSourceRecord) -> dict:
    """Extract fields used for change comparison."""
    return {
        "title":             rec.title,
        "source_org":        rec.source_org,
        "origin_url":        rec.origin_url,
        "bizinfo_url":       rec.bizinfo_url,
        "summary":           rec.summary,
        "support_target":    rec.support_target,
        "hashtags":          tuple(sorted(rec.hashtags)),
        "source_updated_at": rec.source_updated_at,
        # Date range fields
        "app_start": rec.application_period.start if rec.application_period else None,
        "app_end":   rec.application_period.end   if rec.application_period else None,
        "evt_start": rec.event_period.start       if rec.event_period       else None,
        "evt_end":   rec.event_period.end         if rec.event_period       else None,
        "rcp_start": rec.reception_period.start   if rec.reception_period   else None,
        "rcp_end":   rec.reception_period.end     if rec.reception_period   else None,
    }


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def program_status(
    record: NormalizedSourceRecord,
    *,
    as_of: Optional[date] = None,
) -> ProgramStatus:
    """Derive PROGRAM application status from NormalizedSourceRecord.

    as_of defaults to today (UTC).  Pass a fixed date in tests.
    API fetch failure must NOT be passed here — only records from
    successful fetches qualify.
    """
    today = as_of or _today_utc()
    dr    = record.application_period
    status: ProgramApplicationStatus = _date_status(dr, today)  # type: ignore[assignment]

    return ProgramStatus(
        source_key=record.source_key,
        application_status=status,
        last_checked_at=record.retrieved_at,
        source_updated_at=record.source_updated_at,
        has_dates=dr is not None and (dr.start is not None or dr.end is not None),
    )


def event_status(
    record: NormalizedSourceRecord,
    *,
    as_of: Optional[date] = None,
) -> EventStatus:
    """Derive EVENT reception + progress status from NormalizedSourceRecord.

    Two independent axes:
      reception_status — based on reception_period
      progress_status  — based on event_period
    """
    today = as_of or _today_utc()

    rcp_raw = _date_status(record.reception_period, today)
    evt_raw = _date_status(record.event_period,     today)

    reception: EventReceptionStatus = rcp_raw  # type: ignore[assignment]
    # Map OPEN → ONGOING for event progress axis
    progress: EventProgressStatus = "ONGOING" if evt_raw == "OPEN" else evt_raw  # type: ignore[assignment]

    rp = record.reception_period
    ep = record.event_period

    return EventStatus(
        source_key=record.source_key,
        reception_status=reception,
        progress_status=progress,
        last_checked_at=record.retrieved_at,
        source_updated_at=record.source_updated_at,
        has_reception_dates=rp is not None and (rp.start is not None or rp.end is not None),
        has_event_dates=ep is not None and (ep.start is not None or ep.end is not None),
    )


def detect_change(
    prior: Optional[NormalizedSourceRecord],
    current: NormalizedSourceRecord,
) -> ChangeRecord:
    """Compare two snapshots of the same announcement.

    prior=None means first observation — returns CHANGE_UNKNOWN.
    Does not modify either record.
    """
    kind = current.source_kind
    key  = current.source_key

    if prior is None:
        return ChangeRecord(
            source_key=key,
            source_kind=kind,
            verdict="CHANGE_UNKNOWN",
            changed_fields=(),
            checked_at=current.retrieved_at,
            source_updated_at=current.source_updated_at,
        )

    prior_fields   = _comparable_fields(prior)
    current_fields = _comparable_fields(current)

    changed = tuple(
        f for f in prior_fields
        if prior_fields[f] != current_fields.get(f)
    )

    return ChangeRecord(
        source_key=key,
        source_kind=kind,
        verdict="CHANGED" if changed else "UNCHANGED",
        changed_fields=changed,
        checked_at=current.retrieved_at,
        source_updated_at=current.source_updated_at,
    )
