"""WO-TAI-DOC-SEC0-IMPLEMENT-001 / WO-TAI-DOC-SEC0-PR609-CORRECTION-001
   SEC0 Auth & Tenant Scope Test Suite

Coverage:
  T01  report-forms: no token → 401
  T02  report-forms/events/{factory_id}: cross-company factory → 404
  T03  report-forms/events/{factory_id}: own factory → 200
  T04  POST report-forms/events: own factory → 200
  T05  POST report-forms/events: cross-company factory → 404
  T06  POST report-forms/submissions: own factory → 200
  T07  POST report-forms/submissions: cross-company factory → 404
  T08  GET  report-forms/submissions/detail/{id}: own submission → 200
  T09  GET  report-forms/submissions/detail/{id}: cross-company submission → 404
  T10  document-runtime: no token → 401
  T11  document-runtime: no facility_id → 200 (pass through)
  T12  document-runtime: own facility_id → 200
           (facility_id == factory_id UUID; runtime_facility_profile.id exists)
  T13  document-runtime: cross-company facility_id → 4xx (fail-closed)
  T14  POST report-forms/storage/upload-template: no token → 401
  T15  GET  report-forms/storage/signed-url/{id}: no token → 401

  T16  document-runtime: facility not in runtime_facility_profile → 403
  T17  POST /render: cross-company facility_id in context → 4xx
  T18  POST /submissions: cross-company event_id → 404
  T19  PATCH /submissions: submitted_at + own-factory event → event COMPLETED
  T20  PATCH /submissions: submitted_at + cross-factory event → event NOT updated
  T21  PATCH /submissions: pdf_url field rejected → 400
  T22  GET signed-url: storage path prefix mismatches factory_id → 403
  T23  document_engine_api router loads (no regression)
  T24  created_by forced from token, not body

Production DB write = 0 (mock 전용).
mock fixture는 실제 DB 스키마와 일치 —
  runtime_facility_profile: id (PK), facility_name 등 (factory_id 컬럼 없음)
  factories: id, company_id
  facility_id == factory_id UUID (facility_condition.factory_id=facility_id 패턴 근거)
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch


# ─── shared fixtures ────────────────────────────────────────────────────────

USER_OWN = {
    "id": "user-own-001",
    "company_id": "company-A",
    "factory_id": "factory-A1",
    "role_code": "FACTORY_MANAGER",
}

USER_OTHER = {
    "id": "user-other-001",
    "company_id": "company-B",
    "factory_id": "factory-B1",
    "role_code": "FACTORY_MANAGER",
}

FACTORY_A1 = {"id": "factory-A1", "company_id": "company-A", "name": "테스트 사업장"}
FACTORY_B1 = {"id": "factory-B1", "company_id": "company-B", "name": "타사 사업장"}

SUBMISSION_A = {
    "id": "sub-001",
    "factory_id": "factory-A1",
    "form_code": "OSHACT-FORM-002",
    "form_data": {},
    "pdf_url": None,
    "event_id": None,
    "submitted_at": None,
    "created_at": "2026-10-13T00:00:00+09:00",
    "updated_at": "2026-10-13T00:00:00+09:00",
}
EVENT_A = {
    "id": "event-001",
    "factory_id": "factory-A1",
    "form_code": "OSHACT-FORM-002",
    "status": "PENDING",
    "due_date": "2026-11-01",
    "trigger_date": "2026-10-13",
}
EVENT_B = {
    "id": "event-B01",
    "factory_id": "factory-B1",  # 타사 이벤트
    "form_code": "OSHACT-FORM-002",
    "status": "PENDING",
    "due_date": "2026-11-01",
}

# facility_id == factory_id UUID (실제 스키마 근거)
# runtime_facility_profile.id = facility_id; factory_id 컬럼 없음
FACILITY_PROFILE_A = {
    "id": "factory-A1",  # facility_id == factory_id
    "facility_name": "테스트 시설",
}
FACILITY_PROFILE_B = {
    "id": "factory-B1",  # facility_id == factory_id
    "facility_name": "타사 시설",
}


class _R:
    """Mock Supabase result."""
    def __init__(self, data, count=None):
        self.data = data
        self.count = count if count is not None else (len(data) if isinstance(data, list) else 0)


def _make_sb(table_data: dict) -> MagicMock:
    """Supabase mock. table_data: {table_name: [rows]} or {table_name: single_row_dict}.
    insert/update returns table_data.get(table_name+'__insert', [{}])[0].
    """
    sb = MagicMock()

    def _tbl(name):
        rows_raw = table_data.get(name, [])
        rows = rows_raw if isinstance(rows_raw, list) else [rows_raw]
        single = rows[0] if rows else None

        insert_result = table_data.get(name + "__insert", rows)
        insert_single = insert_result[0] if insert_result else {}

        tbl = MagicMock()
        q = MagicMock()

        tbl.select.return_value = q
        tbl.insert.return_value = MagicMock(execute=lambda: _R([insert_single]))
        tbl.update.return_value = MagicMock(execute=lambda: _R([single] if single else []))

        q.eq.return_value = q
        q.neq.return_value = q
        q.order.return_value = q
        q.range.return_value = q
        q.limit.return_value = q
        q.in_.return_value = q
        q.maybe_single.return_value = q
        q.execute.return_value = _R(rows)
        q.single.return_value = MagicMock(execute=lambda: _R(single))

        return tbl

    sb.table.side_effect = _tbl
    return sb


# ─── T01: report-forms no token → 401 ──────────────────────────────────────

def test_T01_report_forms_no_token_401():
    """인증 헤더 없이 report-forms 호출 → 401"""
    from routers.report_forms import router
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/report-forms/templates").status_code == 401


# ─── T02: report-forms/events cross-company → 404 ──────────────────────────

def test_T02_events_cross_company_404(monkeypatch):
    """타사 factory_id 로 이벤트 조회 → 404"""
    from routers.report_forms import router
    from routers.auth import get_current_user

    sb = _make_sb({"factories": [FACTORY_A1]})
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: USER_OTHER
    monkeypatch.setattr("routers.report_forms.get_supabase", lambda: sb)

    assert TestClient(app, raise_server_exceptions=False).get(
        "/report-forms/events/factory-A1"
    ).status_code == 404
    app.dependency_overrides.clear()


# ─── T03: report-forms/events own factory → 200 ─────────────────────────────

def test_T03_events_own_factory_200(monkeypatch):
    """자사 factory_id 로 이벤트 조회 → 200"""
    from routers.report_forms import router
    from routers.auth import get_current_user

    sb = _make_sb({
        "factories": [FACTORY_A1],
        "report_events": [EVENT_A],
    })
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: USER_OWN
    monkeypatch.setattr("routers.report_forms.get_supabase", lambda: sb)
    monkeypatch.setattr("routers.report_forms.business_today",
                        lambda: __import__("datetime").date(2026, 10, 14))
    monkeypatch.setattr("routers.report_forms.now_kst",
                        lambda: __import__("datetime").datetime(2026, 10, 14))
    monkeypatch.setattr("routers.report_forms.serialize_business_datetime", lambda dt: str(dt))

    assert TestClient(app, raise_server_exceptions=False).get(
        "/report-forms/events/factory-A1"
    ).status_code == 200
    app.dependency_overrides.clear()


# ─── T04: POST events own factory → 200 ─────────────────────────────────────

def test_T04_create_event_own_factory_200(monkeypatch):
    """자사 factory_id 로 이벤트 생성 → 200"""
    from routers.report_forms import router
    from routers.auth import get_current_user

    new_event = {**EVENT_A, "id": "event-new-001"}
    sb = _make_sb({
        "factories": [FACTORY_A1],
        "report_events__insert": [new_event],
        "report_events": [new_event],
        "master_building_legal_rules": [],
    })
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: USER_OWN
    monkeypatch.setattr("routers.report_forms.get_supabase", lambda: sb)
    monkeypatch.setattr("routers.report_forms.business_today",
                        lambda: __import__("datetime").date(2026, 10, 14))
    monkeypatch.setattr("routers.report_forms.now_kst",
                        lambda: __import__("datetime").datetime(2026, 10, 14))
    monkeypatch.setattr("routers.report_forms.serialize_business_datetime", lambda dt: str(dt))

    resp = TestClient(app, raise_server_exceptions=False).post(
        "/report-forms/events",
        json={"factory_id": "factory-A1", "form_code": "OSHACT-FORM-002",
              "trigger_date": "2026-10-13", "due_days": 14}
    )
    assert resp.status_code == 200
    app.dependency_overrides.clear()


# ─── T05: POST events cross-company → 404 ────────────────────────────────────

def test_T05_create_event_cross_company_404(monkeypatch):
    """타사 factory_id 로 이벤트 생성 → 404"""
    from routers.report_forms import router
    from routers.auth import get_current_user

    sb = _make_sb({"factories": [FACTORY_A1]})
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: USER_OTHER
    monkeypatch.setattr("routers.report_forms.get_supabase", lambda: sb)

    resp = TestClient(app, raise_server_exceptions=False).post(
        "/report-forms/events",
        json={"factory_id": "factory-A1", "form_code": "OSHACT-FORM-002",
              "trigger_date": "2026-10-13"}
    )
    assert resp.status_code == 404
    app.dependency_overrides.clear()


# ─── T06: POST submissions own factory → 200 ─────────────────────────────────

def test_T06_create_submission_own_factory_200(monkeypatch):
    """자사 factory_id 로 서류 생성 → 200"""
    from routers.report_forms import router
    from routers.auth import get_current_user

    sb = _make_sb({
        "factories": [FACTORY_A1],
        "form_submissions__insert": [SUBMISSION_A],
        "form_submissions": [SUBMISSION_A],
    })
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: USER_OWN
    monkeypatch.setattr("routers.report_forms.get_supabase", lambda: sb)
    monkeypatch.setattr("routers.report_forms.now_kst",
                        lambda: __import__("datetime").datetime(2026, 10, 14))
    monkeypatch.setattr("routers.report_forms.serialize_business_datetime", lambda dt: str(dt))

    resp = TestClient(app, raise_server_exceptions=False).post(
        "/report-forms/submissions",
        json={"factory_id": "factory-A1", "form_code": "OSHACT-FORM-002", "form_data": {}}
    )
    assert resp.status_code == 200
    app.dependency_overrides.clear()


# ─── T07: POST submissions cross-company → 404 ───────────────────────────────

def test_T07_create_submission_cross_company_404(monkeypatch):
    """타사 factory_id 로 서류 생성 → 404"""
    from routers.report_forms import router
    from routers.auth import get_current_user

    sb = _make_sb({"factories": [FACTORY_A1]})
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: USER_OTHER
    monkeypatch.setattr("routers.report_forms.get_supabase", lambda: sb)

    resp = TestClient(app, raise_server_exceptions=False).post(
        "/report-forms/submissions",
        json={"factory_id": "factory-A1", "form_code": "OSHACT-FORM-002"}
    )
    assert resp.status_code == 404
    app.dependency_overrides.clear()


# ─── T08: GET submissions/detail own → 200 ───────────────────────────────────

def test_T08_get_submission_detail_own_200(monkeypatch):
    """자사 서류 상세 조회 → 200"""
    from routers.report_forms import router
    from routers.auth import get_current_user

    sb = _make_sb({
        "factories": [FACTORY_A1],
        "form_submissions": [SUBMISSION_A],
    })
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: USER_OWN
    monkeypatch.setattr("routers.report_forms.get_supabase", lambda: sb)

    assert TestClient(app, raise_server_exceptions=False).get(
        "/report-forms/submissions/detail/sub-001"
    ).status_code == 200
    app.dependency_overrides.clear()


# ─── T09: GET submissions/detail cross-company → 404 ─────────────────────────

def test_T09_get_submission_detail_cross_company_404(monkeypatch):
    """타사 서류 상세 조회 → 404"""
    from routers.report_forms import router
    from routers.auth import get_current_user

    sb = _make_sb({
        "factories": [FACTORY_A1],
        "form_submissions": [SUBMISSION_A],
    })
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: USER_OTHER
    monkeypatch.setattr("routers.report_forms.get_supabase", lambda: sb)

    assert TestClient(app, raise_server_exceptions=False).get(
        "/report-forms/submissions/detail/sub-001"
    ).status_code == 404
    app.dependency_overrides.clear()


# ─── T10: document-runtime no token → 401 ────────────────────────────────────

def test_T10_document_runtime_no_token_401():
    """인증 헤더 없이 document-runtime 호출 → 401"""
    from routers.document_runtime import router
    app = FastAPI()
    app.include_router(router)
    assert TestClient(app, raise_server_exceptions=False).get(
        "/document-runtime/some-doc-type"
    ).status_code == 401


# ─── T11: document-runtime no facility_id → 200 ──────────────────────────────

def test_T11_document_runtime_no_facility_200(monkeypatch):
    """facility_id 없이 document-runtime 호출 → 200 (소유권 검증 생략)"""
    from routers.document_runtime import router
    from routers.auth import get_current_user

    mock_payload = {"document_type": "TEST_DOC", "tenant_context": {}, "sections": []}
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: USER_OWN
    monkeypatch.setattr("routers.document_runtime.resolve_document_runtime",
                        lambda dt, ctx: mock_payload)
    monkeypatch.setattr("routers.document_runtime.calculate_document_completeness",
                        lambda s: {"total": 0, "filled": 0, "pct": 0})

    assert TestClient(app, raise_server_exceptions=False).get(
        "/document-runtime/TEST_DOC"
    ).status_code == 200
    app.dependency_overrides.clear()


# ─── T12: document-runtime own facility_id → 200 ─────────────────────────────
# facility_id == factory_id UUID; runtime_facility_profile.id exists; no factory_id column

def test_T12_document_runtime_own_facility_200(monkeypatch):
    """자사 facility_id 로 document-runtime 호출 → 200.
    mock: runtime_facility_profile.id='factory-A1' (facility_id=factory_id);
          factories.id='factory-A1' company_id='company-A' → USER_OWN 일치.
    """
    from routers.document_runtime import router
    from routers.auth import get_current_user

    sb = _make_sb({
        "runtime_facility_profile": [FACILITY_PROFILE_A],  # id='factory-A1', no factory_id col
        "factories": [FACTORY_A1],  # id='factory-A1', company_id='company-A'
    })
    mock_payload = {"document_type": "TEST_DOC", "tenant_context": {}, "sections": []}
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: USER_OWN
    monkeypatch.setattr("routers.document_runtime.get_supabase", lambda: sb)
    monkeypatch.setattr("routers.document_runtime.resolve_document_runtime",
                        lambda dt, ctx: mock_payload)
    monkeypatch.setattr("routers.document_runtime.calculate_document_completeness",
                        lambda s: {"total": 0, "filled": 0, "pct": 0})

    assert TestClient(app, raise_server_exceptions=False).get(
        "/document-runtime/TEST_DOC?facility_id=factory-A1"
    ).status_code == 200
    app.dependency_overrides.clear()


# ─── T13: document-runtime cross-company facility_id → 4xx (fail-closed) ─────

def test_T13_document_runtime_cross_company_facility_denied(monkeypatch):
    """타사 facility_id 로 document-runtime 호출 → 4xx (fail-closed).
    mock: facility_id='factory-B1'; factories.company_id='company-B' ≠ USER_OWN company-A.
    """
    from routers.document_runtime import router
    from routers.auth import get_current_user

    sb = _make_sb({
        "runtime_facility_profile": [FACILITY_PROFILE_B],  # id='factory-B1'
        "factories": [FACTORY_B1],  # company_id='company-B'
    })
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: USER_OWN
    monkeypatch.setattr("routers.document_runtime.get_supabase", lambda: sb)

    resp = TestClient(app, raise_server_exceptions=False).get(
        "/document-runtime/TEST_DOC?facility_id=factory-B1"
    )
    assert resp.status_code in (403, 404)  # _ensure_factory_own raises 404 (existence-hiding)
    app.dependency_overrides.clear()


# ─── T14: upload-template no token → 401 ─────────────────────────────────────

def test_T14_upload_template_no_token_401():
    """인증 헤더 없이 템플릿 업로드 → 401"""
    from routers.report_forms import router
    app = FastAPI()
    app.include_router(router)
    resp = TestClient(app, raise_server_exceptions=False).post(
        "/report-forms/storage/upload-template",
        json={"form_code": "OSHACT-FORM-002", "html_content": "<html></html>"}
    )
    assert resp.status_code == 401


# ─── T15: signed-url no token → 401 ──────────────────────────────────────────

def test_T15_signed_url_no_token_401():
    """인증 헤더 없이 signed URL 요청 → 401"""
    from routers.report_forms import router
    app = FastAPI()
    app.include_router(router)
    assert TestClient(app, raise_server_exceptions=False).get(
        "/report-forms/storage/signed-url/sub-001"
    ).status_code == 401


# ═══════════════════════════════════════════════════════════════════
# T16–T24: P0 보완 테스트 (WO-TAI-DOC-SEC0-PR609-CORRECTION-001)
# ═══════════════════════════════════════════════════════════════════

# ─── T16: facility not in runtime_facility_profile → 403 (fail-closed) ───────

def test_T16_facility_not_found_403(monkeypatch):
    """facility_id가 runtime_facility_profile에 없으면 403 (fail-closed).
    mock: runtime_facility_profile = [] (없음).
    """
    from routers.document_runtime import router
    from routers.auth import get_current_user

    sb = _make_sb({"runtime_facility_profile": []})
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: USER_OWN
    monkeypatch.setattr("routers.document_runtime.get_supabase", lambda: sb)

    resp = TestClient(app, raise_server_exceptions=False).get(
        "/document-runtime/TEST_DOC?facility_id=factory-A1"
    )
    assert resp.status_code == 403
    app.dependency_overrides.clear()


# ─── T17: POST /render cross-company facility_id → 4xx ───────────────────────

def test_T17_render_cross_company_facility_denied(monkeypatch):
    """POST /render context에 타사 facility_id → 4xx.
    context 키 화이트리스트(facility_id만) + 소유권 검증.
    """
    from routers.document_runtime import router
    from routers.auth import get_current_user

    sb = _make_sb({
        "runtime_facility_profile": [FACILITY_PROFILE_B],
        "factories": [FACTORY_B1],
    })
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: USER_OWN
    monkeypatch.setattr("routers.document_runtime.get_supabase", lambda: sb)

    resp = TestClient(app, raise_server_exceptions=False).post(
        "/document-runtime/render",
        json={"document_type": "TEST_DOC",
              "context": {"facility_id": "factory-B1", "injected_key": "evil"}}
    )
    assert resp.status_code in (403, 404)
    app.dependency_overrides.clear()


# ─── T18: POST /submissions cross-company event_id → 404 ─────────────────────

def test_T18_submission_cross_event_id_404(monkeypatch):
    """POST /submissions: factory_id는 자사이나 event_id가 타사 → 404.
    event_id=event-B01 → factory_id='factory-B1' ≠ submission factory_id='factory-A1'.
    """
    from routers.report_forms import router
    from routers.auth import get_current_user

    sb = _make_sb({
        "factories": [FACTORY_A1],
        "report_events": [EVENT_B],  # factory_id='factory-B1'
    })
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: USER_OWN
    monkeypatch.setattr("routers.report_forms.get_supabase", lambda: sb)
    monkeypatch.setattr("routers.report_forms.now_kst",
                        lambda: __import__("datetime").datetime(2026, 10, 14))
    monkeypatch.setattr("routers.report_forms.serialize_business_datetime", lambda dt: str(dt))

    resp = TestClient(app, raise_server_exceptions=False).post(
        "/report-forms/submissions",
        json={"factory_id": "factory-A1",
              "form_code": "OSHACT-FORM-002",
              "event_id": "event-B01"}
    )
    assert resp.status_code == 404
    app.dependency_overrides.clear()


# ─── T19: PATCH /submissions submitted_at + own event → event COMPLETED ──────

def test_T19_patch_submitted_at_own_event_completed(monkeypatch):
    """submitted_at 수정 + 자사 event_id → event COMPLETED 처리 허용."""
    from routers.report_forms import router
    from routers.auth import get_current_user

    sub_with_event = {**SUBMISSION_A, "event_id": "event-001"}
    updated_sub = {**sub_with_event, "submitted_at": "2026-10-14T10:00:00+09:00"}

    # Track whether report_events.update was called
    events_updated = []

    sb_raw = _make_sb({
        "factories": [FACTORY_A1],
        "form_submissions": [sub_with_event],
        "report_events": [EVENT_A],  # factory_id='factory-A1'
    })

    # Patch tbl.update on report_events to track calls
    orig_side = sb_raw.table.side_effect
    def _tbl_spy(name):
        tbl = orig_side(name)
        if name == "report_events":
            orig_update = tbl.update
            def _update_spy(data):
                events_updated.append(data)
                return orig_update(data)
            tbl.update = _update_spy
        if name == "form_submissions":
            # Make update return the updated submission
            tbl.update.return_value = MagicMock(execute=lambda: _R([updated_sub]))
        return tbl
    sb_raw.table.side_effect = _tbl_spy

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: USER_OWN
    monkeypatch.setattr("routers.report_forms.get_supabase", lambda: sb_raw)
    monkeypatch.setattr("routers.report_forms.now_kst",
                        lambda: __import__("datetime").datetime(2026, 10, 14))
    monkeypatch.setattr("routers.report_forms.serialize_business_datetime", lambda dt: str(dt))

    resp = TestClient(app, raise_server_exceptions=False).patch(
        "/report-forms/submissions/sub-001",
        json={"submitted_at": "2026-10-14T10:00:00+09:00"}
    )
    assert resp.status_code == 200
    # event update should have been called (COMPLETED)
    assert any("COMPLETED" in str(u) for u in events_updated), \
        f"이벤트 COMPLETED 처리 없음. 호출: {events_updated}"
    app.dependency_overrides.clear()


# ─── T20: PATCH /submissions submitted_at + cross-factory event → skipped ────

def test_T20_patch_submitted_at_cross_event_skipped(monkeypatch):
    """submitted_at 수정 + 타사 event_id → event NOT updated (silent skip).
    submission 수정 자체는 허용 (factory_id 이미 검증됨).
    """
    from routers.report_forms import router
    from routers.auth import get_current_user

    # submission은 factory-A1이지만 event_id는 타사(factory-B1) 이벤트
    sub_cross_event = {**SUBMISSION_A, "event_id": "event-B01"}
    updated_sub = {**sub_cross_event, "submitted_at": "2026-10-14T10:00:00+09:00"}

    events_updated = []

    sb_raw = _make_sb({
        "factories": [FACTORY_A1],
        "form_submissions": [sub_cross_event],
        "report_events": [EVENT_B],  # factory_id='factory-B1' ≠ factory-A1
    })

    orig_side = sb_raw.table.side_effect
    def _tbl_spy(name):
        tbl = orig_side(name)
        if name == "report_events":
            orig_update = tbl.update
            def _update_spy(data):
                events_updated.append(data)
                return orig_update(data)
            tbl.update = _update_spy
        if name == "form_submissions":
            tbl.update.return_value = MagicMock(execute=lambda: _R([updated_sub]))
        return tbl
    sb_raw.table.side_effect = _tbl_spy

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: USER_OWN
    monkeypatch.setattr("routers.report_forms.get_supabase", lambda: sb_raw)
    monkeypatch.setattr("routers.report_forms.now_kst",
                        lambda: __import__("datetime").datetime(2026, 10, 14))
    monkeypatch.setattr("routers.report_forms.serialize_business_datetime", lambda dt: str(dt))

    resp = TestClient(app, raise_server_exceptions=False).patch(
        "/report-forms/submissions/sub-001",
        json={"submitted_at": "2026-10-14T10:00:00+09:00"}
    )
    assert resp.status_code == 200
    # 타사 event는 COMPLETED 처리되어선 안 됨
    completed_updates = [u for u in events_updated if "COMPLETED" in str(u)]
    assert len(completed_updates) == 0, \
        f"타사 이벤트가 COMPLETED 처리됨: {completed_updates}"
    app.dependency_overrides.clear()


# ─── T21: PATCH /submissions pdf_url field rejected → 400 ────────────────────

def test_T21_patch_pdf_url_blocked_400(monkeypatch):
    """PATCH /submissions에서 pdf_url만 보내면 400 — 서버 전용 필드."""
    from routers.report_forms import router
    from routers.auth import get_current_user

    sb = _make_sb({
        "factories": [FACTORY_A1],
        "form_submissions": [SUBMISSION_A],
    })
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: USER_OWN
    monkeypatch.setattr("routers.report_forms.get_supabase", lambda: sb)
    monkeypatch.setattr("routers.report_forms.now_kst",
                        lambda: __import__("datetime").datetime(2026, 10, 14))
    monkeypatch.setattr("routers.report_forms.serialize_business_datetime", lambda dt: str(dt))

    resp = TestClient(app, raise_server_exceptions=False).patch(
        "/report-forms/submissions/sub-001",
        json={"pdf_url": "factory-B1/evil.pdf"}
    )
    assert resp.status_code == 400
    app.dependency_overrides.clear()


# ─── T22: signed-url storage path prefix ≠ factory_id → 403 ─────────────────

def test_T22_signed_url_path_mismatch_403(monkeypatch):
    """pdf_url prefix(factory-B1)가 submission factory_id(factory-A1)와 다르면 403."""
    from routers.report_forms import router
    from routers.auth import get_current_user

    sub_bad_path = {**SUBMISSION_A, "pdf_url": "factory-B1/sub-001.pdf"}
    sb = _make_sb({
        "factories": [FACTORY_A1],
        "form_submissions": [sub_bad_path],
    })
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: USER_OWN
    monkeypatch.setattr("routers.report_forms.get_supabase", lambda: sb)

    resp = TestClient(app, raise_server_exceptions=False).get(
        "/report-forms/storage/signed-url/sub-001"
    )
    assert resp.status_code == 403
    app.dependency_overrides.clear()


# ─── T23: document_engine_api router loads (regression guard) ─────────────────

def test_T23_document_engine_router_no_regression():
    """routers.document_engine_api 임포트 이상 없음 — canonical 엔진 회귀 없음."""
    import inspect
    import routers.document_engine_api as eng_mod
    from routers.document_engine_api import router as engine_router
    assert engine_router is not None
    assert len(engine_router.routes) > 0, "document_engine_api 라우터에 라우트 없음"
    # 모듈 소스에 get_current_user 사용 여부 확인 (파라미터 Depends 방식)
    source = inspect.getsource(eng_mod)
    assert "get_current_user" in source, "document_engine_api에 인증 Depends가 없음"


# ─── T24: created_by forced from token, not body ──────────────────────────────

def test_T24_created_by_from_token(monkeypatch):
    """POST /submissions created_by는 token에서 강제 주입 — body 값 무시."""
    from routers.report_forms import router
    from routers.auth import get_current_user

    inserted = []

    sb_raw = _make_sb({
        "factories": [FACTORY_A1],
        "form_submissions": [SUBMISSION_A],
        "form_submissions__insert": [SUBMISSION_A],
    })
    orig_side = sb_raw.table.side_effect
    def _tbl_spy(name):
        tbl = orig_side(name)
        if name == "form_submissions":
            orig_insert = tbl.insert
            def _insert_spy(data):
                inserted.append(data)
                return orig_insert(data)
            tbl.insert = _insert_spy
        return tbl
    sb_raw.table.side_effect = _tbl_spy

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: USER_OWN
    monkeypatch.setattr("routers.report_forms.get_supabase", lambda: sb_raw)
    monkeypatch.setattr("routers.report_forms.now_kst",
                        lambda: __import__("datetime").datetime(2026, 10, 14))
    monkeypatch.setattr("routers.report_forms.serialize_business_datetime", lambda dt: str(dt))

    TestClient(app, raise_server_exceptions=False).post(
        "/report-forms/submissions",
        json={"factory_id": "factory-A1", "form_code": "OSHACT-FORM-002",
              "form_data": {}, "created_by": "attacker-id"}
    )

    assert inserted, "form_submissions.insert가 호출되지 않음"
    payload = inserted[0]
    # created_by는 token의 user id ("user-own-001"), body의 attacker-id가 아님
    assert payload.get("created_by") == "user-own-001", \
        f"created_by가 토큰에서 강제주입되지 않음: {payload.get('created_by')}"
    app.dependency_overrides.clear()
