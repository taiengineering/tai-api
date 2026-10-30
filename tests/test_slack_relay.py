"""WO-TAI-SLACK-BOT-UNIFIED-001-R3 — Slack Events Relay 파일럿 테스트 T01~T25 + R01~R14.

커버리지:
  T01  SLACK_SIGNING_SECRET 미설정 → 500
  T02  서명 없음(헤더 누락) → 403
  T03  서명 만료(타임스탬프 > 300s) → 403
  T04  유효 서명 + url_verification → 200 {"challenge": ...}
  T05  필수 설정 미설정 → 200 ok=True, 발송 안 함 (COR-05 Fail Closed)
  T06  team_id 불일치 → 200 ok=True (discard)
  T07  api_app_id 불일치 → 200 ok=True (discard)
  T08  message 외 이벤트 타입(reaction_added) → 200 ok=True (skip)
  T09  message + subtype(bot_message) → 200 ok=True (skip)
  T10  미승인 발신자 → 200 ok=True (discard)
  T11  미등록 릴레이 채널 → 200 ok=True (discard)
  T12  빈 텍스트 메시지 → 200 ok=True (skip)
  T13  정상 이벤트 → DB INSERT 1회, BackgroundTask 등록
  T14  중복 이벤트(ON CONFLICT) → DB INSERT accepted=False, BackgroundTask 없음
  T15  DB accept_relay_event 예외 → 503
  T16  PENDING → CLAIMED: claim_token 발급, 0 행 반환 시 None
  T17  CLAIMED → SENDING: claim_token 불일치 시 False
  T18  SENDING → SENT: Slack ok=true → status SENT
  T19  DB 복구 — PENDING 행 존재 시 run_relay_recovery_once 처리
  T20  Slack API timeout → UNKNOWN (자동 재시도 금지)
  T21  두 Worker 동시 claim: 한 쪽만 성공 (CAS)
  T22  claim_token 불일치 → _finish 0행 반환, 상태 변경 없음
  T23  PENDING/RETRY 복구 Worker: 빈 큐 → 처리 0건
  T24  Slack HTTP 200 + ok=false (채널 없음) → FAILED_PERMANENT
  T25  Bot token이 로그에 출력되지 않는 것 확인 (코드 정적 검증)
  REG1 기존 Automation 회귀: 인증 없는 /automation/rules → 401
  REG2 기존 Permission Guard is_public: /slack/events 포함 확인
  R01  COR-03: PENDING + next_attempt_at=NULL → Claim 가능
  R02  COR-02/03: RETRY + 도래한 next_attempt_at → Claim 가능
  R03  COR-03: RETRY + 미래 next_attempt_at → Claim 거부
  R04  COR-04: stale CLAIMED/SENDING 복구 — RETRY/UNKNOWN 전환 호출
  R06  중복 event_id CAS 펜싱 — accept=False → BackgroundTask 미등록
  R07  COR-07: 429 Retry-After=47s → _future_sec(47) 호출 (분 변환 없음)
  R08  COR-05: APP_ID/TEAM_ID 미설정 → accept_relay_event 호출 없음
  R09  COR-05: type != event_callback → 접수 거부
  R10  COR-05: event.bot_id 존재 → 접수 거부
  R11  COR-05: event_id 누락 → UUID 대체 금지, 접수 거부
  R12  COR-06: SLACK_BOT_TOKEN1 미설정 → SLACK_BOT_TOKEN 폴백 없이 RETRY
  R13  P0 회귀: slack_events + automation 라우터 공존
  R14  R3 라우터 속성(prefix/tags) 확인
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers.slack_events import router, _load_config, _parse_channel_map
from services.slack_relay_svc import (
    _claim, _finish, _get_bot_token, _retry_delay_sec, _start_sending,
    accept_relay_event, process_relay_event, recover_stale_claimed,
    run_relay_recovery_once,
)


# ─────────────────────────────────────────────────────────────────────────────
# 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

def _app():
    app = FastAPI()
    app.include_router(router)
    return app


_SIGNING_SECRET = "test-signing-secret-32bytes-long!!"
_APP_ID = "A0123APP456"
_TEAM_ID = "T0123TEAM"
_SENDER_ID = "U0APPROVED01"
_RELAY_CHANNEL = "G0RELAY0001"
_TARGET_CHANNEL = "C0TARGET001"
_CHANNEL_MAP_JSON = json.dumps({_RELAY_CHANNEL: _TARGET_CHANNEL})


def _sign(secret: str, body: bytes, ts: int | None = None) -> tuple[str, str]:
    ts = ts or int(time.time())
    sig_base = f"v0:{ts}:{body.decode('utf-8')}"
    digest = hmac.new(secret.encode("utf-8"), sig_base.encode("utf-8"), hashlib.sha256).hexdigest()
    return str(ts), f"v0={digest}"


def _valid_headers(body: bytes, ts: int | None = None) -> dict[str, str]:
    ts_str, sig = _sign(_SIGNING_SECRET, body, ts)
    return {
        "x-slack-request-timestamp": ts_str,
        "x-slack-signature": sig,
        "content-type": "application/json",
    }


def _make_event_body(
    event_id: str = "Ev001TEST",
    sender_id: str = _SENDER_ID,
    relay_channel: str = _RELAY_CHANNEL,
    text: str = "hello relay",
    subtype: str | None = None,
    event_type: str = "message",
    team_id: str = _TEAM_ID,
    app_id: str = _APP_ID,
    bot_id: str | None = None,
) -> bytes:
    event: dict[str, Any] = {
        "type": event_type, "user": sender_id, "channel": relay_channel,
        "text": text, "ts": "1000.0001",
    }
    if subtype:
        event["subtype"] = subtype
    if bot_id:
        event["bot_id"] = bot_id
    payload: dict[str, Any] = {
        "type": "event_callback",
        "event_id": event_id,
        "team_id": team_id,
        "api_app_id": app_id,
        "event": event,
    }
    return json.dumps(payload).encode("utf-8")


def _env(**kwargs):
    defaults = {
        "SLACK_SIGNING_SECRET": _SIGNING_SECRET,
        "SLACK_RELAY_APP_ID": _APP_ID,
        "SLACK_RELAY_TEAM_ID": _TEAM_ID,
        "SLACK_RELAY_ALLOWED_SENDER_IDS": _SENDER_ID,
        "SLACK_RELAY_CHANNEL_MAP": _CHANNEL_MAP_JSON,
    }
    defaults.update(kwargs)
    return {k: v for k, v in defaults.items() if v is not None}


# ─────────────────────────────────────────────────────────────────────────────
# T01: SLACK_SIGNING_SECRET 미설정 → 500
# ─────────────────────────────────────────────────────────────────────────────
def test_t01_no_signing_secret():
    body = b'{"type":"event_callback"}'
    with patch.dict("os.environ", _env(SLACK_SIGNING_SECRET=""), clear=False):
        client = TestClient(_app(), raise_server_exceptions=False)
        resp = client.post("/slack/events", content=body, headers={"content-type": "application/json"})
    assert resp.status_code == 500
    assert "misconfigured" in resp.json().get("error", "")


# ─────────────────────────────────────────────────────────────────────────────
# T02: 서명 헤더 누락 → 403
# ─────────────────────────────────────────────────────────────────────────────
def test_t02_missing_signature():
    body = b'{"type":"event_callback"}'
    with patch.dict("os.environ", _env()):
        client = TestClient(_app())
        resp = client.post("/slack/events", content=body, headers={"content-type": "application/json"})
    assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# T03: 서명 만료 (> 300s) → 403
# ─────────────────────────────────────────────────────────────────────────────
def test_t03_expired_signature():
    body = b'{"type":"event_callback"}'
    stale_ts = int(time.time()) - 400
    headers = _valid_headers(body, ts=stale_ts)
    with patch.dict("os.environ", _env()):
        client = TestClient(_app())
        resp = client.post("/slack/events", content=body, headers=headers)
    assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# T04: url_verification → 200 + challenge
# ─────────────────────────────────────────────────────────────────────────────
def test_t04_url_verification():
    payload = {"type": "url_verification", "challenge": "test-challenge-xyz"}
    body = json.dumps(payload).encode("utf-8")
    headers = _valid_headers(body)
    with patch.dict("os.environ", _env()):
        client = TestClient(_app())
        resp = client.post("/slack/events", content=body, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["challenge"] == "test-challenge-xyz"


# ─────────────────────────────────────────────────────────────────────────────
# T05: 필수 설정 미설정 → 200 ok=True, DB 호출 0건 (COR-05 Fail Closed)
# ─────────────────────────────────────────────────────────────────────────────
def test_t05_pilot_config_missing():
    body = _make_event_body()
    headers = _valid_headers(body)
    minimal_env = {"SLACK_SIGNING_SECRET": _SIGNING_SECRET}  # APP_ID/TEAM_ID 등 미설정
    with patch.dict("os.environ", minimal_env, clear=False):
        with patch("routers.slack_events.accept_relay_event") as mock_accept:
            client = TestClient(_app())
            resp = client.post("/slack/events", content=body, headers=headers)
    assert resp.status_code == 200
    assert resp.json().get("ok") is True
    mock_accept.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# T06: team_id 불일치 → 200 ok=True
# ─────────────────────────────────────────────────────────────────────────────
def test_t06_wrong_team_id():
    body = _make_event_body(team_id="T_WRONG")
    headers = _valid_headers(body)
    with patch.dict("os.environ", _env()):
        with patch("routers.slack_events.accept_relay_event") as mock_accept:
            client = TestClient(_app())
            resp = client.post("/slack/events", content=body, headers=headers)
    assert resp.status_code == 200
    assert resp.json().get("ok") is True
    mock_accept.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# T07: api_app_id 불일치 → 200 ok=True
# ─────────────────────────────────────────────────────────────────────────────
def test_t07_wrong_app_id():
    body = _make_event_body(app_id="A_WRONG_APP")
    headers = _valid_headers(body)
    with patch.dict("os.environ", _env()):
        with patch("routers.slack_events.accept_relay_event") as mock_accept:
            client = TestClient(_app())
            resp = client.post("/slack/events", content=body, headers=headers)
    assert resp.status_code == 200
    mock_accept.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# T08: 비-message 이벤트 타입 → 200 ok=True
# ─────────────────────────────────────────────────────────────────────────────
def test_t08_non_message_event():
    body = _make_event_body(event_type="reaction_added")
    headers = _valid_headers(body)
    with patch.dict("os.environ", _env()):
        with patch("routers.slack_events.accept_relay_event") as mock_accept:
            client = TestClient(_app())
            resp = client.post("/slack/events", content=body, headers=headers)
    assert resp.status_code == 200
    mock_accept.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# T09: message + subtype(bot_message) → 200 ok=True
# ─────────────────────────────────────────────────────────────────────────────
def test_t09_message_with_subtype():
    body = _make_event_body(subtype="bot_message")
    headers = _valid_headers(body)
    with patch.dict("os.environ", _env()):
        with patch("routers.slack_events.accept_relay_event") as mock_accept:
            client = TestClient(_app())
            resp = client.post("/slack/events", content=body, headers=headers)
    assert resp.status_code == 200
    mock_accept.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# T10: 미승인 발신자 → 200 ok=True, DB 호출 0건
# ─────────────────────────────────────────────────────────────────────────────
def test_t10_unapproved_sender():
    body = _make_event_body(sender_id="U_UNKNOWN_USER")
    headers = _valid_headers(body)
    with patch.dict("os.environ", _env()):
        with patch("routers.slack_events.accept_relay_event") as mock_accept:
            client = TestClient(_app())
            resp = client.post("/slack/events", content=body, headers=headers)
    assert resp.status_code == 200
    mock_accept.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# T11: 미등록 릴레이 채널 → 200 ok=True
# ─────────────────────────────────────────────────────────────────────────────
def test_t11_unregistered_relay_channel():
    body = _make_event_body(relay_channel="G_UNKNOWN_CH")
    headers = _valid_headers(body)
    with patch.dict("os.environ", _env()):
        with patch("routers.slack_events.accept_relay_event") as mock_accept:
            client = TestClient(_app())
            resp = client.post("/slack/events", content=body, headers=headers)
    assert resp.status_code == 200
    mock_accept.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# T12: 빈 텍스트 메시지 → 200 ok=True
# ─────────────────────────────────────────────────────────────────────────────
def test_t12_empty_text():
    body = _make_event_body(text="   ")
    headers = _valid_headers(body)
    with patch.dict("os.environ", _env()):
        with patch("routers.slack_events.accept_relay_event") as mock_accept:
            client = TestClient(_app())
            resp = client.post("/slack/events", content=body, headers=headers)
    assert resp.status_code == 200
    mock_accept.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# T13: 정상 이벤트 → accept_relay_event 1회 + BackgroundTask 등록
# ─────────────────────────────────────────────────────────────────────────────
def test_t13_valid_event_accepted():
    body = _make_event_body()
    headers = _valid_headers(body)
    with patch.dict("os.environ", _env()):
        with patch("routers.slack_events.accept_relay_event", return_value=True) as mock_accept:
            with patch("routers.slack_events.process_relay_event") as mock_process:
                client = TestClient(_app())
                resp = client.post("/slack/events", content=body, headers=headers)
    assert resp.status_code == 200
    assert resp.json().get("ok") is True
    mock_accept.assert_called_once()
    call_kwargs = mock_accept.call_args.kwargs
    assert call_kwargs["event_id"] == "Ev001TEST"
    assert call_kwargs["relay_channel"] == _RELAY_CHANNEL
    assert call_kwargs["target_channel"] == _TARGET_CHANNEL
    assert call_kwargs["sender_id"] == _SENDER_ID
    assert "hello relay" in call_kwargs["message_text"]


# ─────────────────────────────────────────────────────────────────────────────
# T14: 중복 이벤트 → accepted=False, BackgroundTask 없음
# ─────────────────────────────────────────────────────────────────────────────
def test_t14_duplicate_event_no_background_task():
    body = _make_event_body()
    headers = _valid_headers(body)
    with patch.dict("os.environ", _env()):
        with patch("routers.slack_events.accept_relay_event", return_value=False):
            with patch("routers.slack_events.process_relay_event") as mock_process:
                client = TestClient(_app())
                resp = client.post("/slack/events", content=body, headers=headers)
    assert resp.status_code == 200
    mock_process.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# T15: DB 예외 → 503
# ─────────────────────────────────────────────────────────────────────────────
def test_t15_db_exception_503():
    body = _make_event_body()
    headers = _valid_headers(body)
    with patch.dict("os.environ", _env()):
        with patch("routers.slack_events.accept_relay_event", side_effect=RuntimeError("db down")):
            client = TestClient(_app(), raise_server_exceptions=False)
            resp = client.post("/slack/events", content=body, headers=headers)
    assert resp.status_code == 503


# ─────────────────────────────────────────────────────────────────────────────
# T16: PENDING → CLAIMED CAS 성공/실패
# (COR-F02: PENDING UPDATE chain = .update.eq("id").eq("status","PENDING").execute)
# ─────────────────────────────────────────────────────────────────────────────
def test_t16_claim_pending_success():
    fake_sb = MagicMock()
    fake_sb.table.return_value.select.return_value.eq.return_value.in_.return_value.limit.return_value.execute.return_value.data = [
        {"id": "row-001", "status": "PENDING", "next_attempt_at": None}
    ]
    fake_sb.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": "row-001", "status": "CLAIMED"}
    ]
    with patch("services.slack_relay_svc._get_supabase", return_value=fake_sb):
        result = _claim("Ev001TEST")
    assert result is not None
    row_id, token = result
    assert row_id == "row-001"
    assert len(token) == 36  # UUID


def test_t16_claim_no_pending_row():
    fake_sb = MagicMock()
    fake_sb.table.return_value.select.return_value.eq.return_value.in_.return_value.limit.return_value.execute.return_value.data = []
    with patch("services.slack_relay_svc._get_supabase", return_value=fake_sb):
        result = _claim("Ev_MISSING")
    assert result is None


def test_t16_claim_cas_race_condition():
    """다른 Worker가 먼저 claim → UPDATE 0행 → None 반환."""
    fake_sb = MagicMock()
    fake_sb.table.return_value.select.return_value.eq.return_value.in_.return_value.limit.return_value.execute.return_value.data = [
        {"id": "row-002", "status": "PENDING", "next_attempt_at": None}
    ]
    fake_sb.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
    with patch("services.slack_relay_svc._get_supabase", return_value=fake_sb):
        result = _claim("Ev_RACE")
    assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# T17: CLAIMED → SENDING claim_token + 출발 상태 검증
# (COR-02: .eq("id").eq("claim_token").eq("status","CLAIMED") 3중 CAS)
# ─────────────────────────────────────────────────────────────────────────────
def test_t17_start_sending_token_mismatch():
    fake_sb = MagicMock()
    fake_sb.table.return_value.update.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
    with patch("services.slack_relay_svc._get_supabase", return_value=fake_sb):
        result = _start_sending("row-001", "wrong-token")
    assert result is False


def test_t17_start_sending_token_match():
    fake_sb = MagicMock()
    fake_sb.table.return_value.update.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{"id": "row-001"}]
    with patch("services.slack_relay_svc._get_supabase", return_value=fake_sb):
        result = _start_sending("row-001", "correct-token")
    assert result is True


# ─────────────────────────────────────────────────────────────────────────────
# T18: SENDING → SENT (Slack ok=true)
# ─────────────────────────────────────────────────────────────────────────────
def test_t18_sent_on_slack_ok():
    slack_resp = MagicMock()
    slack_resp.status_code = 200
    slack_resp.json.return_value = {"ok": True, "message": {"ts": "1234.5678"}}

    with patch("services.slack_relay_svc._claim", return_value=("row-T18", "tok-T18")):
        with patch("services.slack_relay_svc._start_sending", return_value=True):
            with patch("services.slack_relay_svc._load_row", return_value={
                "id": "row-T18", "target_channel": _TARGET_CHANNEL,
                "message_text": "hello", "claim_token": "tok-T18",
                "status": "CLAIMED", "retry_count": 0,
            }):
                with patch("services.slack_relay_svc._get_bot_token", return_value="xoxb-test-token"):
                    with patch("httpx.AsyncClient") as mock_httpx:
                        mock_ctx = AsyncMock()
                        mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
                        mock_ctx.__aexit__ = AsyncMock(return_value=False)
                        mock_ctx.post = AsyncMock(return_value=slack_resp)
                        mock_httpx.return_value = mock_ctx
                        with patch("services.slack_relay_svc._finish") as mock_finish:
                            asyncio.run(process_relay_event("Ev-T18"))
    mock_finish.assert_called_once()
    assert mock_finish.call_args[0][2] == "SENT"


# ─────────────────────────────────────────────────────────────────────────────
# T18b: WO-008 — _finish() claim_token 중복 인자 결함 수정 검증
# ─────────────────────────────────────────────────────────────────────────────
def test_t18b_finish_no_duplicate_arg_typeerror():
    """WO-008: _finish(row, token, 'SENT', ..., claim_token=None) — TypeError 없이 성공."""
    fake_sb = MagicMock()
    fake_sb.table.return_value.update.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": "row-T18b"}
    ]
    with patch("services.slack_relay_svc._get_supabase", return_value=fake_sb):
        result = _finish(
            "row-T18b", "tok-T18b", "SENT",
            sent_at="2026-01-01T00:00:00+00:00",
            slack_ts="1234.5678",
            claim_token=None,
        )
    assert result is True
    update_data = fake_sb.table.return_value.update.call_args[0][0]
    assert update_data["status"] == "SENT"
    assert update_data["claim_token"] is None
    assert update_data["slack_ts"] == "1234.5678"


# ─────────────────────────────────────────────────────────────────────────────
# T18c: WO-008 — process_relay_event E2E, _finish() Mock 없이 SENT 전이 확인
# ─────────────────────────────────────────────────────────────────────────────
def test_t18c_process_relay_event_sent_transition_no_finish_mock():
    """WO-008: _finish() Mock 없이 Slack ok=true 경로 실행 — SENT 전이 + TypeError 없음."""
    slack_resp = MagicMock()
    slack_resp.status_code = 200
    slack_resp.json.return_value = {"ok": True, "message": {"ts": "9999.0001"}}

    fake_sb = MagicMock()
    fake_sb.table.return_value.update.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": "row-T18c"}
    ]

    with patch("services.slack_relay_svc._claim", return_value=("row-T18c", "tok-T18c")):
        with patch("services.slack_relay_svc._start_sending", return_value=True):
            with patch("services.slack_relay_svc._load_row", return_value={
                "id": "row-T18c", "target_channel": _TARGET_CHANNEL,
                "message_text": "relay test", "claim_token": "tok-T18c",
                "status": "CLAIMED", "retry_count": 0,
            }):
                with patch("services.slack_relay_svc._get_bot_token", return_value="xoxb-test"):
                    with patch("httpx.AsyncClient") as mock_httpx:
                        mock_ctx = AsyncMock()
                        mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
                        mock_ctx.__aexit__ = AsyncMock(return_value=False)
                        mock_ctx.post = AsyncMock(return_value=slack_resp)
                        mock_httpx.return_value = mock_ctx
                        with patch("services.slack_relay_svc._get_supabase", return_value=fake_sb):
                            asyncio.run(process_relay_event("Ev-T18c"))

    assert fake_sb.table.return_value.update.called
    update_data = fake_sb.table.return_value.update.call_args[0][0]
    assert update_data["status"] == "SENT"
    assert update_data["claim_token"] is None
    assert update_data.get("slack_ts") == "9999.0001"


# ─────────────────────────────────────────────────────────────────────────────
# T19: DB 복구 — PENDING 행 존재 시 run_relay_recovery_once 처리
# (Mock chain: PENDING=.select.eq.order.limit.execute / RETRY=.select.eq.or_.order.limit.execute)
# ─────────────────────────────────────────────────────────────────────────────
def test_t19_recovery_processes_pending_rows():
    fake_sb = MagicMock()
    # PENDING SELECT
    fake_sb.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [
        {"event_id": "Ev-R01"}, {"event_id": "Ev-R02"}
    ]
    # RETRY SELECT
    fake_sb.table.return_value.select.return_value.eq.return_value.or_.return_value.order.return_value.limit.return_value.execute.return_value.data = []
    # stale recovery UPDATE
    fake_sb.table.return_value.update.return_value.eq.return_value.lt.return_value.execute.return_value.data = []

    processed_ids = []

    async def _fake_process(event_id):
        processed_ids.append(event_id)

    with patch("services.slack_relay_svc._get_supabase", return_value=fake_sb):
        with patch("services.slack_relay_svc.process_relay_event", side_effect=_fake_process):
            count = asyncio.run(run_relay_recovery_once())

    assert count == 2
    assert "Ev-R01" in processed_ids
    assert "Ev-R02" in processed_ids


# ─────────────────────────────────────────────────────────────────────────────
# T20: Slack API timeout → UNKNOWN
# ─────────────────────────────────────────────────────────────────────────────
def test_t20_slack_timeout_unknown():
    import httpx as _httpx

    with patch("services.slack_relay_svc._claim", return_value=("row-T20", "tok-T20")):
        with patch("services.slack_relay_svc._start_sending", return_value=True):
            with patch("services.slack_relay_svc._load_row", return_value={
                "id": "row-T20", "target_channel": _TARGET_CHANNEL,
                "message_text": "hello", "claim_token": "tok-T20",
                "status": "CLAIMED", "retry_count": 0,
            }):
                with patch("services.slack_relay_svc._get_bot_token", return_value="xoxb-test"):
                    with patch("httpx.AsyncClient") as mock_httpx:
                        mock_ctx = AsyncMock()
                        mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
                        mock_ctx.__aexit__ = AsyncMock(return_value=False)
                        mock_ctx.post = AsyncMock(side_effect=_httpx.TimeoutException("timeout"))
                        mock_httpx.return_value = mock_ctx
                        with patch("services.slack_relay_svc._finish") as mock_finish:
                            asyncio.run(process_relay_event("Ev-T20"))
    mock_finish.assert_called_once()
    assert mock_finish.call_args[0][2] == "UNKNOWN"


# ─────────────────────────────────────────────────────────────────────────────
# T21: 두 Worker 동시 claim — 한 쪽만 성공
# ─────────────────────────────────────────────────────────────────────────────
def test_t21_concurrent_claim_only_one_succeeds():
    """CAS: 두 번째 UPDATE는 status 조건 불충족 → 0행 → None."""
    call_count = {"n": 0}

    def _fake_update_execute():
        m = MagicMock()
        call_count["n"] += 1
        m.data = [{"id": "row-T21"}] if call_count["n"] == 1 else []
        return m

    fake_sb = MagicMock()
    fake_sb.table.return_value.select.return_value.eq.return_value.in_.return_value.limit.return_value.execute.return_value.data = [
        {"id": "row-T21", "status": "PENDING", "next_attempt_at": None}
    ]
    # COR-F02: PENDING UPDATE chain = .eq("id").eq("status","PENDING").execute
    fake_sb.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.side_effect = _fake_update_execute

    with patch("services.slack_relay_svc._get_supabase", return_value=fake_sb):
        result1 = _claim("Ev-T21")
        result2 = _claim("Ev-T21")

    assert result1 is not None
    assert result2 is None


# ─────────────────────────────────────────────────────────────────────────────
# T22: claim_token 불일치 → _finish 0행 반환
# (COR-02: .eq("id").eq("claim_token").eq("status","SENDING") 3중 CAS)
# ─────────────────────────────────────────────────────────────────────────────
def test_t22_finish_token_mismatch_no_update():
    fake_sb = MagicMock()
    fake_sb.table.return_value.update.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
    with patch("services.slack_relay_svc._get_supabase", return_value=fake_sb):
        result = _finish("row-T22", "stale-token", "SENT")
    assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# T23: 빈 큐 → 복구 처리 0건
# ─────────────────────────────────────────────────────────────────────────────
def test_t23_recovery_empty_queue():
    fake_sb = MagicMock()
    fake_sb.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
    fake_sb.table.return_value.select.return_value.eq.return_value.or_.return_value.order.return_value.limit.return_value.execute.return_value.data = []
    fake_sb.table.return_value.update.return_value.eq.return_value.lt.return_value.execute.return_value.data = []

    with patch("services.slack_relay_svc._get_supabase", return_value=fake_sb):
        with patch("services.slack_relay_svc.process_relay_event") as mock_process:
            count = asyncio.run(run_relay_recovery_once())

    assert count == 0
    mock_process.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# T24: Slack HTTP 200 + ok=false (channel_not_found) → FAILED_PERMANENT
# ─────────────────────────────────────────────────────────────────────────────
def test_t24_slack_ok_false_permanent_error():
    slack_resp = MagicMock()
    slack_resp.status_code = 200
    slack_resp.json.return_value = {"ok": False, "error": "channel_not_found"}

    with patch("services.slack_relay_svc._claim", return_value=("row-T24", "tok-T24")):
        with patch("services.slack_relay_svc._start_sending", return_value=True):
            with patch("services.slack_relay_svc._load_row", return_value={
                "id": "row-T24", "target_channel": "C_GONE",
                "message_text": "hi", "claim_token": "tok-T24",
                "status": "CLAIMED", "retry_count": 0,
            }):
                with patch("services.slack_relay_svc._get_bot_token", return_value="xoxb-test"):
                    with patch("httpx.AsyncClient") as mock_httpx:
                        mock_ctx = AsyncMock()
                        mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
                        mock_ctx.__aexit__ = AsyncMock(return_value=False)
                        mock_ctx.post = AsyncMock(return_value=slack_resp)
                        mock_httpx.return_value = mock_ctx
                        with patch("services.slack_relay_svc._finish") as mock_finish:
                            asyncio.run(process_relay_event("Ev-T24"))
    mock_finish.assert_called_once()
    assert mock_finish.call_args[0][2] == "FAILED_PERMANENT"


# ─────────────────────────────────────────────────────────────────────────────
# T25: Bot token이 로그에 출력되지 않는 것 확인
# ─────────────────────────────────────────────────────────────────────────────
def test_t25_bot_token_not_logged():
    import logging
    import io
    import services.slack_relay_svc as svc

    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    svc_logger = logging.getLogger("slack_relay_svc")
    svc_logger.addHandler(handler)

    fake_token = "xoxb-SHOULD-NOT-APPEAR-IN-LOGS"
    with patch.dict("os.environ", {"SLACK_BOT_TOKEN1": fake_token}):
        token = svc._get_bot_token()
        assert token == fake_token

    log_output = log_capture.getvalue()
    assert fake_token not in log_output
    svc_logger.removeHandler(handler)


# ─────────────────────────────────────────────────────────────────────────────
# REG1: 기존 Automation 회귀 — 인증 없는 /automation/rules → 401
# ─────────────────────────────────────────────────────────────────────────────
def test_reg1_automation_unauthenticated_401():
    from fastapi import FastAPI
    from routers.automation import router as auto_router
    reg_app = FastAPI()
    reg_app.include_router(auto_router)
    client = TestClient(reg_app)
    resp = client.get("/automation/rules")
    assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# REG2: Permission Guard _PUBLIC 에 /slack/events 포함 확인
# ─────────────────────────────────────────────────────────────────────────────
def test_reg2_permission_guard_slack_events_public():
    from services.permission_guard import is_public
    assert is_public("POST", "/slack/events") is True


def test_reg2_permission_guard_wildcard_not_public():
    from services.permission_guard import is_public
    assert is_public("POST", "/slack/other-endpoint") is False


# ─────────────────────────────────────────────────────────────────────────────
# 보조: _parse_channel_map 단위 테스트
# ─────────────────────────────────────────────────────────────────────────────
def test_parse_channel_map_valid():
    result = _parse_channel_map('{"G001": "C002"}')
    assert result == {"G001": "C002"}


def test_parse_channel_map_empty():
    assert _parse_channel_map("") == {}
    assert _parse_channel_map("  ") == {}


def test_parse_channel_map_invalid_json():
    result = _parse_channel_map("not-json")
    assert result == {}


# ─────────────────────────────────────────────────────────────────────────────
# 보조: _retry_delay_sec 단위 테스트 (COR-07: 초 단위)
# ─────────────────────────────────────────────────────────────────────────────
def test_retry_delay_values():
    assert _retry_delay_sec(0) == 60
    assert _retry_delay_sec(1) == 300
    assert _retry_delay_sec(2) == 900
    assert _retry_delay_sec(99) == 900  # 상한 클램프


# ─────────────────────────────────────────────────────────────────────────────
# 보조: accept_relay_event 멱등 삽입 (upsert ignore_duplicates)
# ─────────────────────────────────────────────────────────────────────────────
def test_accept_relay_event_new():
    fake_sb = MagicMock()
    fake_sb.table.return_value.upsert.return_value.execute.return_value.data = [{"id": "new-row"}]
    with patch("services.slack_relay_svc._get_supabase", return_value=fake_sb):
        result = accept_relay_event(
            event_id="Ev-NEW", relay_channel="G1", target_channel="C2",
            message_text="hi", sender_id="U1", source_message_ts="1234.0"
        )
    assert result is True
    call_args = fake_sb.table.return_value.upsert.call_args
    assert call_args.kwargs.get("ignore_duplicates") is True
    assert call_args.kwargs.get("on_conflict") == "event_id"


def test_accept_relay_event_duplicate():
    fake_sb = MagicMock()
    fake_sb.table.return_value.upsert.return_value.execute.return_value.data = []
    with patch("services.slack_relay_svc._get_supabase", return_value=fake_sb):
        result = accept_relay_event(
            event_id="Ev-DUP", relay_channel="G1", target_channel="C2",
            message_text="hi", sender_id="U1", source_message_ts=None
        )
    assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# R01: COR-03 — PENDING + next_attempt_at=NULL → Claim 가능
# ─────────────────────────────────────────────────────────────────────────────
def test_r01_claim_pending_null_next_attempt():
    fake_sb = MagicMock()
    fake_sb.table.return_value.select.return_value.eq.return_value.in_.return_value.limit.return_value.execute.return_value.data = [
        {"id": "row-R01", "status": "PENDING", "next_attempt_at": None}
    ]
    # COR-F02: PENDING UPDATE = .eq("id").eq("status","PENDING").execute
    fake_sb.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": "row-R01"}
    ]
    with patch("services.slack_relay_svc._get_supabase", return_value=fake_sb):
        result = _claim("Ev-R01")
    assert result is not None
    row_id, _ = result
    assert row_id == "row-R01"


# ─────────────────────────────────────────────────────────────────────────────
# R02: COR-02/03 — RETRY + 도래한 next_attempt_at → Claim 가능
# ─────────────────────────────────────────────────────────────────────────────
def test_r02_claim_retry_arrived():
    past = (datetime.now(tz=timezone.utc) - timedelta(seconds=120)).isoformat()
    fake_sb = MagicMock()
    fake_sb.table.return_value.select.return_value.eq.return_value.in_.return_value.limit.return_value.execute.return_value.data = [
        {"id": "row-R02", "status": "RETRY", "next_attempt_at": past}
    ]
    # COR-F02: RETRY UPDATE = .eq("id").eq("status","RETRY").or_(...).execute
    fake_sb.table.return_value.update.return_value.eq.return_value.eq.return_value.or_.return_value.execute.return_value.data = [
        {"id": "row-R02"}
    ]
    with patch("services.slack_relay_svc._get_supabase", return_value=fake_sb):
        result = _claim("Ev-R02")
    assert result is not None


# ─────────────────────────────────────────────────────────────────────────────
# R03: COR-03 — RETRY + 미래 next_attempt_at → Claim 거부
# ─────────────────────────────────────────────────────────────────────────────
def test_r03_claim_retry_future():
    future = (datetime.now(tz=timezone.utc) + timedelta(seconds=300)).isoformat()
    fake_sb = MagicMock()
    fake_sb.table.return_value.select.return_value.eq.return_value.in_.return_value.limit.return_value.execute.return_value.data = [
        {"id": "row-R03", "status": "RETRY", "next_attempt_at": future}
    ]
    with patch("services.slack_relay_svc._get_supabase", return_value=fake_sb):
        result = _claim("Ev-R03")
    assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# R04: COR-04 — stale CLAIMED/SENDING 복구 — RETRY/UNKNOWN 전환 호출
# ─────────────────────────────────────────────────────────────────────────────
def test_r04_recover_stale_both_statuses():
    fake_sb = MagicMock()
    # COR-F02: CLAIMED 복구는 claim_expires 기준 .or_ 체인 사용
    fake_sb.table.return_value.update.return_value.eq.return_value.or_.return_value.execute.return_value.data = [
        {"id": "row-stale-claimed"}
    ]
    # SENDING 복구는 updated_at 기준 .lt 체인 유지
    fake_sb.table.return_value.update.return_value.eq.return_value.lt.return_value.execute.return_value.data = [
        {"id": "row-stale-sending"}
    ]
    with patch("services.slack_relay_svc._get_supabase", return_value=fake_sb):
        recovered = recover_stale_claimed()
    assert recovered == 2  # CLAIMED→RETRY(1) + SENDING→UNKNOWN(1)
    update_calls = fake_sb.table.return_value.update.call_args_list
    status_strings = [str(c) for c in update_calls]
    assert any("RETRY" in s for s in status_strings)
    assert any("UNKNOWN" in s for s in status_strings)


# ─────────────────────────────────────────────────────────────────────────────
# R06: 중복 event_id CAS 펜싱 — accept=False → BackgroundTask 미등록
# ─────────────────────────────────────────────────────────────────────────────
def test_r06_duplicate_event_id_no_background_task():
    body = _make_event_body(event_id="Ev-R06-DUP")
    headers = _valid_headers(body)
    with patch.dict("os.environ", _env()):
        with patch("routers.slack_events.accept_relay_event", return_value=False):
            with patch("routers.slack_events.process_relay_event") as mock_proc:
                client = TestClient(_app())
                resp = client.post("/slack/events", content=body, headers=headers)
    assert resp.status_code == 200
    mock_proc.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# R07: COR-07 — 429 Retry-After=47s → _future_sec(47) 호출 (분 변환 없음)
# ─────────────────────────────────────────────────────────────────────────────
def test_r07_rate_limit_uses_exact_seconds():
    slack_resp = MagicMock()
    slack_resp.status_code = 429
    slack_resp.headers = {"Retry-After": "47"}

    future_calls: list[int] = []

    def _capturing_future_sec(s: int) -> str:
        future_calls.append(s)
        return "2099-01-01T00:00:00+00:00"

    with patch("services.slack_relay_svc._claim", return_value=("row-R07", "tok-R07")):
        with patch("services.slack_relay_svc._start_sending", return_value=True):
            with patch("services.slack_relay_svc._load_row", return_value={
                "id": "row-R07", "target_channel": "C_T",
                "message_text": "hi", "claim_token": "tok-R07",
                "status": "CLAIMED", "retry_count": 0,
            }):
                with patch("services.slack_relay_svc._get_bot_token", return_value="xoxb-test"):
                    with patch("httpx.AsyncClient") as mock_httpx:
                        mock_ctx = AsyncMock()
                        mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
                        mock_ctx.__aexit__ = AsyncMock(return_value=False)
                        mock_ctx.post = AsyncMock(return_value=slack_resp)
                        mock_httpx.return_value = mock_ctx
                        with patch("services.slack_relay_svc._future_sec",
                                   side_effect=_capturing_future_sec):
                            with patch("services.slack_relay_svc._finish"):
                                asyncio.run(process_relay_event("Ev-R07"))

    assert 47 in future_calls, f"_future_sec(47) 미호출 — 실제 호출: {future_calls}"
    assert 60 not in future_calls, "분 변환된 60이 사용됨 (COR-07 위반)"


# ─────────────────────────────────────────────────────────────────────────────
# R08: COR-05 — APP_ID/TEAM_ID 미설정 → accept_relay_event 호출 없음
# ─────────────────────────────────────────────────────────────────────────────
def test_r08_app_id_team_id_unset_fail_closed():
    body = _make_event_body()
    headers = _valid_headers(body)
    env_no_ids = {
        "SLACK_SIGNING_SECRET": _SIGNING_SECRET,
        "SLACK_RELAY_ALLOWED_SENDER_IDS": _SENDER_ID,
        "SLACK_RELAY_CHANNEL_MAP": _CHANNEL_MAP_JSON,
        # APP_ID, TEAM_ID 미설정
    }
    with patch.dict("os.environ", env_no_ids, clear=False):
        with patch("routers.slack_events.accept_relay_event") as mock_accept:
            client = TestClient(_app())
            resp = client.post("/slack/events", content=body, headers=headers)
    assert resp.status_code == 200
    assert resp.json().get("ok") is True
    mock_accept.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# R09: COR-05 — type != event_callback → 접수 거부
# ─────────────────────────────────────────────────────────────────────────────
def test_r09_non_event_callback_type_discarded():
    payload = {"type": "block_actions", "api_app_id": _APP_ID, "team_id": _TEAM_ID}
    body = json.dumps(payload).encode("utf-8")
    headers = _valid_headers(body)
    with patch.dict("os.environ", _env()):
        with patch("routers.slack_events.accept_relay_event") as mock_accept:
            client = TestClient(_app())
            resp = client.post("/slack/events", content=body, headers=headers)
    assert resp.status_code == 200
    mock_accept.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# R10: COR-05 — event.bot_id 존재 → 접수 거부
# ─────────────────────────────────────────────────────────────────────────────
def test_r10_bot_id_present_discarded():
    body = _make_event_body(bot_id="B0SOMEBOTID")
    headers = _valid_headers(body)
    with patch.dict("os.environ", _env()):
        with patch("routers.slack_events.accept_relay_event") as mock_accept:
            client = TestClient(_app())
            resp = client.post("/slack/events", content=body, headers=headers)
    assert resp.status_code == 200
    mock_accept.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# R11: COR-05 — event_id 누락 → UUID 대체 금지, 접수 거부
# ─────────────────────────────────────────────────────────────────────────────
def test_r11_missing_event_id_no_uuid_fallback():
    event = {
        "type": "message", "user": _SENDER_ID, "channel": _RELAY_CHANNEL,
        "text": "no event id", "ts": "1000.0001",
    }
    payload = {
        "type": "event_callback",
        # event_id 없음
        "team_id": _TEAM_ID,
        "api_app_id": _APP_ID,
        "event": event,
    }
    body = json.dumps(payload).encode("utf-8")
    headers = _valid_headers(body)
    with patch.dict("os.environ", _env()):
        with patch("routers.slack_events.accept_relay_event") as mock_accept:
            client = TestClient(_app())
            resp = client.post("/slack/events", content=body, headers=headers)
    assert resp.status_code == 200
    mock_accept.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# R12: COR-06 — SLACK_BOT_TOKEN1 미설정 → SLACK_BOT_TOKEN 폴백 없이 RETRY
# ─────────────────────────────────────────────────────────────────────────────
def test_r12_token1_unset_no_fallback_to_old_token():
    import services.slack_relay_svc as svc
    with patch.dict("os.environ", {"SLACK_BOT_TOKEN1": "", "SLACK_BOT_TOKEN": "xoxb-old-bot"}):
        token = svc._get_bot_token()
    assert token == ""


def test_r12_token1_unset_causes_retry():
    with patch("services.slack_relay_svc._claim", return_value=("row-R12", "tok-R12")):
        with patch("services.slack_relay_svc._load_row", return_value={
            "id": "row-R12", "target_channel": "C_T",
            "message_text": "hi", "claim_token": "tok-R12",
            "status": "CLAIMED", "retry_count": 0,
        }):
            with patch("services.slack_relay_svc._start_sending", return_value=True):
                with patch.dict("os.environ", {"SLACK_BOT_TOKEN1": "", "SLACK_BOT_TOKEN": "xoxb-fallback"}):
                    with patch("services.slack_relay_svc._finish") as mock_finish:
                        asyncio.run(process_relay_event("Ev-R12"))
    mock_finish.assert_called_once()
    assert mock_finish.call_args[0][2] == "RETRY"
    assert "TOKEN1" in mock_finish.call_args.kwargs.get("error_detail", "")


# ─────────────────────────────────────────────────────────────────────────────
# R13: P0 회귀 — slack_events + automation 라우터 공존 확인
# ─────────────────────────────────────────────────────────────────────────────
def test_r13_p0_slack_and_automation_coexist():
    """두 라우터를 동일 앱에 등록해도 Import 충돌·예외 없음."""
    from fastapi import FastAPI
    from routers.automation import router as auto_router
    from routers.slack_events import router as slack_router
    app = FastAPI()
    # 예외 없이 등록 완료되어야 함
    app.include_router(slack_router)
    app.include_router(auto_router)
    # URL 조회 가능 여부로 라우트 등록 확인
    url = app.url_path_for("slack_events")
    assert str(url) == "/slack/events"


# ─────────────────────────────────────────────────────────────────────────────
# R14: R3 라우터 속성(prefix/tags) 확인
# ─────────────────────────────────────────────────────────────────────────────
def test_r14_slack_relay_router_attributes():
    assert router.prefix == "/slack"
    assert "slack-relay" in router.tags


# ─────────────────────────────────────────────────────────────────────────────
# R05: COR-04 — stale SENDING → UNKNOWN 전환, Slack 재발송 없음
# ─────────────────────────────────────────────────────────────────────────────
def test_r05_stale_sending_to_unknown_no_resend():
    """stale SENDING → UNKNOWN 전환 확인 (자동 재발송 차단, claim_token 제거)."""
    fake_sb = MagicMock()
    # CLAIMED 복구 (.or_ 체인)는 빈 결과
    fake_sb.table.return_value.update.return_value.eq.return_value.or_.return_value.execute.return_value.data = []
    # SENDING 복구 (.lt 체인)는 1행
    fake_sb.table.return_value.update.return_value.eq.return_value.lt.return_value.execute.return_value.data = [
        {"id": "row-R05"}
    ]
    with patch("services.slack_relay_svc._get_supabase", return_value=fake_sb):
        with patch("httpx.AsyncClient") as mock_httpx:
            recovered = recover_stale_claimed()
    # Slack HTTP 발송 없음
    mock_httpx.assert_not_called()
    # SENDING→UNKNOWN 업데이트 포함 확인
    update_calls = fake_sb.table.return_value.update.call_args_list
    assert any("UNKNOWN" in str(c) for c in update_calls)
    # UNKNOWN 전환 시 claim_token=None 포함 확인 (재발송 잠금)
    for call in update_calls:
        payload = call.args[0] if call.args else (call[0][0] if call[0] else {})
        if isinstance(payload, dict) and payload.get("status") == "UNKNOWN":
            assert payload.get("claim_token") is None


# ─────────────────────────────────────────────────────────────────────────────
# R15: COR-01 — 복구 진입점 등록, 미인증 시 401
# ─────────────────────────────────────────────────────────────────────────────
def test_r15_recovery_endpoint_exists_and_requires_auth():
    """COR-01: POST /internal/slack-relay/recover — 등록 확인, 미인증 시 401."""
    from fastapi import FastAPI
    from routers.slack_relay_recover import router as recover_router
    app = FastAPI()
    app.include_router(recover_router)
    url = app.url_path_for("trigger_relay_recovery")
    assert str(url) == "/internal/slack-relay/recover"
    client = TestClient(app)
    resp = client.post("/internal/slack-relay/recover")
    assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# R16: COR-02 — _start_sending / _finish 출발 상태 검증 (status guard)
# ─────────────────────────────────────────────────────────────────────────────
def test_r16_start_sending_requires_claimed_status():
    """COR-02: _start_sending이 status='CLAIMED' 조건(3번째 .eq)으로 UPDATE하는지 확인."""
    fake_sb = MagicMock()
    fake_sb.table.return_value.update.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": "row-R16"}
    ]
    with patch("services.slack_relay_svc._get_supabase", return_value=fake_sb):
        result = _start_sending("row-R16", "tok-R16")
    assert result is True
    # 세 번째 .eq() 호출: eq.return_value.eq.return_value.eq.call_args
    third_eq = fake_sb.table.return_value.update.return_value.eq.return_value.eq.return_value.eq
    assert third_eq.called
    call_args = third_eq.call_args
    assert "CLAIMED" in str(call_args)


def test_r16_finish_requires_sending_status():
    """COR-02: _finish가 status='SENDING' 조건(3번째 .eq)으로 UPDATE하는지 확인."""
    fake_sb = MagicMock()
    fake_sb.table.return_value.update.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": "row-R16"}
    ]
    with patch("services.slack_relay_svc._get_supabase", return_value=fake_sb):
        result = _finish("row-R16", "tok-R16", "SENT")
    assert result is True
    third_eq = fake_sb.table.return_value.update.return_value.eq.return_value.eq.return_value.eq
    assert third_eq.called
    assert "SENDING" in str(third_eq.call_args)


# ─────────────────────────────────────────────────────────────────────────────
# R17: COR-F01 — CLI --run 플래그로 복구 실행 / 플래그 없으면 종료
# ─────────────────────────────────────────────────────────────────────────────
def test_r17_cli_run_calls_recovery():
    """scripts/slack_relay_recover_cli.py: --run으로 run_relay_recovery_once 호출."""
    from scripts.slack_relay_recover_cli import main
    with patch(
        "services.slack_relay_svc.run_relay_recovery_once",
        new_callable=AsyncMock,
        return_value=3,
    ) as mock_run:
        result = main(["--run"])
    assert result == 0
    mock_run.assert_called_once()


def test_r17_cli_no_flag_exits_nonzero():
    """scripts/slack_relay_recover_cli.py: --run 없이 실행하면 종료 코드 != 0."""
    from scripts.slack_relay_recover_cli import main
    result = main([])
    assert result != 0


# ─────────────────────────────────────────────────────────────────────────────
# R18: COR-F01 — slack_relay_recover가 external ROUTERS에 없음
# ─────────────────────────────────────────────────────────────────────────────
def test_r18_recover_router_not_in_external_registry():
    """COR-F01: routers.slack_relay_recover가 인터넷 노출 레지스트리에서 제거됨."""
    from router_registry.external import ROUTERS
    modules = [r.get("module", "") for r in ROUTERS]
    assert "routers.slack_relay_recover" not in modules
