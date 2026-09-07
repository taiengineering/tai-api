"""WO-SLACK-EVENT-HUB-001 PR-② · Q1..Q4 + F1..F5

Verifies writer hooks:
  · QUOTE_MANUAL_REQUESTED — routers/member_quotes.py::custom_request (sync handler → send_slack_sync)
  · FREE_DIAGNOSIS_COMPLETED — routers/diagnosis_integrated_leg.py::_run_leg_impl (async → await send_slack)

Dispatcher is mocked at the module import points (no real Slack calls).
DB / service calls are stubbed via monkeypatch (no real DB writes).
"""
from __future__ import annotations

import ast
import asyncio
import pathlib
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest


# ══════════════════════════════════════════════════════════════
# QUOTE hook — routers.member_quotes.custom_request
# ══════════════════════════════════════════════════════════════
class _FakeSvc:
    """Substitute for services.member_quote_svc.create_custom_quote."""
    def __init__(self, *, row: Dict[str, Any] | None = None, raise_exc: BaseException | None = None):
        self.row = row or {
            "id": "q-1", "quote_no": "TAI-Q-20260907-0001",
            "company_id": "c-1", "company_name": "Acme Co.",
            "contact_name": "홍길동", "service_type": "SAAS",
            "status_code": "REQUESTED", "source": "member_custom",
            "survey_data": {"member_custom": {"sector": "IND",
                                              "request_title": "T", "request_detail": "D"}},
        }
        self.raise_exc = raise_exc
        self.calls: List[Dict[str, Any]] = []

    def create_custom_quote(self, supabase, company_id, created_by, service_type, sector,
                            request_title, request_detail, contact_name=None):
        self.calls.append({"company_id": company_id, "service_type": service_type,
                           "sector": sector, "title": request_title})
        if self.raise_exc:
            raise self.raise_exc
        return self.row


class _RecordingDispatcher:
    """Records dispatcher.send_slack_sync calls."""
    def __init__(self, raise_exc: BaseException | None = None):
        self.calls: List[Dict[str, Any]] = []
        self.raise_exc = raise_exc

    def __call__(self, event_type, severity, title, detail="", channel_override=None, blocks=None):
        self.calls.append({"event_type": event_type, "severity": severity,
                           "title": title, "detail": detail,
                           "channel_override": channel_override, "blocks": blocks})
        if self.raise_exc:
            raise self.raise_exc


@pytest.fixture()
def quote_env(monkeypatch):
    from routers import member_quotes as mq
    # stub svc.create_custom_quote / auto svc
    fake = _FakeSvc()
    monkeypatch.setattr(mq.svc, "create_custom_quote", fake.create_custom_quote)
    # stub supabase / company scope
    monkeypatch.setattr(mq, "get_supabase", lambda: object())
    monkeypatch.setattr(mq, "_require_member_company", lambda cur, sb: "c-1")
    # stub dispatcher — patch the reference *inside slack_dispatcher module*,
    # since custom_request does `from services.slack_dispatcher import send_slack_sync`
    # (dynamic import — patches on services.slack_dispatcher.send_slack_sync work).
    disp = _RecordingDispatcher()
    monkeypatch.setattr("services.slack_dispatcher.send_slack_sync", disp)
    return mq, fake, disp


def _quote_body():
    from routers.member_quotes import CustomQuoteBody
    return CustomQuoteBody(service_type="SAAS", sector="IND",
                           request_title="T", request_detail="D", contact_name="홍길동")


def _auto_body():
    from routers.member_quotes import AutoQuoteBody
    return AutoQuoteBody(service_type="SAAS", sector="IND", tier_code="T1")


# Q1 — custom success → QUOTE_MANUAL_REQUESTED exactly 1 call, no channel_override
def test_q1_custom_success_emits_quote_manual_requested(quote_env):
    mq, fake, disp = quote_env
    resp = mq.custom_request(_quote_body(), current={"id": "u-1"})
    assert resp["status"] == "success"
    assert len(fake.calls) == 1
    assert len(disp.calls) == 1
    call = disp.calls[0]
    assert call["event_type"] == "QUOTE_MANUAL_REQUESTED"
    assert call["severity"] == "INFO"
    assert call["channel_override"] is None  # dispatcher routes via EVENT_TYPE_CHANNEL
    assert "Acme Co." in call["title"]
    assert "TAI-Q-20260907-0001" in call["detail"]


# Q2 — service raises MemberQuoteError → HTTPException, dispatcher NOT called
def test_q2_service_error_no_dispatch(monkeypatch):
    from fastapi import HTTPException
    from routers import member_quotes as mq
    fake = _FakeSvc(raise_exc=mq.svc.MemberQuoteError("BAD", "bad", 422))
    monkeypatch.setattr(mq.svc, "create_custom_quote", fake.create_custom_quote)
    monkeypatch.setattr(mq, "get_supabase", lambda: object())
    monkeypatch.setattr(mq, "_require_member_company", lambda cur, sb: "c-1")
    disp = _RecordingDispatcher()
    monkeypatch.setattr("services.slack_dispatcher.send_slack_sync", disp)

    with pytest.raises(HTTPException):
        mq.custom_request(_quote_body(), current={"id": "u-1"})
    assert disp.calls == []


# Q3 — auto_issue emits NO QUOTE_MANUAL_REQUESTED
def test_q3_auto_quote_no_dispatch(monkeypatch):
    from routers import member_quotes as mq

    row = {"id": "a-1", "quote_no": "TAI-Q-A", "company_id": "c-1", "source": "member_auto"}
    monkeypatch.setattr(mq.svc, "create_auto_quote",
                        lambda *a, **k: row)
    monkeypatch.setattr(mq, "get_supabase", lambda: object())
    monkeypatch.setattr(mq, "_require_member_company", lambda cur, sb: "c-1")
    disp = _RecordingDispatcher()
    monkeypatch.setattr("services.slack_dispatcher.send_slack_sync", disp)

    resp = mq.auto_issue(_auto_body(), current={"id": "u-1"})
    assert resp["status"] == "success"
    assert disp.calls == []  # no QUOTE_MANUAL for auto


# Q4 — dispatcher raises → custom_request STILL succeeds (Slack fail-safe)
def test_q4_dispatcher_failure_does_not_break_quote(monkeypatch):
    from routers import member_quotes as mq
    fake = _FakeSvc()
    monkeypatch.setattr(mq.svc, "create_custom_quote", fake.create_custom_quote)
    monkeypatch.setattr(mq, "get_supabase", lambda: object())
    monkeypatch.setattr(mq, "_require_member_company", lambda cur, sb: "c-1")
    disp = _RecordingDispatcher(raise_exc=RuntimeError("slack down"))
    monkeypatch.setattr("services.slack_dispatcher.send_slack_sync", disp)

    resp = mq.custom_request(_quote_body(), current={"id": "u-1"})
    assert resp["status"] == "success"
    assert resp["data"] == fake.row
    assert len(disp.calls) == 1  # attempted but raised


# ══════════════════════════════════════════════════════════════
# FREE_DIAG hook — routers.diagnosis_integrated_leg._run_leg_impl
# ══════════════════════════════════════════════════════════════
class _RecordingAsyncDispatcher:
    """Records async send_slack calls."""
    def __init__(self, raise_exc: BaseException | None = None):
        self.calls: List[Dict[str, Any]] = []
        self.raise_exc = raise_exc

    async def __call__(self, event_type, severity, title, detail="", channel_override=None, blocks=None):
        self.calls.append({"event_type": event_type, "severity": severity,
                           "title": title, "detail": detail,
                           "channel_override": channel_override, "blocks": blocks})
        if self.raise_exc:
            raise self.raise_exc


def _fake_run_diagnosis_factory(*, is_free: bool, raise_exc: BaseException | None = None):
    def _fake(*args, **kwargs):
        if raise_exc:
            raise raise_exc
        return {
            "public_token": "pt-1",
            "diagnosis_id": "d-1",
            "tier_code": "T1",
            "is_free": is_free,
            "expires_at": None,
            "free_remaining_after": 2,
            "result": {"leg_status": "OK", "applicable_count": 5},
        }
    return _fake


@pytest.fixture()
def leg_env(monkeypatch):
    import routers.diagnosis_integrated_leg as dl
    monkeypatch.setattr(dl, "LEG_PIPELINE_ENABLED", True)
    monkeypatch.setattr(dl, "is_enabled", lambda: True)
    monkeypatch.setattr(dl, "get_supabase", lambda: object())
    return dl


def _leg_body():
    """Minimal DiagnosisRunBody-shaped stub via SimpleNamespace (schema is complex)."""
    from types import SimpleNamespace
    return SimpleNamespace(form_data={"sector": "IND"})


# F1 — is_free=True → FREE_DIAGNOSIS_COMPLETED exactly 1 call
def test_f1_free_diagnosis_emits_completed(leg_env, monkeypatch):
    dl = leg_env
    monkeypatch.setattr(dl.diagnosis_integrated_svc, "run_diagnosis",
                        _fake_run_diagnosis_factory(is_free=True))
    disp = _RecordingAsyncDispatcher()
    monkeypatch.setattr("services.slack_dispatcher.send_slack", disp)

    resp = asyncio.run(dl._run_leg_impl(_leg_body(), current_user=None))
    assert resp["status"] == "success"
    assert resp["isFree"] is True
    assert len(disp.calls) == 1
    call = disp.calls[0]
    assert call["event_type"] == "FREE_DIAGNOSIS_COMPLETED"
    assert call["severity"] == "INFO"
    assert call["channel_override"] is None
    assert "IND" in call["title"]
    assert "pt-1" in call["detail"]


# F2 — is_free=False (paid) → dispatcher NOT called
def test_f2_paid_diagnosis_no_dispatch(leg_env, monkeypatch):
    dl = leg_env
    monkeypatch.setattr(dl.diagnosis_integrated_svc, "run_diagnosis",
                        _fake_run_diagnosis_factory(is_free=False))
    disp = _RecordingAsyncDispatcher()
    monkeypatch.setattr("services.slack_dispatcher.send_slack", disp)

    resp = asyncio.run(dl._run_leg_impl(_leg_body(), current_user=None))
    assert resp["isFree"] is False
    assert disp.calls == []


# F3 — run_diagnosis raises → dispatcher NOT called
def test_f3_diagnosis_failure_no_dispatch(leg_env, monkeypatch):
    from fastapi import HTTPException
    dl = leg_env
    monkeypatch.setattr(dl.diagnosis_integrated_svc, "run_diagnosis",
                        _fake_run_diagnosis_factory(is_free=True,
                                                   raise_exc=RuntimeError("engine boom")))
    disp = _RecordingAsyncDispatcher()
    monkeypatch.setattr("services.slack_dispatcher.send_slack", disp)

    with pytest.raises(RuntimeError):
        asyncio.run(dl._run_leg_impl(_leg_body(), current_user=None))
    assert disp.calls == []


# F4 — source-level assertion: await send_slack, no ensure_future / create_task
def test_f4_free_diag_awaits_no_fire_and_forget():
    src = pathlib.Path("routers/diagnosis_integrated_leg.py").read_text(encoding="utf-8")
    assert "await send_slack(" in src, "must await send_slack"
    assert "ensure_future" not in src, "no fire-and-forget"
    assert "create_task" not in src, "no fire-and-forget"
    # AST: the await sits inside _run_leg_impl (async fn)
    tree = ast.parse(src)
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.AsyncFunctionDef) and n.name == "_run_leg_impl"), None)
    assert fn is not None
    awaits = [n for n in ast.walk(fn) if isinstance(n, ast.Await)]
    # at least one await, and one of them targets `send_slack(...)`
    assert awaits, "_run_leg_impl must contain await(s)"
    def _is_send_slack_call(node):
        v = node.value
        return isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id == "send_slack"
    assert any(_is_send_slack_call(a) for a in awaits), \
        "must await send_slack(...) explicitly (no create_task/ensure_future)"


# F5 — dispatcher raises → _run_leg_impl STILL returns success
def test_f5_dispatcher_failure_does_not_break_diagnosis(leg_env, monkeypatch):
    dl = leg_env
    monkeypatch.setattr(dl.diagnosis_integrated_svc, "run_diagnosis",
                        _fake_run_diagnosis_factory(is_free=True))
    disp = _RecordingAsyncDispatcher(raise_exc=RuntimeError("slack down"))
    monkeypatch.setattr("services.slack_dispatcher.send_slack", disp)

    resp = asyncio.run(dl._run_leg_impl(_leg_body(), current_user=None))
    assert resp["status"] == "success"
    assert resp["isFree"] is True
    assert len(disp.calls) == 1
