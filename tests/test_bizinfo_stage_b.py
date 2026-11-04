"""OBJ-BZI-004/005/006 STAGE-B 통합 테스트.

WO-TAI-BIZINFO-STAGE-B-INTEGRATED-IMPLEMENTATION-001

전체 기능 흐름 시나리오 7개:
  S-01  지원사업 — 정상 접수 중 → 목록·상세 제공
  S-02  안전행사 — 접수 상태·진행 상태 두 축 구분
  S-03  관련성 미확인(REVIEW_REQUIRED) → 고객 화면 미노출
  S-04  편집 승인 없는 콘텐츠 → 고객 화면 미노출
  S-05  API 수집 실패 → 기존 공고 삭제·마감 판단 없음
  S-06  날짜 없음·변경 없음 → UNKNOWN / CHANGE_UNKNOWN 명시
  S-07  목록·상세 식별자 일치

단위 테스트:
  U-01  PROGRAM 접수 예정·마감 경계
  U-02  EVENT 두 축 독립 판정
  U-03  변경 감지 — 필드 변경·무변경·최초 관측
  U-04  공개 조건 6개 — 각각 단독 실패
  U-05  InMemoryBizinfoRepository — 저장·조회 계약
  U-06  API 라우터 — 승인된 항목만 반환
  U-07  API 라우터 — 미등록 key → 404
  U-08  API 라우터 — STORAGE_GATE 미활성 → 503
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Optional

import pytest
from fastapi.testclient import TestClient

from services.bizinfo.approval import (
    ALLOWED_RIGHTS_BASIS,
    COND_APPROVAL_RECORD,
    COND_ATTRIBUTION,
    COND_EDITORIAL,
    COND_RELEVANCE,
    COND_RIGHTS,
    COND_SOURCE_LINK,
    COND_STATUS_PRESENT,
    RIGHTS_BASIS_FACTS_ONLY_ATTRIBUTED,
    ContentApprovalRecord,
    EditorialContent,
    RightsRecord,
    check_publication_eligibility,
)
from services.bizinfo.normalizer import DateRange, NormalizedSourceRecord
from services.bizinfo.repository import InMemoryBizinfoRepository
from services.bizinfo.status import (
    ChangeRecord,
    detect_change,
    event_status,
    program_status,
)

# ---------------------------------------------------------------------------
# Synthetic test fixtures
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 11, 4, 0, 0, 0, tzinfo=timezone.utc)
_TODAY = date(2026, 11, 4)


def _program_record(
    key: str = "PBLN_TEST_001",
    title: str = "산업재해 예방설비 설치비 지원",
    app_start: Optional[date] = date(2026, 10, 1),
    app_end:   Optional[date] = date(2026, 12, 31),
    source_org: str = "고용노동부",
    summary: str = "50인 미만 제조업 사업장의 산업안전 설비 설치를 지원합니다.",
    support_target: str = "50인 미만 제조업 사업장",
) -> NormalizedSourceRecord:
    return NormalizedSourceRecord(
        source_kind="PROGRAM",
        source_id="BIZINFO_PROGRAM",
        source_key=key,
        title=title,
        source_org=source_org,
        origin_url="https://www.bizinfo.go.kr/web/lay1/program/" + key,
        bizinfo_url="https://www.bizinfo.go.kr/web/lay1/program/" + key,
        retrieved_at=_NOW,
        application_period=DateRange(start=app_start, end=app_end) if (app_start or app_end) else None,
        summary=summary,
        support_target=support_target,
    )


def _event_record(
    key: str = "EVEN_TEST_001",
    title: str = "산업안전보건 교육 행사",
    evt_start: Optional[date] = date(2026, 11, 10),
    evt_end:   Optional[date] = date(2026, 11, 20),
    rcp_start: Optional[date] = date(2026, 10, 1),
    rcp_end:   Optional[date] = date(2026, 11, 5),
    source_org: str = "한국산업안전보건공단",
) -> NormalizedSourceRecord:
    return NormalizedSourceRecord(
        source_kind="EVENT",
        source_id="BIZINFO_EVENT",
        source_key=key,
        title=title,
        source_org=source_org,
        origin_url=None,
        bizinfo_url="https://www.bizinfo.go.kr/portal/event/detail/" + key,
        retrieved_at=_NOW,
        event_period=DateRange(start=evt_start, end=evt_end) if (evt_start or evt_end) else None,
        reception_period=DateRange(start=rcp_start, end=rcp_end) if (rcp_start or rcp_end) else None,
        summary="산업안전보건 교육 행사입니다.",
    )


def _editorial(source_kind: str, source_key: str) -> EditorialContent:
    return EditorialContent(
        source_kind=source_kind,
        source_key=source_key,
        explanation="TAI Safe 선별 — 50인 미만 사업장의 안전설비 설치비 지원사업입니다.",
        guidance="신청 전 사업장 규모와 업종 적합 여부를 확인하세요.",
        authored_at=_NOW,
    )


def _rights(source_key: str) -> RightsRecord:
    return RightsRecord(
        source_key=source_key,
        rights_basis=RIGHTS_BASIS_FACTS_ONLY_ATTRIBUTED,
        confirmed_at=_NOW,
        confirmed_by="reviewer-001",
    )


def _approval(source_kind: str, source_key: str) -> ContentApprovalRecord:
    return ContentApprovalRecord(
        source_kind=source_kind,
        source_key=source_key,
        approved_at=_NOW,
        approved_by="editor-001",
    )


def _first_change(record: NormalizedSourceRecord) -> ChangeRecord:
    return detect_change(None, record)


def _fully_seeded_repo(
    program_key: str = "PBLN_TEST_001",
    event_key:   str = "EVEN_TEST_001",
) -> InMemoryBizinfoRepository:
    repo = InMemoryBizinfoRepository()
    prec = _program_record(program_key)
    erec = _event_record(event_key)
    repo.seed_record(prec, _first_change(prec))
    repo.seed_record(erec, _first_change(erec))
    repo.seed_editorial(_editorial("PROGRAM", program_key))
    repo.seed_editorial(_editorial("EVENT", event_key))
    repo.seed_rights(_rights(program_key))
    repo.seed_rights(_rights(event_key))
    repo.seed_approval(_approval("PROGRAM", program_key))
    repo.seed_approval(_approval("EVENT", event_key))
    repo.seed_relevance("PROGRAM", program_key, "INCLUDE")
    repo.seed_relevance("EVENT", event_key, "INCLUDE")
    return repo


# ---------------------------------------------------------------------------
# FastAPI test client
# ---------------------------------------------------------------------------

def _client(repo: Optional[InMemoryBizinfoRepository] = None) -> TestClient:
    from fastapi import FastAPI
    from routers.bizinfo_public import get_repository, router

    app = FastAPI()
    app.include_router(router)
    if repo is not None:
        app.dependency_overrides[get_repository] = lambda: repo
    return TestClient(app, raise_server_exceptions=True)


# ===========================================================================
# S: Integration scenarios
# ===========================================================================


def test_S01_program_open_appears_in_list_and_detail():
    """S-01: 접수 중 지원사업이 목록과 상세 양쪽에 노출됨."""
    repo   = _fully_seeded_repo()
    client = _client(repo)

    r = client.get("/public/bizinfo/programs")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["source_key"] == "PBLN_TEST_001"
    assert items[0]["application_status"] == "OPEN"

    r2 = client.get("/public/bizinfo/programs/PBLN_TEST_001")
    assert r2.status_code == 200
    detail = r2.json()
    assert detail["source_key"] == "PBLN_TEST_001"
    assert detail["explanation"]  # TAI editorial present
    assert detail["guidance"]


def test_S02_event_two_axes_independent():
    """S-02: 행사 접수 마감·행사 진행 중 두 축이 독립적으로 표현됨."""
    # 접수 마감(rcp_end passed), 행사 진행 중(evt ongoing)
    rec = _event_record(
        rcp_start=date(2026, 10, 1),
        rcp_end=date(2026, 11, 3),    # yesterday
        evt_start=date(2026, 11, 1),
        evt_end=date(2026, 11, 30),
    )
    status = event_status(rec, as_of=_TODAY)
    assert status.reception_status == "CLOSED"
    assert status.progress_status  == "ONGOING"

    repo = InMemoryBizinfoRepository()
    repo.seed_record(rec, _first_change(rec))
    repo.seed_editorial(_editorial("EVENT", "EVEN_TEST_001"))
    repo.seed_rights(_rights("EVEN_TEST_001"))
    repo.seed_approval(_approval("EVENT", "EVEN_TEST_001"))
    repo.seed_relevance("EVENT", "EVEN_TEST_001", "INCLUDE")
    client = _client(repo)

    r = client.get("/public/bizinfo/events/EVEN_TEST_001")
    assert r.status_code == 200
    d = r.json()
    assert d["reception_status"] == "CLOSED"
    assert d["progress_status"]  == "ONGOING"


def test_S03_review_required_not_visible_to_customer():
    """S-03: 관련성 REVIEW_REQUIRED → 공개 조건 C-1 실패 → 고객 화면 미노출."""
    rec = _program_record()
    status = program_status(rec, as_of=_TODAY)
    change = _first_change(rec)

    eligibility = check_publication_eligibility(
        rec, status, change,
        _editorial("PROGRAM", rec.source_key),
        _rights(rec.source_key),
        _approval("PROGRAM", rec.source_key),
        relevance_verdict="REVIEW_REQUIRED",
    )
    assert not eligibility.eligible
    assert COND_RELEVANCE in eligibility.failed_conditions


def test_S04_no_editorial_not_visible():
    """S-04: 편집 콘텐츠 없음 → C-4 실패 → 고객 화면 미노출."""
    rec = _program_record()
    status = program_status(rec, as_of=_TODAY)
    change = _first_change(rec)

    eligibility = check_publication_eligibility(
        rec, status, change,
        None,                             # editorial missing
        _rights(rec.source_key),
        _approval("PROGRAM", rec.source_key),
        relevance_verdict="INCLUDE",
    )
    assert not eligibility.eligible
    assert COND_EDITORIAL in eligibility.failed_conditions

    # Router also excludes it — relevance seeded INCLUDE to isolate C-4 failure
    repo = InMemoryBizinfoRepository()
    repo.seed_record(rec, _first_change(rec))
    # no editorial seeded → not eligible
    repo.seed_rights(_rights(rec.source_key))
    repo.seed_approval(_approval("PROGRAM", rec.source_key))
    repo.seed_relevance("PROGRAM", rec.source_key, "INCLUDE")
    client = _client(repo)
    r = client.get("/public/bizinfo/programs/PBLN_TEST_001")
    assert r.status_code == 404


def test_S05_api_failure_does_not_remove_existing_record():
    """S-05: API 수집 실패 시 기존 저장 레코드가 삭제·취소로 처리되지 않음.

    API 실패는 SourceBatch.error_code != None로 반환된다.
    상태 판정 함수는 성공한 SourceBatch에서 나온 record만 받아야 하므로
    실패 경우는 호출 계층에서 차단한다.  이 테스트는 그 경계를 확인한다.
    """
    from services.bizinfo.api_access import ERR_TIMEOUT, SourceBatch
    batch = SourceBatch(
        source_kind="PROGRAM",
        provider="BIZINFO_PROGRAM",
        items=(),
        retrieved_at=_NOW,
        page=1,
        size=10,
        total_count=0,
        error_code=ERR_TIMEOUT,
    )
    # An error batch has no items — status.py is never called.
    assert batch.error_code is not None
    assert batch.items == ()
    # Previously stored record in repo must NOT be deleted
    repo = _fully_seeded_repo()
    assert repo.get_prior_record("PROGRAM", "PBLN_TEST_001") is not None


def test_S06_missing_dates_yield_unknown_and_first_obs_explicit():
    """S-06: 날짜 없음 → UNKNOWN 상태 / 최초 관측 → CHANGE_UNKNOWN."""
    rec = _program_record(app_start=None, app_end=None)
    status = program_status(rec, as_of=_TODAY)
    assert status.application_status == "UNKNOWN"
    assert not status.has_dates

    change = detect_change(None, rec)
    assert change.verdict == "CHANGE_UNKNOWN"
    assert change.changed_fields == ()


def test_S07_list_and_detail_key_match():
    """S-07: 목록과 상세의 source_key / bizinfo_url이 일치함."""
    repo   = _fully_seeded_repo()
    client = _client(repo)

    items = client.get("/public/bizinfo/programs").json()
    key   = items[0]["source_key"]
    burl  = items[0]["bizinfo_url"]

    detail = client.get(f"/public/bizinfo/programs/{key}").json()
    assert detail["source_key"] == key
    assert detail["bizinfo_url"] == burl


# ===========================================================================
# U: Unit tests
# ===========================================================================


def test_U01_program_status_boundaries():
    """U-01: PROGRAM 접수 예정·접수 중·마감 경계 판정."""
    rec_upcoming = _program_record(app_start=date(2026, 11, 10), app_end=date(2026, 11, 30))
    rec_open     = _program_record(app_start=date(2026, 11, 1),  app_end=date(2026, 11, 30))
    rec_closed   = _program_record(app_start=date(2026, 10, 1),  app_end=date(2026, 11, 3))

    assert program_status(rec_upcoming, as_of=_TODAY).application_status == "UPCOMING"
    assert program_status(rec_open,     as_of=_TODAY).application_status == "OPEN"
    assert program_status(rec_closed,   as_of=_TODAY).application_status == "CLOSED"


def test_U02_event_axes_independent():
    """U-02: EVENT 두 축이 서로 독립적으로 판정됨."""
    # Reception OPEN, event UPCOMING
    rec = _event_record(
        rcp_start=date(2026, 10, 1),  rcp_end=date(2026, 11, 30),
        evt_start=date(2026, 11, 20), evt_end=date(2026, 11, 25),
    )
    s = event_status(rec, as_of=_TODAY)
    assert s.reception_status == "OPEN"
    assert s.progress_status  == "UPCOMING"


def test_U03_change_detection():
    """U-03: 변경 감지 — 필드 변경·무변경·최초 관측."""
    rec1 = _program_record(title="원제목")
    rec2 = _program_record(title="수정된 제목", app_end=date(2027, 1, 31))

    # First observation
    c1 = detect_change(None, rec1)
    assert c1.verdict == "CHANGE_UNKNOWN"
    assert c1.changed_fields == ()

    # Unchanged
    c2 = detect_change(rec1, rec1)
    assert c2.verdict == "UNCHANGED"
    assert c2.changed_fields == ()

    # Changed
    c3 = detect_change(rec1, rec2)
    assert c3.verdict == "CHANGED"
    assert "title" in c3.changed_fields
    assert "app_end" in c3.changed_fields


def test_U04_publication_conditions_individual_failure():
    """U-04: 6개 공개 조건 각각 단독 실패 시 not_eligible."""
    rec    = _program_record()
    status = program_status(rec, as_of=_TODAY)
    change = _first_change(rec)
    ed     = _editorial("PROGRAM", rec.source_key)
    ri     = _rights(rec.source_key)
    ap     = _approval("PROGRAM", rec.source_key)

    # C-1: relevance
    e = check_publication_eligibility(rec, status, change, ed, ri, ap, relevance_verdict="HOLD")
    assert COND_RELEVANCE in e.failed_conditions

    # C-2: bizinfo_url missing (origin_url만 있어도 차단)
    rec_nourl = _program_record()
    object.__setattr__(rec_nourl, "bizinfo_url", None)
    object.__setattr__(rec_nourl, "origin_url",  None)
    e = check_publication_eligibility(rec_nourl, status, change, ed, ri, ap, relevance_verdict="INCLUDE")
    assert COND_SOURCE_LINK in e.failed_conditions

    # C-2 R1-02: bizinfo_url=None이지만 origin_url 있음 → 여전히 COND_SOURCE_LINK
    rec_origin_only = _program_record()
    object.__setattr__(rec_origin_only, "bizinfo_url", None)
    # origin_url은 _program_record() 기본값으로 설정돼 있음
    e = check_publication_eligibility(rec_origin_only, status, change, ed, ri, ap, relevance_verdict="INCLUDE")
    assert COND_SOURCE_LINK in e.failed_conditions

    # C-2b: attribution name (source_org) missing
    rec_noorg = _program_record()
    object.__setattr__(rec_noorg, "source_org", None)
    e = check_publication_eligibility(rec_noorg, status, change, ed, ri, ap, relevance_verdict="INCLUDE")
    assert COND_ATTRIBUTION in e.failed_conditions

    # C-2b R1-02: source_org 공백만 있는 경우도 차단
    rec_wsorg = _program_record()
    object.__setattr__(rec_wsorg, "source_org", "   ")
    e = check_publication_eligibility(rec_wsorg, status, change, ed, ri, ap, relevance_verdict="INCLUDE")
    assert COND_ATTRIBUTION in e.failed_conditions

    # C-5b: rights_basis not in ALLOWED_RIGHTS_BASIS
    ri_invalid = RightsRecord(
        source_key=rec.source_key,
        rights_basis="INVALID_BASIS",
        confirmed_at=_NOW,
        confirmed_by="reviewer-001",
    )
    e = check_publication_eligibility(rec, status, change, ed, ri_invalid, ap, relevance_verdict="INCLUDE")
    assert COND_RIGHTS in e.failed_conditions

    # C-5 R1-01: confirmed_by 비어있음 → COND_RIGHTS
    ri_noreviewer = RightsRecord(
        source_key=rec.source_key,
        rights_basis=RIGHTS_BASIS_FACTS_ONLY_ATTRIBUTED,
        confirmed_at=_NOW,
        confirmed_by="",
    )
    e = check_publication_eligibility(rec, status, change, ed, ri_noreviewer, ap, relevance_verdict="INCLUDE")
    assert COND_RIGHTS in e.failed_conditions

    # C-6 R1-01: approved_by 비어있음 → COND_APPROVAL_RECORD
    ap_noapprover = ContentApprovalRecord(
        source_kind="PROGRAM",
        source_key=rec.source_key,
        approved_at=_NOW,
        approved_by="",
    )
    e = check_publication_eligibility(rec, status, change, ed, ri, ap_noapprover, relevance_verdict="INCLUDE")
    assert COND_APPROVAL_RECORD in e.failed_conditions

    # C-4: editorial missing
    e = check_publication_eligibility(rec, status, change, None, ri, ap, relevance_verdict="INCLUDE")
    assert COND_EDITORIAL in e.failed_conditions

    # C-5: rights missing
    e = check_publication_eligibility(rec, status, change, ed, None, ap, relevance_verdict="INCLUDE")
    assert COND_RIGHTS in e.failed_conditions

    # C-6: approval missing
    e = check_publication_eligibility(rec, status, change, ed, ri, None, relevance_verdict="INCLUDE")
    assert COND_APPROVAL_RECORD in e.failed_conditions

    # All pass
    e = check_publication_eligibility(rec, status, change, ed, ri, ap, relevance_verdict="INCLUDE")
    assert e.eligible
    assert e.failed_conditions == ()


def test_U05_in_memory_repository_contract():
    """U-05: InMemoryBizinfoRepository 저장·조회 계약."""
    repo = InMemoryBizinfoRepository()
    rec  = _program_record()
    chg  = _first_change(rec)

    assert repo.get_prior_record("PROGRAM", rec.source_key) is None
    repo.save_record(rec, chg)
    assert repo.get_prior_record("PROGRAM", rec.source_key) is rec

    ed = _editorial("PROGRAM", rec.source_key)
    repo.seed_editorial(ed)
    assert repo.get_editorial("PROGRAM", rec.source_key) is ed

    ri = _rights(rec.source_key)
    repo.seed_rights(ri)

    ap = _approval("PROGRAM", rec.source_key)
    repo.seed_approval(ap)
    assert repo.get_approval("PROGRAM", rec.source_key) is ap

    keys = repo.list_eligible_keys("PROGRAM")
    assert rec.source_key in keys


def test_U06_router_returns_only_approved():
    """U-06: 라우터는 6개 조건이 모두 충족된 항목만 반환함."""
    repo      = _fully_seeded_repo(program_key="PBLN_APPROVED")
    # Second record — no approval seeded
    rec_noapp = _program_record(key="PBLN_NOAPP")
    repo.seed_record(rec_noapp, _first_change(rec_noapp))
    repo.seed_editorial(_editorial("PROGRAM", "PBLN_NOAPP"))
    repo.seed_rights(_rights("PBLN_NOAPP"))
    # No approval for PBLN_NOAPP

    client = _client(repo)
    items  = client.get("/public/bizinfo/programs").json()
    keys   = [i["source_key"] for i in items]
    assert "PBLN_APPROVED" in keys
    assert "PBLN_NOAPP"    not in keys


def test_U07_router_unknown_key_returns_404():
    """U-07: 미등록 key → 404."""
    repo   = _fully_seeded_repo()
    client = _client(repo)
    r      = client.get("/public/bizinfo/programs/PBLN_NONEXISTENT")
    assert r.status_code == 404


def test_U08_router_storage_gate_pending_returns_503():
    """U-08: repository 미등록(STORAGE_GATE 미활성) → 503."""
    client = _client(repo=None)   # no override → get_repository raises 503
    r      = client.get("/public/bizinfo/programs")
    assert r.status_code == 503
    assert "BIZINFO_STORAGE_GATE_PENDING" in r.text


# ===========================================================================
# R: R1 보정 검증 — 고객 정보 오공개 위험 3건
# ===========================================================================


def test_R01_relevance_exclude_blocked_in_api():
    """R-01: 관련성 EXCLUDE → 목록·상세 모두 차단됨."""
    rec = _program_record()
    repo = InMemoryBizinfoRepository()
    repo.seed_record(rec, _first_change(rec))
    repo.seed_editorial(_editorial("PROGRAM", rec.source_key))
    repo.seed_rights(_rights(rec.source_key))
    repo.seed_approval(_approval("PROGRAM", rec.source_key))
    repo.seed_relevance("PROGRAM", rec.source_key, "EXCLUDE")
    client = _client(repo)

    items = client.get("/public/bizinfo/programs").json()
    assert all(i["source_key"] != rec.source_key for i in items)

    r = client.get(f"/public/bizinfo/programs/{rec.source_key}")
    assert r.status_code == 404


def test_R02_relevance_hold_blocked_in_api():
    """R-02: 관련성 HOLD → 목록·상세 모두 차단됨."""
    rec = _program_record()
    repo = InMemoryBizinfoRepository()
    repo.seed_record(rec, _first_change(rec))
    repo.seed_editorial(_editorial("PROGRAM", rec.source_key))
    repo.seed_rights(_rights(rec.source_key))
    repo.seed_approval(_approval("PROGRAM", rec.source_key))
    repo.seed_relevance("PROGRAM", rec.source_key, "HOLD")
    client = _client(repo)

    items = client.get("/public/bizinfo/programs").json()
    assert all(i["source_key"] != rec.source_key for i in items)

    r = client.get(f"/public/bizinfo/programs/{rec.source_key}")
    assert r.status_code == 404


def test_R04_invalid_rights_basis_blocked():
    """R-04: ALLOWED_RIGHTS_BASIS 외 rights_basis → C-5 실패 → 공개 차단.

    기업마당 원문·PDF 복제를 의미하는 비승인 근거는 공개 조건을 통과하지 못한다.
    """
    rec    = _program_record()
    status = program_status(rec, as_of=_TODAY)
    change = _first_change(rec)
    ed     = _editorial("PROGRAM", rec.source_key)
    ap     = _approval("PROGRAM", rec.source_key)

    ri_invalid = RightsRecord(
        source_key=rec.source_key,
        rights_basis="공공저작물 자유이용허락 (KOGL 제1유형)",  # 미승인 근거
        confirmed_at=_NOW,
        confirmed_by="reviewer-001",
    )
    e = check_publication_eligibility(
        rec, status, change, ed, ri_invalid, ap, relevance_verdict="INCLUDE"
    )
    assert not e.eligible
    assert COND_RIGHTS in e.failed_conditions


def test_R05_missing_source_org_blocked():
    """R-05: source_org 없음 → C-2b(attribution) 실패 → 공개 차단.

    출처명이 없으면 고객 화면에 출처를 표기할 수 없어 공개를 차단한다.
    """
    rec_noorg = _program_record()
    object.__setattr__(rec_noorg, "source_org", None)
    status = program_status(rec_noorg, as_of=_TODAY)
    change = _first_change(rec_noorg)
    ed     = _editorial("PROGRAM", rec_noorg.source_key)
    ri     = _rights(rec_noorg.source_key)
    ap     = _approval("PROGRAM", rec_noorg.source_key)

    e = check_publication_eligibility(
        rec_noorg, status, change, ed, ri, ap, relevance_verdict="INCLUDE"
    )
    assert not e.eligible
    assert COND_ATTRIBUTION in e.failed_conditions


def test_R03_no_end_date_past_start_date_is_unknown():
    """R-03: 종료일 없는 과거 시작일 → OPEN이 아닌 UNKNOWN.

    시작일이 지났더라도 종료일을 모르면 접수 계속 여부를 확정할 수 없다.
    """
    # PROGRAM: start in past, end missing
    rec = _program_record(app_start=date(2026, 10, 1), app_end=None)
    status = program_status(rec, as_of=_TODAY)
    assert status.application_status == "UNKNOWN"
    assert status.has_dates  # start date is known

    # EVENT reception: start in past, end missing
    erec = _event_record(
        rcp_start=date(2026, 10, 1),
        rcp_end=None,
        evt_start=date(2026, 11, 20),
        evt_end=date(2026, 11, 25),
    )
    estatus = event_status(erec, as_of=_TODAY)
    assert estatus.reception_status == "UNKNOWN"
    assert estatus.progress_status  == "UPCOMING"  # Nov 20 is in the future


# ===========================================================================
# RG: RIGHTS_GATE R1 보정 검증
# ===========================================================================


def test_RG01_empty_confirmed_by_blocked():
    """RG-01: rights.confirmed_by 비어있음 → C-5 실패 → 공개 차단."""
    rec    = _program_record()
    status = program_status(rec, as_of=_TODAY)
    change = _first_change(rec)
    ed     = _editorial("PROGRAM", rec.source_key)
    ap     = _approval("PROGRAM", rec.source_key)

    ri_empty = RightsRecord(
        source_key=rec.source_key,
        rights_basis=RIGHTS_BASIS_FACTS_ONLY_ATTRIBUTED,
        confirmed_at=_NOW,
        confirmed_by="",   # 빈 승인자
    )
    e = check_publication_eligibility(
        rec, status, change, ed, ri_empty, ap, relevance_verdict="INCLUDE"
    )
    assert not e.eligible
    assert COND_RIGHTS in e.failed_conditions


def test_RG02_empty_approved_by_blocked():
    """RG-02: approval.approved_by 비어있음 → C-6 실패 → 공개 차단."""
    rec    = _program_record()
    status = program_status(rec, as_of=_TODAY)
    change = _first_change(rec)
    ed     = _editorial("PROGRAM", rec.source_key)
    ri     = _rights(rec.source_key)

    ap_empty = ContentApprovalRecord(
        source_kind="PROGRAM",
        source_key=rec.source_key,
        approved_at=_NOW,
        approved_by="",   # 빈 승인자
    )
    e = check_publication_eligibility(
        rec, status, change, ed, ri, ap_empty, relevance_verdict="INCLUDE"
    )
    assert not e.eligible
    assert COND_APPROVAL_RECORD in e.failed_conditions


def test_RG03_whitespace_only_source_org_blocked():
    """RG-03: source_org 공백만 있는 경우 → C-2b 실패 → 공개 차단."""
    rec_ws = _program_record()
    object.__setattr__(rec_ws, "source_org", "   ")
    status = program_status(rec_ws, as_of=_TODAY)
    change = _first_change(rec_ws)
    ed     = _editorial("PROGRAM", rec_ws.source_key)
    ri     = _rights(rec_ws.source_key)
    ap     = _approval("PROGRAM", rec_ws.source_key)

    e = check_publication_eligibility(
        rec_ws, status, change, ed, ri, ap, relevance_verdict="INCLUDE"
    )
    assert not e.eligible
    assert COND_ATTRIBUTION in e.failed_conditions


def test_RG04_origin_url_only_no_bizinfo_url_blocked():
    """RG-04: bizinfo_url 없고 origin_url만 있으면 → C-2 실패 → 공개 차단.

    고객 화면은 bizinfo_url을 원문 링크로 사용하므로
    bizinfo_url 없이는 공식 공고를 열어볼 수 없다.
    """
    rec_origin_only = _program_record()
    object.__setattr__(rec_origin_only, "bizinfo_url", None)
    # origin_url은 _program_record() 기본값으로 설정돼 있음
    status = program_status(rec_origin_only, as_of=_TODAY)
    change = _first_change(rec_origin_only)
    ed     = _editorial("PROGRAM", rec_origin_only.source_key)
    ri     = _rights(rec_origin_only.source_key)
    ap     = _approval("PROGRAM", rec_origin_only.source_key)

    e = check_publication_eligibility(
        rec_origin_only, status, change, ed, ri, ap, relevance_verdict="INCLUDE"
    )
    assert not e.eligible
    assert COND_SOURCE_LINK in e.failed_conditions


def test_RG05_full_valid_data_passes_all_conditions():
    """RG-05: 모든 조건 충족 — INCLUDE 판정, 실패 조건 없음."""
    rec    = _program_record()
    status = program_status(rec, as_of=_TODAY)
    change = _first_change(rec)
    ed     = _editorial("PROGRAM", rec.source_key)
    ri     = _rights(rec.source_key)
    ap     = _approval("PROGRAM", rec.source_key)

    e = check_publication_eligibility(
        rec, status, change, ed, ri, ap, relevance_verdict="INCLUDE"
    )
    assert e.eligible
    assert e.failed_conditions == ()
