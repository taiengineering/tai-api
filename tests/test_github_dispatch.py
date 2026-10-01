"""GitHub Dispatch tests — WO-QA-CONTROL-PHASE2E-001.

GD-01: dispatch payload 구조 (ref / inputs.run_id / inputs.scenario_ids)
GD-02: Token 없음 실패 (QA_GITHUB_TOKEN 미설정 → RuntimeError)
GD-03: Token 노출 없음 (payload / captured 헤더에 token 미포함)
GD-04: HTTP 4xx/5xx → RuntimeError (run 상태는 호출자 책임)
GD-05: scenario_ids comma-join + callback 연결 계약 (SCHEDULE run 거부 없음)
GD-06: Run ERROR 처리 (scheduler dispatch fail → _set_run_error 호출)
GD-07: Secret fail-close (token 미설정 즉시 실패, lazy 허용 금지)
"""
import asyncio
import os
import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

class _FakeResp:
    def __init__(self, status_code):
        self.status_code = status_code


class _FakeClient:
    def __init__(self, status_code=204):
        self._status_code = status_code
        self.captured: dict = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def post(self, url, *, json, headers):
        self.captured["url"]     = url
        self.captured["payload"] = json
        self.captured["headers"] = {k: v for k, v in headers.items() if k.lower() != "authorization"}
        return _FakeResp(self._status_code)


# ── GD-01: dispatch payload 구조 ──────────────────────────────────────────────

def test_GD01_dispatch_payload_structure(monkeypatch):
    """dispatch_qa_run이 올바른 ref / inputs payload를 전달한다."""
    monkeypatch.setenv("QA_GITHUB_TOKEN", "ghp-test-token")
    monkeypatch.setenv("QA_GITHUB_OWNER", "taiengineering")
    monkeypatch.setenv("QA_GITHUB_REPO",  "tai-qa")
    monkeypatch.setenv("QA_GITHUB_WORKFLOW", "run-qa.yml")
    monkeypatch.setenv("QA_GITHUB_REF", "main")

    client = _FakeClient(status_code=204)
    import importlib, services.github_dispatch_svc as mod
    importlib.reload(mod)
    monkeypatch.setattr("services.github_dispatch_svc.httpx.AsyncClient", lambda **k: client)

    asyncio.run(mod.dispatch_qa_run("run-001", ["P0-WWW-001", "P0-SAAS-001"]))

    payload = client.captured["payload"]
    assert payload["ref"] == "main"
    assert payload["inputs"]["run_id"] == "run-001"
    assert "P0-WWW-001" in payload["inputs"]["scenario_ids"]
    assert "P0-SAAS-001" in payload["inputs"]["scenario_ids"]


# ── GD-02: token 미설정 → RuntimeError ────────────────────────────────────────

def test_GD02_missing_token_raises(monkeypatch):
    """QA_GITHUB_TOKEN 미설정이면 RuntimeError."""
    monkeypatch.delenv("QA_GITHUB_TOKEN", raising=False)

    import importlib, services.github_dispatch_svc as mod
    importlib.reload(mod)

    with pytest.raises(RuntimeError, match="QA_GITHUB_TOKEN"):
        asyncio.run(mod.dispatch_qa_run("run-002", ["P0-001"]))


# ── GD-03: scenario_ids comma-join 확인 ────────────────────────────────────────

def test_GD03_scenario_ids_comma_join(monkeypatch):
    """scenario_ids가 comma 구분 문자열로 전달된다."""
    monkeypatch.setenv("QA_GITHUB_TOKEN", "ghp-test")
    monkeypatch.setenv("QA_GITHUB_OWNER", "taiengineering")
    monkeypatch.setenv("QA_GITHUB_REPO",  "tai-qa")
    monkeypatch.setenv("QA_GITHUB_WORKFLOW", "run-qa.yml")
    monkeypatch.setenv("QA_GITHUB_REF", "main")

    client = _FakeClient(status_code=204)
    import importlib, services.github_dispatch_svc as mod
    importlib.reload(mod)
    monkeypatch.setattr("services.github_dispatch_svc.httpx.AsyncClient", lambda **k: client)

    scenarios = ["A-001", "B-002", "C-003"]
    asyncio.run(mod.dispatch_qa_run("run-003", scenarios))

    raw = client.captured["payload"]["inputs"]["scenario_ids"]
    assert raw == "A-001,B-002,C-003"


# ── GD-03b: Token 노출 없음 ───────────────────────────────────────────────────

def test_GD03b_token_not_in_payload(monkeypatch):
    """dispatch payload에 token이 포함되지 않는다."""
    token = "ghp-super-secret-token-do-not-leak"
    monkeypatch.setenv("QA_GITHUB_TOKEN", token)
    monkeypatch.setenv("QA_GITHUB_OWNER", "taiengineering")
    monkeypatch.setenv("QA_GITHUB_REPO",  "tai-qa")
    monkeypatch.setenv("QA_GITHUB_WORKFLOW", "run-qa.yml")
    monkeypatch.setenv("QA_GITHUB_REF", "main")

    client = _FakeClient(status_code=204)
    import importlib, services.github_dispatch_svc as mod
    importlib.reload(mod)
    monkeypatch.setattr("services.github_dispatch_svc.httpx.AsyncClient", lambda **k: client)

    asyncio.run(mod.dispatch_qa_run("run-tok", ["P0-001"]))

    # payload JSON에 token 미포함
    import json
    payload_str = json.dumps(client.captured.get("payload", {}))
    assert token not in payload_str

    # 캡처된 헤더(Authorization 제외됨)에 token 미포함
    headers_str = json.dumps(client.captured.get("headers", {}))
    assert token not in headers_str


# ── GD-04: HTTP 실패 → RuntimeError ──────────────────────────────────────────

@pytest.mark.parametrize("status_code", [401, 403, 422, 500])
def test_GD04_http_failure_raises(monkeypatch, status_code):
    """HTTP 4xx/5xx → RuntimeError. 호출자가 run_status=ERROR 처리."""
    monkeypatch.setenv("QA_GITHUB_TOKEN", "ghp-test")
    monkeypatch.setenv("QA_GITHUB_OWNER", "taiengineering")
    monkeypatch.setenv("QA_GITHUB_REPO",  "tai-qa")
    monkeypatch.setenv("QA_GITHUB_WORKFLOW", "run-qa.yml")
    monkeypatch.setenv("QA_GITHUB_REF", "main")

    client = _FakeClient(status_code=status_code)
    import importlib, services.github_dispatch_svc as mod
    importlib.reload(mod)
    monkeypatch.setattr("services.github_dispatch_svc.httpx.AsyncClient", lambda **k: client)

    with pytest.raises(RuntimeError, match="GitHub dispatch failed"):
        asyncio.run(mod.dispatch_qa_run("run-004", ["P0-001"]))


# ── GD-05: Callback 연결 — SCHEDULE run 거부 없음 ────────────────────────────

def test_GD05_callback_accepts_schedule_run():
    """internal_qa callback은 trigger_type=SCHEDULE run도 거부하지 않는다.

    apply_results는 run_id 기반으로 동작하며 trigger_type 값으로 run을 거부하지 않는다.
    """
    import inspect, services.qa_control_svc as svc_mod
    fn_body = inspect.getsource(svc_mod.apply_results).split("def apply_results")[1]
    # trigger_type 기반 거부 조건이 없어야 함
    assert 'trigger_type == "MANUAL"' not in fn_body
    assert 'trigger_type != "SCHEDULE"' not in fn_body
    assert 'trigger_type not in' not in fn_body


# ── GD-06: Run ERROR 처리 — scheduler dispatch 실패 ──────────────────────────

def test_GD06_scheduler_dispatch_fail_sets_error():
    """scheduler_tick에서 dispatch 실패 시 run_status=ERROR로 업데이트된다."""
    import asyncio
    from unittest.mock import MagicMock, patch
    import services.qa_scheduler_svc as mod

    sched = {
        "id": "sched-1",
        "qa_item_id": "item-1",
        "frequency_type": "DAY",
        "frequency_value": 1,
        "next_run_at": "2026-01-01T00:00:00+00:00",
        "qa_items": {"id": "item-1", "scenario_id": "P0-001", "enabled": True},
    }

    updated: dict = {}

    def _table(name):
        m = MagicMock()
        if name == "qa_runs":
            m.insert.return_value.execute.return_value = MagicMock(data=[{"id": "run-err"}])
            def _update(data):
                updated.update(data)
                mm = MagicMock()
                mm.eq.return_value.execute.return_value = MagicMock(data=[{}])
                return mm
            m.update = _update
            m.delete.return_value.eq.return_value.execute.return_value = MagicMock()
        elif name == "qa_run_targets":
            m.insert.return_value.execute.return_value = MagicMock(data=[{}])
        elif name == "qa_schedules":
            m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{}])
        return m

    sb = MagicMock()
    sb.table.side_effect = _table

    async def _fail_dispatch(run_id, scenarios):
        raise RuntimeError("dispatch error")

    async def _run():
        with patch.object(mod, "_due_schedules", return_value=[sched]), \
             patch.object(mod, "_active_item_ids", return_value=frozenset()), \
             patch.object(mod, "dispatch_qa_run", _fail_dispatch):
            return await mod.scheduler_tick(sb)

    result = asyncio.run(_run())
    assert result["dispatch"] == "ERROR"
    assert updated.get("run_status") == "ERROR"


# ── GD-07: Secret fail-close ──────────────────────────────────────────────────

def test_GD07_secret_fail_close_immediate(monkeypatch):
    """token 미설정이면 즉시 RuntimeError — lazy 실패 허용 안 됨."""
    monkeypatch.delenv("QA_GITHUB_TOKEN", raising=False)
    import importlib, services.github_dispatch_svc as mod
    importlib.reload(mod)

    raised = False
    try:
        asyncio.run(mod.dispatch_qa_run("run-007", ["P0-001"]))
    except RuntimeError as e:
        raised = True
        assert "QA_GITHUB_TOKEN" in str(e)
    # HTTP 호출 없이 즉시 실패해야 함
    assert raised
