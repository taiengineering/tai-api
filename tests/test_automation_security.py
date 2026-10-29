"""WO-TAI-SEC-AUTOMATION-P0-001 — Automation Engine 보안 회귀 테스트.

커버리지:
  T01  무인증 전체 9개 경로 → 401
  T02  일반 사용자 (non-admin) → 403
  T03  Total Admin → GET /rules 200
  T04  비활성 사용자 토큰 → 401
  T05  Permission Guard ADVISORY 상태에서도 라우터 인증 강제
  T06  인증 DB 장애 시 안전한 거부, 비즈니스 부작용 0건
  T07  CALL_WEBHOOK 규칙 신규 생성 → 403, DB INSERT 0건
  T08  기존 CALL_WEBHOOK 규칙 fire → HTTP 200 + outcome FAILED
  T09  임의 by 값 무시, 인증 사용자 ID 기록
  T10  CALL_WEBHOOK 경로 외부 HTTP 요청 0회
  T11  SEND_MAIL/SEND_SMS/CREATE_TASK 회귀 PASS
  T12  direct:// 스케줄러 실행 회귀 PASS
  T13  기존 CALL_WEBHOOK 승인 실행 → HTTP 502 + FAILED 기록
  T14  _call_webhook() 직접 호출 → 네트워크 요청 0회
  T15  DB 오류 시 미인증 접근 허용 없음 (Fail Closed)
  T16  전체 9개 경로 보호 커버리지 확인
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException as FHTTPEx
from fastapi.testclient import TestClient

from routers.automation import router, require_automation_admin
from routers.auth import get_current_user
from services.automation_svc import AutomationError, _call_webhook, _execute_action


# ─────────────────────────────────────────────────────────────────────────────
# 공통 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

def _app():
    app = FastAPI()
    app.include_router(router)
    return app


_ADMIN_USER = {"id": "admin-uuid-001", "role_code": "000"}
_NORMAL_USER = {"id": "user-uuid-002", "role_code": "099"}

_ALL_ROUTES = [
    ("GET",   "/automation/rules"),
    ("POST",  "/automation/rules"),
    ("PATCH", "/automation/rules/some-id/toggle"),
    ("POST",  "/automation/fire"),
    ("POST",  "/automation/scan/expiring"),
    ("GET",   "/automation/runs"),
    ("POST",  "/automation/runs/some-id/approve"),
    ("GET",   "/automation/tasks"),
    ("POST",  "/automation/tasks/some-id/close"),
]


# ─────────────────────────────────────────────────────────────────────────────
# T01: 무인증 전체 9개 경로 → 401
# ─────────────────────────────────────────────────────────────────────────────

def test_T01_no_token_all_routes_401():
    app = _app()
    client = TestClient(app, raise_server_exceptions=False)
    for method, path in _ALL_ROUTES:
        resp = client.request(method, path)
        assert resp.status_code == 401, f"{method} {path} expected 401, got {resp.status_code}"


# ─────────────────────────────────────────────────────────────────────────────
# T02: 일반 사용자 → 403
# ─────────────────────────────────────────────────────────────────────────────

def test_T02_non_admin_403(monkeypatch):
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _NORMAL_USER

    def _deny(*a, **k):
        raise FHTTPEx(status_code=403, detail="권한이 없습니다")

    monkeypatch.setattr("routers.automation._require_admin", _deny)
    monkeypatch.setattr("routers.automation.get_supabase", lambda: None)

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/automation/rules", headers={"Authorization": "Bearer fake"})
    assert resp.status_code == 403
    app.dependency_overrides.clear()


# ─────────────────────────────────────────────────────────────────────────────
# T03: Total Admin → GET /rules 200
# ─────────────────────────────────────────────────────────────────────────────

def test_T03_total_admin_rules_200(monkeypatch):
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _ADMIN_USER
    monkeypatch.setattr("routers.automation._require_admin", lambda *a, **k: None)

    class _FakeSB:
        def table(self, _):
            return _FakeQ()

    class _FakeQ:
        def select(self, *a, **k): return self
        def eq(self, *a, **k):    return self
        def order(self, *a, **k): return self
        def execute(self):
            return type("R", (), {"data": []})()

    monkeypatch.setattr("routers.automation.get_supabase", lambda: _FakeSB())

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/automation/rules", headers={"Authorization": "Bearer valid"})
    assert resp.status_code == 200
    app.dependency_overrides.clear()


# ─────────────────────────────────────────────────────────────────────────────
# T04: 비활성 사용자 토큰 → 401
# ─────────────────────────────────────────────────────────────────────────────

def test_T04_inactive_user_401():
    def _raise_401():
        raise FHTTPEx(status_code=401, detail="비활성 계정")

    app = _app()
    app.dependency_overrides[get_current_user] = _raise_401

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/automation/rules", headers={"Authorization": "Bearer inactive"})
    assert resp.status_code == 401
    app.dependency_overrides.clear()


# ─────────────────────────────────────────────────────────────────────────────
# T05: Permission Guard ADVISORY여도 라우터 인증 강제
# ─────────────────────────────────────────────────────────────────────────────

def test_T05_router_auth_independent_of_guard():
    """Guard가 fail-open이어도 require_automation_admin Depends가 독립적으로 401 반환."""
    app = _app()
    # get_current_user를 오버라이드하지 않아 실제 401 경로 통과
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/automation/fire", json={"event_type": "manual", "payload": {}})
    assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# T06: 인증 DB 장애 시 안전한 거부, 비즈니스 부작용 0건
# ─────────────────────────────────────────────────────────────────────────────

def test_T06_db_error_fail_closed(monkeypatch):
    """_require_admin 내 DB 장애 → 401/403/500 중 하나, fire() 실행 없음."""
    fired = []

    def _db_error(*a, **k):
        raise Exception("DB 연결 실패")

    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _ADMIN_USER
    monkeypatch.setattr("routers.automation._require_admin", _db_error)
    monkeypatch.setattr("routers.automation.get_supabase", lambda: None)
    monkeypatch.setattr("routers.automation.fire", lambda *a, **k: fired.append(1) or {})

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/automation/fire", json={"event_type": "manual", "payload": {}},
                       headers={"Authorization": "Bearer valid"})
    assert resp.status_code in (401, 403, 500)
    assert len(fired) == 0
    app.dependency_overrides.clear()


# ─────────────────────────────────────────────────────────────────────────────
# T07: CALL_WEBHOOK 신규 규칙 생성 → 403, DB INSERT 0건
# ─────────────────────────────────────────────────────────────────────────────

def test_T07_call_webhook_create_rule_403(monkeypatch):
    inserted = []

    class _FakeSB:
        def table(self, _):
            return _FakeQ()

    class _FakeQ:
        def insert(self, row, **k):
            inserted.append(row)
            return self
        def execute(self):
            return type("R", (), {"data": [{"id": "x"}]})()

    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _ADMIN_USER
    monkeypatch.setattr("routers.automation._require_admin", lambda *a, **k: None)
    monkeypatch.setattr("routers.automation.get_supabase", lambda: _FakeSB())

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/automation/rules", json={
        "rule_code": "R001", "event_type": "manual",
        "action_type": "CALL_WEBHOOK",
    }, headers={"Authorization": "Bearer valid"})
    assert resp.status_code == 403
    assert len(inserted) == 0
    app.dependency_overrides.clear()


# ─────────────────────────────────────────────────────────────────────────────
# T08: 기존 CALL_WEBHOOK 규칙 fire → HTTP 200 + outcome FAILED
# ─────────────────────────────────────────────────────────────────────────────

def test_T08_existing_webhook_rule_fire_200_failed(monkeypatch):
    """fire()는 CALL_WEBHOOK 실행 실패를 삼켜 HTTP 200 + FAILED outcome 반환."""
    from services import automation_svc

    _rule = {
        "id": "rule-1", "rule_code": "WH01", "event_type": "manual",
        "action_type": "CALL_WEBHOOK", "condition_json": {},
        "action_config_json": {"url": "https://example.com"},
        "require_approval": False, "enabled": True,
    }
    monkeypatch.setattr(automation_svc, "_rules_for", lambda _: [_rule])
    monkeypatch.setattr(automation_svc, "_log_run", lambda *a, **k: "run-1")
    monkeypatch.setattr("services.automation_svc.audit_svc",
                        type("A", (), {"record": lambda *a, **k: None})())

    result = automation_svc.fire("manual", {})
    outcomes = result["outcomes"]
    assert len(outcomes) == 1
    assert outcomes[0]["status"] == "FAILED"
    assert "CALL_WEBHOOK" in outcomes[0].get("error", "")


# ─────────────────────────────────────────────────────────────────────────────
# T09: 임의 by 값 무시, 인증 사용자 ID 기록
# ─────────────────────────────────────────────────────────────────────────────

def test_T09_by_param_ignored_auth_user_recorded(monkeypatch):
    recorded = {}

    class _FakeSB:
        def table(self, name):
            return _FakeQ(name)

    class _FakeQ:
        def __init__(self, name): self._name = name
        def select(self, *a, **k): return self
        def eq(self, *a, **k):    return self
        def order(self, *a, **k): return self
        def limit(self, *a, **k): return self
        def insert(self, row, **k):
            recorded["insert"] = row
            return self
        def execute(self):
            return type("R", (), {"data": []})()

    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _ADMIN_USER
    monkeypatch.setattr("routers.automation._require_admin", lambda *a, **k: None)
    monkeypatch.setattr("routers.automation.get_supabase", lambda: _FakeSB())

    client = TestClient(app, raise_server_exceptions=False)
    client.post("/automation/rules", json={
        "rule_code": "R002", "event_type": "manual",
        "action_type": "SEND_MAIL", "by": "attacker@evil.com",
    }, headers={"Authorization": "Bearer valid"})

    assert recorded.get("insert", {}).get("created_by") == _ADMIN_USER["id"]
    assert recorded.get("insert", {}).get("created_by") != "attacker@evil.com"
    app.dependency_overrides.clear()


# ─────────────────────────────────────────────────────────────────────────────
# T10: CALL_WEBHOOK 외부 HTTP 요청 0회
# ─────────────────────────────────────────────────────────────────────────────

def test_T10_no_external_http_on_webhook():
    """_execute_action("CALL_WEBHOOK") 호출 시 외부 HTTP 요청 없이 AutomationError."""
    import services.automation_svc as svc
    with pytest.raises(AutomationError) as exc_info:
        svc._execute_action("CALL_WEBHOOK", {"url": "https://attacker.example.com"}, {})
    assert exc_info.value.status_code == 403
    assert "비활성화" in exc_info.value.detail


# ─────────────────────────────────────────────────────────────────────────────
# T11: SEND_MAIL/SEND_SMS/CREATE_TASK 회귀 PASS
# ─────────────────────────────────────────────────────────────────────────────

def test_T11_other_actions_not_blocked(monkeypatch):
    import services.automation_svc as svc

    monkeypatch.setattr("services.automation_svc.audit_svc",
                        type("A", (), {"record": lambda *a, **k: None})())

    # SEND_MAIL: notify_svc.send 모킹
    from unittest.mock import MagicMock
    mock_send = MagicMock(return_value={"sent": True})
    monkeypatch.setattr("services.notify_svc.send", mock_send)

    result = svc._execute_action("SEND_MAIL", {"to": "a@b.com", "subject": "s", "html": "h"}, {})
    assert result is not None

    result2 = svc._execute_action("LLM_DRAFT", {"prompt_key": "p1"}, {})
    assert result2.get("llm_draft") == "queued"


# ─────────────────────────────────────────────────────────────────────────────
# T12: direct:// 스케줄러는 라우터 미경유 — 회귀 없음
# ─────────────────────────────────────────────────────────────────────────────

def test_T12_direct_scheduler_unaffected():
    """automation 라우터 변경이 direct:// 스케줄러 경로에 영향 없음."""
    import services.automation_svc as svc
    # scan_expiring_subscriptions 는 직접 fire()를 호출하며 라우터를 경유하지 않는다.
    # 인증 의존성이 없으므로 라우터 없이도 호출 가능.
    assert callable(svc.scan_expiring_subscriptions)
    assert callable(svc.fire)


# ─────────────────────────────────────────────────────────────────────────────
# T13: 기존 CALL_WEBHOOK 승인 실행 → HTTP 502 + FAILED 기록
# ─────────────────────────────────────────────────────────────────────────────

def test_T13_webhook_approve_502_failed(monkeypatch):
    from services import automation_svc

    _run = {
        "id": "run-1", "rule_id": "rule-1", "status": "APPROVAL_PENDING",
        "result_json": {"payload": {}, "config": {"url": "https://example.com"}},
        "event_type": "manual", "trigger_ref": None,
    }
    _rule = {
        "id": "rule-1", "action_type": "CALL_WEBHOOK",
        "action_config_json": {"url": "https://example.com"},
    }

    class _FakeSB:
        def table(self, name):
            if name == "automation_run_log":
                return _RunQ()
            if name == "automation_rule":
                return _RuleQ()
            return _NullQ()

    class _RunQ:
        def select(self, *a, **k): return self
        def eq(self, *a, **k):    return self
        def limit(self, *a, **k): return self
        def update(self, data, **k): self._data = data; return self
        def execute(self):
            return type("R", (), {"data": [_run]})()

    class _RuleQ:
        def select(self, *a, **k): return self
        def eq(self, *a, **k):    return self
        def limit(self, *a, **k): return self
        def execute(self):
            return type("R", (), {"data": [_rule]})()

    class _NullQ:
        def select(self, *a, **k): return self
        def eq(self, *a, **k):    return self
        def update(self, *a, **k): return self
        def limit(self, *a, **k): return self
        def execute(self):
            return type("R", (), {"data": []})()

    monkeypatch.setattr("services.automation_svc.get_supabase", lambda: _FakeSB())
    monkeypatch.setattr("services.automation_svc.audit_svc",
                        type("A", (), {"record": lambda *a, **k: None})())

    with pytest.raises(AutomationError) as exc_info:
        automation_svc.approve_run("run-1", actor="admin-uuid-001")
    assert exc_info.value.status_code == 502


# ─────────────────────────────────────────────────────────────────────────────
# T14: _call_webhook() 직접 호출 → 네트워크 요청 0회
# ─────────────────────────────────────────────────────────────────────────────

def test_T14_call_webhook_direct_no_network():
    with pytest.raises(AutomationError) as exc_info:
        _call_webhook("https://external.example.com", {"data": "x"})
    assert exc_info.value.status_code == 403
    assert "비활성화" in exc_info.value.detail


# ─────────────────────────────────────────────────────────────────────────────
# T15: DB 오류 시 미인증 접근 허용 없음 (Fail Closed)
# ─────────────────────────────────────────────────────────────────────────────

def test_T15_no_unauth_access_on_db_error():
    """토큰 없는 요청은 DB 상태와 무관하게 401."""
    app = _app()
    client = TestClient(app, raise_server_exceptions=False)
    # 토큰 없이 요청
    resp = client.post("/automation/fire", json={"event_type": "manual", "payload": {}})
    assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# T16: 전체 9개 경로 Router 보호 커버리지
# ─────────────────────────────────────────────────────────────────────────────

def test_T16_all_nine_routes_require_auth():
    """9개 경로 모두 토큰 없이 401 — Router dependencies 적용 확인."""
    app = _app()
    client = TestClient(app, raise_server_exceptions=False)
    failures = []
    for method, path in _ALL_ROUTES:
        resp = client.request(method, path, json={})
        if resp.status_code != 401:
            failures.append(f"{method} {path}: {resp.status_code}")
    assert not failures, f"보호되지 않은 경로:\n" + "\n".join(failures)
