"""OBJ-BZI-006 — Bizinfo Public API Router.

WO-TAI-BIZINFO-STAGE-B-INTEGRATED-IMPLEMENTATION-001

Prefix: /public/bizinfo

NOT registered in router_registry (STORAGE_GATE + RIGHTS_GATE pending).
Router is intentionally dormant following the kosha_public_msds pattern.

Activation requires:
  1. STORAGE_GATE Owner approval (DB tables + migration)
  2. RIGHTS_GATE Owner approval (content publication)
  3. Explicit router registration in router_registry/public.py

In development / local integration tests, inject a repository instance
directly via the dependency override mechanism.

Endpoints:
  GET /public/bizinfo/programs          — 지원사업 목록 (승인된 항목만)
  GET /public/bizinfo/programs/{key}    — 지원사업 상세
  GET /public/bizinfo/events            — 안전행사 목록 (승인된 항목만)
  GET /public/bizinfo/events/{key}      — 안전행사 상세

All responses include only content that has passed all 6 approval
conditions.  Content that has not been approved is never returned.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from services.bizinfo.approval import (
    ContentApprovalRecord,
    EditorialContent,
    PublicationEligibility,
    RightsRecord,
    check_publication_eligibility,
)
from services.bizinfo.normalizer import NormalizedSourceRecord
from services.bizinfo.repository import BizinfoRepository, InMemoryBizinfoRepository
from services.bizinfo.status import (
    ChangeRecord,
    EventStatus,
    ProgramStatus,
    detect_change,
    event_status,
    program_status,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/public/bizinfo",
    tags=["Bizinfo public"],
)

# ---------------------------------------------------------------------------
# Dependency injection — repository
# ---------------------------------------------------------------------------

_repo: Optional[BizinfoRepository] = None


def get_repository() -> BizinfoRepository:
    """Return the active repository.

    In tests: override via app.dependency_overrides[get_repository] = lambda: stub.
    In production: requires STORAGE_GATE approval before wiring a real repo.
    """
    if _repo is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "BIZINFO_STORAGE_GATE_PENDING",
                "message": "기업마당 콘텐츠 저장소가 아직 활성화되지 않았습니다.",
            },
        )
    return _repo


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ProgramListItem(BaseModel):
    source_key:         str
    title:              str
    source_org:         Optional[str]
    application_status: str
    application_start:  Optional[str]   # ISO date string or None
    application_end:    Optional[str]
    last_checked_at:    str             # ISO datetime string
    bizinfo_url:        Optional[str]


class ProgramDetail(ProgramListItem):
    origin_url:         Optional[str]
    support_target:     Optional[str]
    explanation:        str    # TAI editorial
    guidance:           str    # 실무 사항
    tai_link:           Optional[str]
    source_updated_at:  Optional[str]


class EventListItem(BaseModel):
    source_key:         str
    title:              str
    source_org:         Optional[str]
    reception_status:   str
    progress_status:    str
    event_start:        Optional[str]
    event_end:          Optional[str]
    reception_start:    Optional[str]
    reception_end:      Optional[str]
    last_checked_at:    str
    bizinfo_url:        Optional[str]


class EventDetail(EventListItem):
    origin_url:         Optional[str]
    support_target:     Optional[str]
    explanation:        str
    guidance:           str
    tai_link:           Optional[str]
    source_updated_at:  Optional[str]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _iso(dt: Any) -> Optional[str]:
    if dt is None:
        return None
    if hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt)


def _approved_program(
    source_key: str,
    repo: BizinfoRepository,
) -> Optional[tuple[NormalizedSourceRecord, ProgramStatus, EditorialContent]]:
    """Return (record, status, editorial) only if all 6 conditions pass."""
    record   = repo.get_prior_record("PROGRAM", source_key)
    if record is None:
        return None
    editorial = repo.get_editorial("PROGRAM", source_key)
    rights    = repo.get_rights("PROGRAM", source_key)
    approval  = repo.get_approval("PROGRAM", source_key)

    # Identity validation — ensure retrieved records belong to this announcement
    if editorial is not None and (editorial.source_key != source_key or editorial.source_kind != "PROGRAM"):
        editorial = None
    if rights is not None and rights.source_key != source_key:
        rights = None
    if approval is not None and (approval.source_key != source_key or approval.source_kind != "PROGRAM"):
        approval = None

    relevance = repo.get_relevance_verdict("PROGRAM", source_key) or "REVIEW_REQUIRED"
    pstatus   = program_status(record)
    change    = ChangeRecord(
        source_key=source_key,
        source_kind="PROGRAM",
        verdict="CHANGE_UNKNOWN",
        changed_fields=(),
        checked_at=record.retrieved_at,
        source_updated_at=record.source_updated_at,
    )
    eligibility = check_publication_eligibility(
        record, pstatus, change, editorial, rights, approval,
        relevance_verdict=relevance,
    )
    if not eligibility.eligible:
        return None
    assert editorial is not None  # guaranteed by eligibility check
    return record, pstatus, editorial


def _approved_event(
    source_key: str,
    repo: BizinfoRepository,
) -> Optional[tuple[NormalizedSourceRecord, EventStatus, EditorialContent]]:
    record    = repo.get_prior_record("EVENT", source_key)
    if record is None:
        return None
    editorial = repo.get_editorial("EVENT", source_key)
    rights    = repo.get_rights("EVENT", source_key)
    approval  = repo.get_approval("EVENT", source_key)

    # Identity validation — ensure retrieved records belong to this announcement
    if editorial is not None and (editorial.source_key != source_key or editorial.source_kind != "EVENT"):
        editorial = None
    if rights is not None and rights.source_key != source_key:
        rights = None
    if approval is not None and (approval.source_key != source_key or approval.source_kind != "EVENT"):
        approval = None

    relevance = repo.get_relevance_verdict("EVENT", source_key) or "REVIEW_REQUIRED"
    estatus   = event_status(record)
    change    = ChangeRecord(
        source_key=source_key,
        source_kind="EVENT",
        verdict="CHANGE_UNKNOWN",
        changed_fields=(),
        checked_at=record.retrieved_at,
        source_updated_at=record.source_updated_at,
    )
    eligibility = check_publication_eligibility(
        record, estatus, change, editorial, rights, approval,
        relevance_verdict=relevance,
    )
    if not eligibility.eligible:
        return None
    assert editorial is not None
    return record, estatus, editorial


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/programs", response_model=list[ProgramListItem])
def list_programs(
    limit:  int = Query(20, ge=1, le=100),
    offset: int = Query(0,  ge=0),
    repo:   BizinfoRepository = Depends(get_repository),
) -> list[ProgramListItem]:
    """Return approved 지원사업 announcements only."""
    keys    = repo.list_eligible_keys("PROGRAM", limit=limit, offset=offset)
    results = []
    for key in keys:
        item = _approved_program(key, repo)
        if item is None:
            continue
        record, status, _ = item
        ap = record.application_period
        results.append(ProgramListItem(
            source_key=record.source_key,
            title=record.title,
            source_org=record.source_org,
            application_status=status.application_status,
            application_start=_iso(ap.start if ap else None),
            application_end=_iso(ap.end if ap else None),
            last_checked_at=_iso(status.last_checked_at),
            bizinfo_url=record.bizinfo_url,
        ))
    return results


@router.get("/programs/{source_key}", response_model=ProgramDetail)
def get_program(
    source_key: str,
    repo: BizinfoRepository = Depends(get_repository),
) -> ProgramDetail:
    """Return one approved 지원사업 announcement detail."""
    item = _approved_program(source_key, repo)
    if item is None:
        raise HTTPException(status_code=404, detail="공고를 찾을 수 없습니다.")
    record, status, editorial = item
    ap = record.application_period
    return ProgramDetail(
        source_key=record.source_key,
        title=record.title,
        source_org=record.source_org,
        application_status=status.application_status,
        application_start=_iso(ap.start if ap else None),
        application_end=_iso(ap.end if ap else None),
        last_checked_at=_iso(status.last_checked_at),
        bizinfo_url=record.bizinfo_url,
        origin_url=record.origin_url,
        support_target=record.support_target,
        explanation=editorial.explanation,
        guidance=editorial.guidance,
        tai_link=editorial.tai_link,
        source_updated_at=_iso(record.source_updated_at),
    )


@router.get("/events", response_model=list[EventListItem])
def list_events(
    limit:  int = Query(20, ge=1, le=100),
    offset: int = Query(0,  ge=0),
    repo:   BizinfoRepository = Depends(get_repository),
) -> list[EventListItem]:
    """Return approved 안전행사 announcements only."""
    keys    = repo.list_eligible_keys("EVENT", limit=limit, offset=offset)
    results = []
    for key in keys:
        item = _approved_event(key, repo)
        if item is None:
            continue
        record, status, _ = item
        ep = record.event_period
        rp = record.reception_period
        results.append(EventListItem(
            source_key=record.source_key,
            title=record.title,
            source_org=record.source_org,
            reception_status=status.reception_status,
            progress_status=status.progress_status,
            event_start=_iso(ep.start if ep else None),
            event_end=_iso(ep.end if ep else None),
            reception_start=_iso(rp.start if rp else None),
            reception_end=_iso(rp.end if rp else None),
            last_checked_at=_iso(status.last_checked_at),
            bizinfo_url=record.bizinfo_url,
        ))
    return results


@router.get("/events/{source_key}", response_model=EventDetail)
def get_event(
    source_key: str,
    repo: BizinfoRepository = Depends(get_repository),
) -> EventDetail:
    """Return one approved 안전행사 announcement detail."""
    item = _approved_event(source_key, repo)
    if item is None:
        raise HTTPException(status_code=404, detail="행사를 찾을 수 없습니다.")
    record, status, editorial = item
    ep = record.event_period
    rp = record.reception_period
    return EventDetail(
        source_key=record.source_key,
        title=record.title,
        source_org=record.source_org,
        reception_status=status.reception_status,
        progress_status=status.progress_status,
        event_start=_iso(ep.start if ep else None),
        event_end=_iso(ep.end if ep else None),
        reception_start=_iso(rp.start if rp else None),
        reception_end=_iso(rp.end if rp else None),
        last_checked_at=_iso(status.last_checked_at),
        bizinfo_url=record.bizinfo_url,
        origin_url=record.origin_url,
        support_target=record.support_target,
        explanation=editorial.explanation,
        guidance=editorial.guidance,
        tai_link=editorial.tai_link,
        source_updated_at=_iso(record.source_updated_at),
    )
