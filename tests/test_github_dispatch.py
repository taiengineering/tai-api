"""GitHub Dispatch tests — WO-QA-CONTROL-PHASE2E-001.

GD-01: dispatch payload 구조 (ref / inputs.run_id / inputs.scenario_ids)
GD-02: QA_GITHUB_TOKEN 미설정 → RuntimeError
GD-03: scenario_ids 전달 확인 (comma-join)
GD-04: HTTP 4xx/5xx → RuntimeError (run 상태는 호출자 책임)
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
