"""WO-TAI-DOC-SEC0-IMPLEMENT-001 — SEC0 Auth & Tenant Scope Test Suite

Coverage:
  T01  report-forms: no token → 401
  T02  report-forms/events/{factory_id}: cross-company factory → 404
  T03  report-forms/events/{factory_id}: own factory → 200
  T04  POST report-forms/events: own factory → 201/200
  T05  POST report-forms/events: cross-company factory → 404
  T06  POST report-forms/submissions: own factory → 200
  T07  POST report-forms/submissions: cross-company factory → 404
  T08  GET  report-forms/submissions/detail/{id}: own submission → 200
  T09  GET  report-forms/submissions/detail/{id}: cross-company submission → 404
  T10  document-runtime: no token → 401
  T11  document-runtime: no facility_id → 200 (pass through)
  T12  document-runtime: own facility_id → 200
  T13  document-runtime: cross-company facility_id → 403
  T14  POST report-forms/storage/upload-template: no token → 401
  T15  GET  report-forms/storage/signed-url/{id}: no token → 401

Production DB write = 0 (mock 전용).
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
FACILITY_PROFILE_A = {
    "id": "facility-001",
    "factory_id": "factory-A1",
    "facility_name": "테스트 시설",
}
FACILITY_PROFILE_B = {
    "id": "facility-002",
    "factory_id": "factory-B1",
    "facility_name": "타사 시설",
}


class _MockResult:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count or (len(data) if isinstance(data, list) else 0)


def _make_supabase_mock(factory_row=None, submission_row=None, event_row=None,
                        facility_row=None, insert_row=None, events_list=None,
                        submissions_list=None):
    """범용 Supabase mock 빌더."""
    sb = MagicMock()

    def _table_side_effect(table_name):
        tbl = MagicMock()
        q = MagicMock()
        tbl.select.return_value = q
        tbl.insert.return_value = MagicMock(execute=lambda: _MockResult([insert_row or {}]))
        tbl.update.return_value = MagicMock(execute=lambda: _MockResult([insert_row or {}]))

        q.eq.return_value = q
        q.neq.return_value = q
        q.order.return_value = q
        q.range.return_value = q
        q.limit.return_value = q
        q.in_.return_value = q
        q.maybe_single.return_value = q

        if table_name == "factories":
            q.execute.return_value = _MockResult([factory_row] if factory_row else [])
            q.single.return_value = MagicMock(
                execute=lambda: _MockResult(factory_row)
            )
        elif table_name == "form_submissions":
            if submissions_list is not None:
                q.execute.return_value = _MockResult(submissions_list, count=len(submissions_list))
            elif submission_row is not None:
                q.execute.return_value = _MockResult([submission_row])
            else:
                q.execute.return_value = _MockResult([])
            q.single.return_value = MagicMock(
                execute=lambda: _MockResult(submission_row)
            )
        elif table_name == "report_events":
            if events_list is not None:
                q.execute.return_value = _MockResult(events_list, count=len(events_list))
            elif event_row is not None:
                q.execute.return_value = _MockResult([event_row])
            else:
                q.execute.return_value = _MockResult([])
            q.single.return_value = MagicMock(
                execute=lambda: _MockResult(event_row)
            )
        elif table_name == "runtime_facility_profile":
            q.execute.return_value = _MockResult([facility_row] if facility_row else [])
            q.single.return_value = MagicMock(
                execute=lambda: _MockResult(facility_row)
            )
        else:
            q.execute.return_value = _MockResult([])
            q.single.return_value = MagicMock(execute=lambda: _MockResult(None))

        return tbl

    sb.table.side_effect = _table_side_effect
    return sb


# ─── helper: make report_forms test app ─────────────────────────────────────

def _make_report_forms_app(current_user_override, supabase_mock):
    from fastapi import FastAPI
    from routers.report_forms import router
    from routers.auth import get_current_user

    app = FastAPI()
    app.include_router(router)
    if current_user_override is not None:
        app.dependency_overrides[get_current_user] = lambda: current_user_override
    with patch("routers.report_forms.get_supabase", return_value=supabase_mock):
        yield app


# ─── T01: report-forms no token → 401 ──────────────────────────────────────

def test_T01_report_forms_no_token_401():
    """인증 헤더 없이 report-forms 호출 → 401"""
    from fastapi import FastAPI
    from routers.report_forms import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/report-forms/templates")
    assert resp.status_code == 401


# ─── T02: report-forms/events cross-company → 404 ──────────────────────────

def test_T02_events_cross_company_404(monkeypatch):
    """타사 factory_id 로 이벤트 조회 → 404"""
    from fastapi import FastAPI
    from routers.report_forms import router
    from routers.auth import get_current_user

    sb = _make_supabase_mock(factory_row={"id": "factory-A1", "company_id": "company-A"})

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: USER_OTHER

    monkeypatch.setattr("routers.report_forms.get_supabase", lambda: sb)

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/report-forms/events/factory-A1")
    assert resp.status_code == 404

    app.dependency_overrides.clear()


# ─── T03: report-forms/events own factory → 200 ─────────────────────────────

def test_T03_events_own_factory_200(monkeypatch):
    """자사 factory_id 로 이벤트 조회 → 200"""
    from fastapi import FastAPI
    from routers.report_forms import router
    from routers.auth import get_current_user

    sb = _make_supabase_mock(
        factory_row=FACTORY_A1,
        events_list=[EVENT_A],
    )

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: USER_OWN

    monkeypatch.setattr("routers.report_forms.get_supabase", lambda: sb)
    monkeypatch.setattr("routers.report_forms.business_today", lambda: __import__("datetime").date(2026, 10, 14))
    monkeypatch.setattr("routers.report_forms.now_kst", lambda: __import__("datetime").datetime(2026, 10, 14))
    monkeypatch.setattr("routers.report_forms.serialize_business_datetime", lambda dt: str(dt))

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/report-forms/events/factory-A1")
    assert resp.status_code == 200

    app.dependency_overrides.clear()


# ─── T04: POST events own factory → 200 ─────────────────────────────────────

def test_T04_create_event_own_factory_200(monkeypatch):
    """자사 factory_id 로 이벤트 생성 → 200"""
    from fastapi import FastAPI
    from routers.report_forms import router
    from routers.auth import get_current_user

    new_event = {**EVENT_A, "id": "event-new-001"}
    sb = _make_supabase_mock(factory_row=FACTORY_A1, insert_row=new_event)
    # master_building_legal_rules mock
    rules_mock = MagicMock()
    rules_mock.select.return_value.eq.return_value.limit.return_value.execute.return_value = _MockResult([])
    sb.table.side_effect = lambda t: (
        rules_mock if t == "master_building_legal_rules"
        else sb.table.side_effect.__wrapped__(t)
        if hasattr(sb.table.side_effect, "__wrapped__") else MagicMock()
    )
    # Rebuild with simpler approach
    sb2 = _make_supabase_mock(factory_row=FACTORY_A1, insert_row=new_event)

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: USER_OWN

    monkeypatch.setattr("routers.report_forms.get_supabase", lambda: sb2)
    monkeypatch.setattr("routers.report_forms.business_today", lambda: __import__("datetime").date(2026, 10, 14))
    monkeypatch.setattr("routers.report_forms.now_kst", lambda: __import__("datetime").datetime(2026, 10, 14))
    monkeypatch.setattr("routers.report_forms.serialize_business_datetime", lambda dt: str(dt))

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/report-forms/events", json={
        "factory_id": "factory-A1",
        "form_code": "OSHACT-FORM-002",
        "trigger_date": "2026-10-13",
        "due_days": 14,
    })
    assert resp.status_code == 200

    app.dependency_overrides.clear()


# ─── T05: POST events cross-company → 404 ────────────────────────────────────

def test_T05_create_event_cross_company_404(monkeypatch):
    """타사 factory_id 로 이벤트 생성 → 404"""
    from fastapi import FastAPI
    from routers.report_forms import router
    from routers.auth import get_current_user

    sb = _make_supabase_mock(factory_row=FACTORY_A1)

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: USER_OTHER

    monkeypatch.setattr("routers.report_forms.get_supabase", lambda: sb)

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/report-forms/events", json={
        "factory_id": "factory-A1",
        "form_code": "OSHACT-FORM-002",
        "trigger_date": "2026-10-13",
    })
    assert resp.status_code == 404

    app.dependency_overrides.clear()


# ─── T06: POST submissions own factory → 200 ─────────────────────────────────

def test_T06_create_submission_own_factory_200(monkeypatch):
    """자사 factory_id 로 서류 생성 → 200"""
    from fastapi import FastAPI
    from routers.report_forms import router
    from routers.auth import get_current_user

    sb = _make_supabase_mock(factory_row=FACTORY_A1, insert_row=SUBMISSION_A)

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: USER_OWN

    monkeypatch.setattr("routers.report_forms.get_supabase", lambda: sb)
    monkeypatch.setattr("routers.report_forms.now_kst", lambda: __import__("datetime").datetime(2026, 10, 14))
    monkeypatch.setattr("routers.report_forms.serialize_business_datetime", lambda dt: str(dt))

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/report-forms/submissions", json={
        "factory_id": "factory-A1",
        "form_code": "OSHACT-FORM-002",
        "form_data": {},
    })
    assert resp.status_code == 200

    app.dependency_overrides.clear()


# ─── T07: POST submissions cross-company → 404 ───────────────────────────────

def test_T07_create_submission_cross_company_404(monkeypatch):
    """타사 factory_id 로 서류 생성 → 404"""
    from fastapi import FastAPI
    from routers.report_forms import router
    from routers.auth import get_current_user

    sb = _make_supabase_mock(factory_row=FACTORY_A1)

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: USER_OTHER

    monkeypatch.setattr("routers.report_forms.get_supabase", lambda: sb)

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/report-forms/submissions", json={
        "factory_id": "factory-A1",
        "form_code": "OSHACT-FORM-002",
    })
    assert resp.status_code == 404

    app.dependency_overrides.clear()


# ─── T08: GET submissions/detail own → 200 ───────────────────────────────────

def test_T08_get_submission_detail_own_200(monkeypatch):
    """자사 서류 상세 조회 → 200"""
    from fastapi import FastAPI
    from routers.report_forms import router
    from routers.auth import get_current_user

    sb = _make_supabase_mock(factory_row=FACTORY_A1, submission_row=SUBMISSION_A)

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: USER_OWN

    monkeypatch.setattr("routers.report_forms.get_supabase", lambda: sb)

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/report-forms/submissions/detail/sub-001")
    assert resp.status_code == 200

    app.dependency_overrides.clear()


# ─── T09: GET submissions/detail cross-company → 404 ─────────────────────────

def test_T09_get_submission_detail_cross_company_404(monkeypatch):
    """타사 서류 상세 조회 → 404"""
    from fastapi import FastAPI
    from routers.report_forms import router
    from routers.auth import get_current_user

    sb = _make_supabase_mock(factory_row=FACTORY_A1, submission_row=SUBMISSION_A)

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: USER_OTHER

    monkeypatch.setattr("routers.report_forms.get_supabase", lambda: sb)

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/report-forms/submissions/detail/sub-001")
    assert resp.status_code == 404

    app.dependency_overrides.clear()


# ─── T10: document-runtime no token → 401 ────────────────────────────────────

def test_T10_document_runtime_no_token_401():
    """인증 헤더 없이 document-runtime 호출 → 401"""
    from fastapi import FastAPI
    from routers.document_runtime import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/document-runtime/some-doc-type")
    assert resp.status_code == 401


# ─── T11: document-runtime no facility_id → 200 (pass through) ───────────────

def test_T11_document_runtime_no_facility_200(monkeypatch):
    """facility_id 없이 document-runtime 호출 → 200 (소유권 검증 생략)"""
    from fastapi import FastAPI
    from routers.document_runtime import router
    from routers.auth import get_current_user

    mock_payload = {
        "document_type": "TEST_DOC",
        "tenant_context": {},
        "sections": [],
    }

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: USER_OWN

    monkeypatch.setattr(
        "routers.document_runtime.resolve_document_runtime",
        lambda dt, ctx: mock_payload,
    )
    monkeypatch.setattr(
        "routers.document_runtime.calculate_document_completeness",
        lambda sections: {"total": 0, "filled": 0, "pct": 0},
    )

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/document-runtime/TEST_DOC")
    assert resp.status_code == 200

    app.dependency_overrides.clear()


# ─── T12: document-runtime own facility → 200 ────────────────────────────────

def test_T12_document_runtime_own_facility_200(monkeypatch):
    """자사 facility_id 로 document-runtime 호출 → 200"""
    from fastapi import FastAPI
    from routers.document_runtime import router
    from routers.auth import get_current_user

    sb = _make_supabase_mock(factory_row=FACTORY_A1, facility_row=FACILITY_PROFILE_A)
    mock_payload = {
        "document_type": "TEST_DOC",
        "tenant_context": {},
        "sections": [],
    }

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: USER_OWN

    monkeypatch.setattr("routers.document_runtime.get_supabase", lambda: sb)
    monkeypatch.setattr(
        "routers.document_runtime.resolve_document_runtime",
        lambda dt, ctx: mock_payload,
    )
    monkeypatch.setattr(
        "routers.document_runtime.calculate_document_completeness",
        lambda sections: {"total": 0, "filled": 0, "pct": 0},
    )

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/document-runtime/TEST_DOC?facility_id=facility-001")
    assert resp.status_code == 200

    app.dependency_overrides.clear()


# ─── T13: document-runtime cross-company facility → 4xx (fail-closed) ────────

def test_T13_document_runtime_cross_company_facility_denied(monkeypatch):
    """타사 facility_id 로 document-runtime 호출 → 4xx (fail-closed; 존재 숨김=404)"""
    from fastapi import FastAPI
    from routers.document_runtime import router
    from routers.auth import get_current_user

    # factory-B1 belongs to company-B; USER_OWN is company-A
    sb = _make_supabase_mock(
        factory_row={"id": "factory-B1", "company_id": "company-B"},
        facility_row=FACILITY_PROFILE_B,
    )

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: USER_OWN

    monkeypatch.setattr("routers.document_runtime.get_supabase", lambda: sb)

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/document-runtime/TEST_DOC?facility_id=facility-002")
    # _ensure_factory_own raises 404 (existence-hiding) — fail-closed confirmed
    assert resp.status_code in (403, 404)

    app.dependency_overrides.clear()


# ─── T14: upload-template no token → 401 ─────────────────────────────────────

def test_T14_upload_template_no_token_401():
    """인증 헤더 없이 템플릿 업로드 → 401"""
    from fastapi import FastAPI
    from routers.report_forms import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/report-forms/storage/upload-template", json={
        "form_code": "OSHACT-FORM-002",
        "html_content": "<html></html>",
    })
    assert resp.status_code == 401


# ─── T15: signed-url no token → 401 ──────────────────────────────────────────

def test_T15_signed_url_no_token_401():
    """인증 헤더 없이 signed URL 요청 → 401"""
    from fastapi import FastAPI
    from routers.report_forms import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/report-forms/storage/signed-url/sub-001")
    assert resp.status_code == 401
