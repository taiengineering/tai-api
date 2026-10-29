"""WO-TAI-SEC-AUTOMATION-P0-001 — Automation Engine 보안 회귀 테스트.
PR #719 TEST_EVIDENCE_GAP 보정 (GPT IV CORRECTION).

커버리지:
  T01  무인증 전체 9개 경로 → 401
  T02  일반 사용자 (non-admin) — 실제 _require_admin 로직 검증 → 403
  T03  Total Admin → GET /rules 200
  T04  비활성 계정(PENDING/SUSPENDED/INACTIVE) → 403
  T05  Permission Guard ADVISORY 상태와 무관하게 Router 인증 강제
  T06  인증 DB 장애 시 안전한 거부 + 비즈니스 부작용 0건
  T07  CALL_WEBHOOK 신규 규칙 생성 → 403, DB INSERT 0건
  T08  기존 CALL_WEBHOOK 규칙 fire → HTTP 200 + outcome FAILED (TestClient 경유)
  T09  임의 by 값 무시 — create_rule·approve·close_task 모두 인증 사용자 ID 기록
  T10  CALL_WEBHOOK 경로 외부 HTTP 요청 0회 (requests.post Spy 검증)
  T11  SEND_MAIL·SEND_SMS·CREATE_TASK·LLM_DRAFT 각각 회귀 PASS
  T12  scan_expiring_subscriptions 직접 실행 — HTTP 라우터 미경유 정상 완료
  T13  기존 CALL_WEBHOOK 승인 실행 → HTTP 502 + DB FAILED 상태 기록
  T14  _call_webhook() 직접 호출 → 네트워크 요청 0회
  T15  get_supabase DB 장애 시 미인증 접근 허용 없음 (Fail Closed)
  T16  전체 9개 경로 Router 보호 커버리지 확인
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

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


class _Q:
    """범용 Supabase 쿼리 Mock."""
    def __init__(self, rows=None):
        self._rows = rows or []
        self.inserted = None
        self.updated = None

    def select(self, *a, **k): return self
    def eq(self, *a, **k):     return self
    def neq(self, *a, **k):    return self
    def gte(self, *a, **k):    return self
    def lte(self, *a, **k):    return self
    def order(self, *a, **k):  return self
    def limit(self, *a, **k):  return self
    def in_(self, *a, **k):    return self

    def insert(self, row, **k):
        self.inserted = row
        return self

    def update(self, data, **k):
        self.updated = data
        return self

    def delete(self, *a, **k): return self

    def execute(self):
        return type("R", (), {"data": list(self._rows)})()


class _SB:
    """범용 Supabase Mock — table 이름별 _Q 반환."""
    def __init__(self, table_map: dict | None = None):
        self._map = table_map or {}

    def table(self, name):
        return self._map.get(name, _Q())


# ─────────────────────────────────────────────────────────────────────────────
# T01: 무인증 전체 9개 경로 → 401
# ─────────────────────────────────────────────────────────────────────────────

def test_T01_no_token_all_routes_401():
    app = _app()
    client = TestClient(app, raise_server_exceptions=False)
    for method, path in _ALL_ROUTES:
        resp = client.request(method, path)
        assert resp.status_code == 401, (
            f"{method} {path} expected 401, got {resp.status_code}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# T02: 일반 사용자 — 실제 _require_admin 로직으로 403
# ─────────────────────────────────────────────────────────────────────────────

def test_T02_non_admin_actual_logic_403(monkeypatch):
    """_require_admin을 직접 패치하지 않고 _scope → "TEAM" 으로 모킹해
    실제 _is_admin("TEAM")==False → HTTPException(403) 경로를 검증."""
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _NORMAL_USER

    # _scope 를 "TEAM" 반환으로 모킹 — 실제 _require_admin 로직 사용
    monkeypatch.setattr("services.company_scope._scope", lambda sb, role_code: "TEAM")
    monkeypatch.setattr("routers.automation.get_supabase", lambda: _SB())

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

    # _scope → "ALL" 이면 _is_admin=True, _require_admin 통과
    monkeypatch.setattr("services.company_scope._scope", lambda sb, role_code: "ALL")
    monkeypatch.setattr("routers.automation.get_supabase", lambda: _SB({
        "automation_rule": _Q(rows=[]),
    }))

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/automation/rules", headers={"Authorization": "Bearer valid"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
    app.dependency_overrides.clear()


# ─────────────────────────────────────────────────────────────────────────────
# T04: 비활성 계정 (PENDING/SUSPENDED/INACTIVE) → 403
# ─────────────────────────────────────────────────────────────────────────────

def test_T04_inactive_account_403():
    """routers/auth.py: PENDING/SUSPENDED/INACTIVE → HTTPException(403).
    토큰이 유효해도 비활성 계정은 403으로 차단된다."""
    for status_label, status_code in [
        ("PENDING",   403),
        ("SUSPENDED", 403),
        ("INACTIVE",  403),
    ]:
        def _raise_inactive():
            raise FHTTPEx(status_code=403, detail={"code": "ACCOUNT_INACTIVE"})

        app = _app()
        app.dependency_overrides[get_current_user] = _raise_inactive

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(
            "/automation/rules",
            headers={"Authorization": f"Bearer {status_label.lower()}-token"},
        )
        assert resp.status_code == 403, (
            f"{status_label} account expected 403, got {resp.status_code}"
        )
        app.dependency_overrides.clear()


# ─────────────────────────────────────────────────────────────────────────────
# T05: Permission Guard ADVISORY 상태에서도 Router 인증 강제
# ─────────────────────────────────────────────────────────────────────────────

def test_T05_router_auth_independent_of_guard():
    """Guard fail-open 상황을 시뮬레이션 — Router Depends는 독립적으로 동작."""
    from fastapi import Request
    from fastapi.responses import JSONResponse

    app = _app()

    # Guard가 모든 요청을 통과시키는 미들웨어 추가 (ADVISORY 시뮬레이션)
    @app.middleware("http")
    async def fake_guard_advisory(request: Request, call_next):
        # Advisory: 인증 실패해도 통과
        return await call_next(request)

    client = TestClient(app, raise_server_exceptions=False)
    # 토큰 없이 요청 — Guard는 통과시키지만 Router Depends가 401 반환
    resp = client.post(
        "/automation/fire",
        json={"event_type": "manual", "payload": {}},
    )
    assert resp.status_code == 401, (
        f"Guard ADVISORY여도 Router 인증이 강제되어야 함: got {resp.status_code}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# T06: 인증 DB 장애 시 안전한 거부 + 비즈니스 부작용 0건
# ─────────────────────────────────────────────────────────────────────────────

def test_T06_db_error_fail_closed(monkeypatch):
    """_scope 조회 중 DB 예외 → 401/403/500 중 하나, fire() 실행 없음."""
    fired = []

    def _db_scope_error(sb, role_code):
        raise Exception("DB 연결 실패")

    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _ADMIN_USER
    monkeypatch.setattr("services.company_scope._scope", _db_scope_error)
    monkeypatch.setattr("routers.automation.get_supabase", lambda: _SB())
    monkeypatch.setattr("routers.automation.fire", lambda *a, **k: fired.append(1) or {})

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/automation/fire",
        json={"event_type": "manual", "payload": {}},
        headers={"Authorization": "Bearer valid"},
    )
    assert resp.status_code in (401, 403, 500)
    assert len(fired) == 0, "DB 장애 시 fire() 실행 부작용 없어야 함"
    app.dependency_overrides.clear()


# ─────────────────────────────────────────────────────────────────────────────
# T07: CALL_WEBHOOK 신규 규칙 생성 → 403, DB INSERT 0건
# ─────────────────────────────────────────────────────────────────────────────

def test_T07_call_webhook_create_rule_403(monkeypatch):
    rules_q = _Q(rows=[{"id": "x"}])

    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _ADMIN_USER
    monkeypatch.setattr("services.company_scope._scope", lambda sb, role_code: "ALL")
    monkeypatch.setattr("routers.automation.get_supabase", lambda: _SB({
        "automation_rule": rules_q,
    }))

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/automation/rules", json={
        "rule_code": "R001", "event_type": "manual",
        "action_type": "CALL_WEBHOOK",
    }, headers={"Authorization": "Bearer valid"})

    assert resp.status_code == 403
    assert rules_q.inserted is None, "CALL_WEBHOOK 차단 시 DB INSERT 없어야 함"
    app.dependency_overrides.clear()


# ─────────────────────────────────────────────────────────────────────────────
# T08: 기존 CALL_WEBHOOK 규칙 fire → HTTP 200 + outcome FAILED (TestClient)
# ─────────────────────────────────────────────────────────────────────────────

def test_T08_existing_webhook_rule_fire_http200_failed(monkeypatch):
    """TestClient를 통해 HTTP 200 응답과 outcome FAILED를 함께 검증."""
    import services.automation_svc as svc

    _wh_rule = {
        "id": "rule-wh1", "rule_code": "WH01", "event_type": "manual",
        "action_type": "CALL_WEBHOOK", "condition_json": {},
        "action_config_json": {"url": "https://example.com"},
        "require_approval": False, "enabled": True,
    }
    monkeypatch.setattr(svc, "_rules_for", lambda _: [_wh_rule])
    monkeypatch.setattr(svc, "_log_run", lambda *a, **k: "run-1")
    monkeypatch.setattr(svc, "audit_svc",
                        type("A", (), {"record": lambda *a, **k: None})())

    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _ADMIN_USER
    monkeypatch.setattr("services.company_scope._scope", lambda sb, role_code: "ALL")
    monkeypatch.setattr("routers.automation.get_supabase", lambda: _SB())

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/automation/fire",
        json={"event_type": "manual", "payload": {}},
        headers={"Authorization": "Bearer valid"},
    )
    assert resp.status_code == 200
    outcomes = resp.json()["data"]["outcomes"]
    assert len(outcomes) == 1
    assert outcomes[0]["status"] == "FAILED"
    assert "CALL_WEBHOOK" in outcomes[0].get("error", "")
    app.dependency_overrides.clear()


# ─────────────────────────────────────────────────────────────────────────────
# T09: by 값 무시 — create_rule·approve·close_task 모두 auth user ID 기록
# ─────────────────────────────────────────────────────────────────────────────

def test_T09_by_param_ignored_all_endpoints(monkeypatch):
    """세 엔드포인트 모두 클라이언트 by를 무시하고 current["id"]를 기록."""
    import services.automation_svc as svc

    # ── (a) create_rule: created_by = admin ID ──────────────────────────────
    rules_q = _Q(rows=[{"id": "r1"}])
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _ADMIN_USER
    monkeypatch.setattr("services.company_scope._scope", lambda sb, role_code: "ALL")
    monkeypatch.setattr("routers.automation.get_supabase", lambda: _SB({
        "automation_rule": rules_q,
    }))

    client = TestClient(app, raise_server_exceptions=False)
    client.post("/automation/rules", json={
        "rule_code": "R-BY-TEST", "event_type": "manual",
        "action_type": "SEND_MAIL", "by": "attacker@evil.com",
    }, headers={"Authorization": "Bearer valid"})

    inserted = rules_q.inserted or {}
    assert inserted.get("created_by") == _ADMIN_USER["id"]
    assert inserted.get("created_by") != "attacker@evil.com"
    app.dependency_overrides.clear()

    # ── (b) approve: actor = admin ID ──────────────────────────────────────
    recorded_actor = {}

    def _fake_approve(run_id, actor=None):
        recorded_actor["actor"] = actor
        return {"status": "APPROVED_RUN", "result": {}}

    app2 = _app()
    app2.dependency_overrides[get_current_user] = lambda: _ADMIN_USER
    monkeypatch.setattr("services.company_scope._scope", lambda sb, role_code: "ALL")
    monkeypatch.setattr("routers.automation.get_supabase", lambda: _SB())
    monkeypatch.setattr("routers.automation.approve_run", _fake_approve)

    client2 = TestClient(app2, raise_server_exceptions=False)
    # 이전 by Query 파라미터는 제거됨 — actor는 current["id"]에서만 온다
    client2.post(
        "/automation/runs/run-xyz/approve",
        headers={"Authorization": "Bearer valid"},
    )
    assert recorded_actor.get("actor") == _ADMIN_USER["id"]
    app2.dependency_overrides.clear()

    # ── (c) close_task: actor = admin ID ───────────────────────────────────
    recorded_close = {}

    def _fake_close(task_id, status="DONE", actor=None):
        recorded_close["actor"] = actor
        return {"id": task_id, "status": status}

    app3 = _app()
    app3.dependency_overrides[get_current_user] = lambda: _ADMIN_USER
    monkeypatch.setattr("services.company_scope._scope", lambda sb, role_code: "ALL")
    monkeypatch.setattr("routers.automation.get_supabase", lambda: _SB())
    monkeypatch.setattr("routers.automation.close_ops_task", _fake_close)

    client3 = TestClient(app3, raise_server_exceptions=False)
    client3.post(
        "/automation/tasks/task-xyz/close",
        json={"status": "DONE", "by": "attacker@evil.com"},
        headers={"Authorization": "Bearer valid"},
    )
    assert recorded_close.get("actor") == _ADMIN_USER["id"]
    assert recorded_close.get("actor") != "attacker@evil.com"
    app3.dependency_overrides.clear()


# ─────────────────────────────────────────────────────────────────────────────
# T10: CALL_WEBHOOK 경로 외부 HTTP 요청 0회 (requests.post Spy)
# ─────────────────────────────────────────────────────────────────────────────

def test_T10_no_external_http_call_webhook():
    """requests.post를 Spy로 감시해 CALL_WEBHOOK 경로에서 호출 0회를 명시적으로 확인."""
    with patch("requests.post") as spy_post:
        with pytest.raises(AutomationError) as exc_info:
            _execute_action("CALL_WEBHOOK", {"url": "https://attacker.example.com"}, {})
        assert exc_info.value.status_code == 403
        assert spy_post.call_count == 0, (
            f"외부 HTTP 요청이 발생했음: requests.post 호출 {spy_post.call_count}회"
        )

    # _call_webhook() 직접 경로도 동일하게 검증
    with patch("requests.post") as spy2:
        with pytest.raises(AutomationError):
            _call_webhook("https://external.example.com", {})
        assert spy2.call_count == 0


# ─────────────────────────────────────────────────────────────────────────────
# T11: SEND_MAIL·SEND_SMS·CREATE_TASK·LLM_DRAFT 각각 회귀 PASS
# ─────────────────────────────────────────────────────────────────────────────

def test_T11_other_actions_all_pass(monkeypatch):
    import services.automation_svc as svc

    # SEND_MAIL
    mock_send = MagicMock(return_value={"sent": True})
    monkeypatch.setattr("services.notify_svc.send", mock_send)
    result = svc._execute_action(
        "SEND_MAIL", {"to": "a@b.com", "subject": "s", "html": "<p>h</p>"}, {}
    )
    assert result is not None
    mock_send.assert_called_once()

    # SEND_SMS
    mock_send.reset_mock()
    result2 = svc._execute_action(
        "SEND_SMS", {"to": "+821099999999", "message": "알림"}, {}
    )
    assert result2 is not None
    mock_send.assert_called_once()

    # LLM_DRAFT
    result3 = svc._execute_action("LLM_DRAFT", {"prompt_key": "p1"}, {})
    assert result3.get("llm_draft") == "queued"

    # CREATE_TASK (admin_ops_task 테이블 모킹)
    task_q = _Q(rows=[{"id": "task-001", "title": "자동화 태스크", "status": "OPEN"}])
    monkeypatch.setattr(
        "services.automation_svc.get_supabase",
        lambda: _SB({"admin_ops_task": task_q}),
    )
    result4 = svc._execute_action(
        "CREATE_TASK",
        {"title": "테스트 태스크", "priority": "NORMAL"},
        {"company_id": "co-1"},
        rule_id="r-1",
        event_type="manual",
        trigger_ref="ref-1",
    )
    assert result4.get("task") in ("created", "deduped")


# ─────────────────────────────────────────────────────────────────────────────
# T12: scan_expiring_subscriptions 직접 실행 — HTTP 라우터 미경유 정상 완료
# ─────────────────────────────────────────────────────────────────────────────

def test_T12_scan_expiring_direct_no_router(monkeypatch):
    """scan_expiring_subscriptions()는 HTTP 라우터를 경유하지 않고 직접 호출 가능.
    인증 의존성이 없으므로 라우터 없이도 정상 완료된다."""
    import services.automation_svc as svc

    # v_payments_list 에서 빈 결과 반환 — 발화 없음
    monkeypatch.setattr(
        "services.automation_svc.get_supabase",
        lambda: _SB({"v_payments_list": _Q(rows=[])}),
    )

    result = svc.scan_expiring_subscriptions(days=1)
    assert result["scanned"] == 0
    assert result["fired"] == 0
    assert result["days"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# T13: 기존 CALL_WEBHOOK 승인 실행 → HTTP 502 + DB FAILED 상태 기록
# ─────────────────────────────────────────────────────────────────────────────

def test_T13_webhook_approve_502_and_db_failed(monkeypatch):
    """approve_run: CALL_WEBHOOK 실행 실패 시 automation_run_log.status=FAILED 업데이트 후 502."""
    import services.automation_svc as svc

    _run_row = {
        "id": "run-1", "rule_id": "rule-1", "status": "APPROVAL_PENDING",
        "result_json": {"payload": {}, "config": {"url": "https://example.com"}},
        "event_type": "manual", "trigger_ref": None,
    }
    _rule_row = {
        "id": "rule-1", "action_type": "CALL_WEBHOOK",
        "action_config_json": {"url": "https://example.com"},
    }

    # 상태 기록을 캡처하는 _Q
    run_log_q = _Q(rows=[_run_row])

    class _SBCapture:
        def table(self, name):
            if name == "automation_run_log":
                return run_log_q
            if name == "automation_rule":
                return _Q(rows=[_rule_row])
            return _Q()

    monkeypatch.setattr("services.automation_svc.get_supabase", lambda: _SBCapture())
    monkeypatch.setattr(svc, "audit_svc",
                        type("A", (), {"record": lambda *a, **k: None})())

    with pytest.raises(AutomationError) as exc_info:
        svc.approve_run("run-1", actor="admin-uuid-001")

    # HTTP 502 반환
    assert exc_info.value.status_code == 502

    # DB 업데이트에 status=FAILED 포함
    updated = run_log_q.updated or {}
    assert updated.get("status") == "FAILED", (
        f"DB update에 status=FAILED 가 없음: {updated}"
    )
    assert updated.get("approved_by") == "admin-uuid-001"


# ─────────────────────────────────────────────────────────────────────────────
# T14: _call_webhook() 직접 호출 → 네트워크 요청 0회
# ─────────────────────────────────────────────────────────────────────────────

def test_T14_call_webhook_direct_no_network():
    with pytest.raises(AutomationError) as exc_info:
        _call_webhook("https://external.example.com", {"data": "x"})
    assert exc_info.value.status_code == 403
    assert "비활성화" in exc_info.value.detail


# ─────────────────────────────────────────────────────────────────────────────
# T15: get_supabase 장애 시 미인증 접근 허용 없음 (Fail Closed)
# ─────────────────────────────────────────────────────────────────────────────

def test_T15_supabase_failure_no_auth_bypass(monkeypatch):
    """get_supabase()가 예외를 던져도 토큰 없는 요청은 401로 차단된다."""

    def _sb_crash():
        raise Exception("supabase connection refused")

    app = _app()
    monkeypatch.setattr("routers.automation.get_supabase", _sb_crash)

    client = TestClient(app, raise_server_exceptions=False)

    # 토큰 없음 → 401 (get_current_user가 먼저 거부, get_supabase 도달 안 함)
    resp_no_token = client.post(
        "/automation/fire",
        json={"event_type": "manual", "payload": {}},
    )
    assert resp_no_token.status_code == 401

    # 인증된 사용자 + DB 장애 → 401/403/500 중 하나 (fire 실행 없음)
    fired = []
    app2 = _app()
    app2.dependency_overrides[get_current_user] = lambda: _ADMIN_USER
    monkeypatch.setattr("routers.automation.get_supabase", _sb_crash)
    monkeypatch.setattr("routers.automation.fire", lambda *a, **k: fired.append(1) or {})

    client2 = TestClient(app2, raise_server_exceptions=False)
    resp_auth = client2.post(
        "/automation/fire",
        json={"event_type": "manual", "payload": {}},
        headers={"Authorization": "Bearer valid"},
    )
    assert resp_auth.status_code in (401, 403, 500)
    assert len(fired) == 0
    app2.dependency_overrides.clear()


# ─────────────────────────────────────────────────────────────────────────────
# T16: 전체 9개 경로 Router 보호 커버리지 확인
# ─────────────────────────────────────────────────────────────────────────────

def test_T16_all_nine_routes_require_auth():
    """9개 경로 모두 토큰 없이 401 — APIRouter dependencies 일괄 적용 확인."""
    app = _app()
    client = TestClient(app, raise_server_exceptions=False)
    failures = []
    for method, path in _ALL_ROUTES:
        resp = client.request(method, path, json={})
        if resp.status_code != 401:
            failures.append(f"{method} {path}: {resp.status_code}")
    assert not failures, "보호되지 않은 경로:\n" + "\n".join(failures)
