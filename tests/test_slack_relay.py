"""WO-TAI-SLACK-BOT-UNIFIED-001-R3 — Slack Events Relay 파일럿 테스트 T01~T25.

커버리지:
  T01  SLACK_SIGNING_SECRET 미설정 → 500
  T02  서명 없음(헤더 누락) → 403
  T03  서명 만료(타임스탬프 > 300s) → 403
  T04  유효 서명 + url_verification → 200 {"challenge": ...}
  T05  SLACK_RELAY_APP_ID/SENDER_IDS/CHANNEL_MAP 미설정 → 200 ok=True (발송 안 함)
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
  T23  PENDING/RETRY 복구 Worker: next_attempt_at 도래 행만 처리
  T24  Slack HTTP 200 + ok=false (채널 없음) → FAILED_PERMANENT
  T25  Bot token이 로그에 출력되지 않는 것 확인 (코드 정적 검증)
  REG1 기존 Automation 회귀: 인증 없는 /automation/rules → 401
  REG2 기존 Permission Guard is_public: /slack/events 포함 확인
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers.slack_events import router, _load_config, _parse_channel_map
from services.slack_relay_svc import (
    _claim, _finish, _get_bot_token, _retry_delay, _start_sending,
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
) -> bytes:
    event: dict[str, Any] = {"type": event_type, "user": sender_id, "channel": relay_channel, "text": text, "ts": "1000.0001"}
    if subtype:
        event["subtype"] = subtype
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
    with patch.dict("os.environ", {"SLACK_SIGNING_SECRET": ""}, clear=False):
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
# T05: 파일럿 설정 미설정 → 200 ok=True, DB 호출 0건
# ─────────────────────────────────────────────────────────────────────────────
def test_t05_pilot_config_missing():
    body = _make_event_body()
    headers = _valid_headers(body)
    minimal_env = {"SLACK_SIGNING_SECRET": _SIGNING_SECRET}  # APP_ID 등 미설정
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
    # BackgroundTask가 등록되지 않았어야 함 (TestClient는 sync — background task는 응답 후 실행)
    # process_relay_event가 직접 호출되지 않았는지 확인
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
# ─────────────────────────────────────────────────────────────────────────────
def test_t16_claim_pending_success():
    fake_sb = MagicMock()
    fake_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [{"id": "row-001"}]
    fake_sb.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{"id": "row-001", "status": "CLAIMED"}]
    with patch("services.slack_relay_svc._get_supabase", return_value=fake_sb):
        result = _claim("Ev001TEST")
    assert result is not None
    row_id, token = result
    assert row_id == "row-001"
    assert len(token) == 36  # UUID


def test_t16_claim_no_pending_row():
    fake_sb = MagicMock()
    fake_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
    with patch("services.slack_relay_svc._get_supabase", return_value=fake_sb):
        result = _claim("Ev_MISSING")
    assert result is None


def test_t16_claim_cas_race_condition():
    """다른 Worker가 먼저 claim → UPDATE 0행 → None 반환."""
    fake_sb = MagicMock()
    fake_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [{"id": "row-002"}]
    fake_sb.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
    with patch("services.slack_relay_svc._get_supabase", return_value=fake_sb):
        result = _claim("Ev_RACE")
    assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# T17: CLAIMED → SENDING claim_token 불일치 시 False
# ─────────────────────────────────────────────────────────────────────────────
def test_t17_start_sending_token_mismatch():
    fake_sb = MagicMock()
    fake_sb.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
    with patch("services.slack_relay_svc._get_supabase", return_value=fake_sb):
        result = _start_sending("row-001", "wrong-token")
    assert result is False


def test_t17_start_sending_token_match():
    fake_sb = MagicMock()
    fake_sb.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{"id": "row-001"}]
    with patch("services.slack_relay_svc._get_supabase", return_value=fake_sb):
        result = _start_sending("row-001", "correct-token")
    assert result is True


# ─────────────────────────────────────────────────────────────────────────────
# T18: SENDING → SENT (Slack ok=true)
# ─────────────────────────────────────────────────────────────────────────────
def test_t18_sent_on_slack_ok():
    fake_sb = MagicMock()
    # _claim: select + update
    select_chain = MagicMock()
    select_chain.data = [{"id": "row-T18"}]
    fake_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = select_chain
    update_chain = MagicMock()
    update_chain.data = [{"id": "row-T18"}]
    fake_sb.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = update_chain

    slack_resp = MagicMock()
    slack_resp.status_code = 200
    slack_resp.json.return_value = {"ok": True, "message": {"ts": "1234.5678"}}

    with patch("services.slack_relay_svc._get_supabase", return_value=fake_sb):
        with patch("services.slack_relay_svc._load_row", return_value={
            "id": "row-T18", "target_channel": _TARGET_CHANNEL,
            "message_text": "hello", "claim_token": "tok-T18", "status": "CLAIMED", "retry_count": 0
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
# T19: DB 복구 — PENDING 행 run_relay_recovery_once 처리
# ─────────────────────────────────────────────────────────────────────────────
def test_t19_recovery_processes_pending_rows():
    fake_sb = MagicMock()
    fake_sb.table.return_value.select.return_value.in_.return_value.lte.return_value.order.return_value.limit.return_value.execute.return_value.data = [
        {"event_id": "Ev-R01"}, {"event_id": "Ev-R02"}
    ]
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

    with patch("services.slack_relay_svc._get_supabase", return_value=MagicMock()):
        with patch("services.slack_relay_svc._load_row", return_value={
            "id": "row-T20", "target_channel": _TARGET_CHANNEL,
            "message_text": "hello", "claim_token": "tok-T20", "status": "CLAIMED", "retry_count": 0
        }):
            with patch("services.slack_relay_svc._claim", return_value=("row-T20", "tok-T20")):
                with patch("services.slack_relay_svc._start_sending", return_value=True):
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
    """CAS: 두 번째 UPDATE는 status=PENDING 조건 불충족 → 0행 → None."""
    call_count = {"n": 0}

    def _fake_update_execute():
        m = MagicMock()
        call_count["n"] += 1
        # 첫 번째 Worker만 성공
        m.data = [{"id": "row-T21"}] if call_count["n"] == 1 else []
        return m

    fake_sb = MagicMock()
    fake_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [{"id": "row-T21"}]
    fake_sb.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.side_effect = _fake_update_execute

    with patch("services.slack_relay_svc._get_supabase", return_value=fake_sb):
        result1 = _claim("Ev-T21")
        result2 = _claim("Ev-T21")

    assert result1 is not None
    assert result2 is None


# ─────────────────────────────────────────────────────────────────────────────
# T22: claim_token 불일치 → _finish 0행 반환
# ─────────────────────────────────────────────────────────────────────────────
def test_t22_finish_token_mismatch_no_update():
    fake_sb = MagicMock()
    fake_sb.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
    with patch("services.slack_relay_svc._get_supabase", return_value=fake_sb):
        result = _finish("row-T22", "stale-token", "SENT")
    assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# T23: next_attempt_at 미도래 행 → 복구 스캔에서 제외
# ─────────────────────────────────────────────────────────────────────────────
def test_t23_recovery_skips_future_retry():
    """next_attempt_at이 미래인 행은 lte 조건에서 제외되어 처리하지 않음."""
    fake_sb = MagicMock()
    fake_sb.table.return_value.select.return_value.in_.return_value.lte.return_value.order.return_value.limit.return_value.execute.return_value.data = []
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
                "message_text": "hi", "claim_token": "tok-T24", "status": "CLAIMED", "retry_count": 0
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
# T25: Bot token이 로그·코드에 출력되지 않는 것 확인 (정적 검증)
# ─────────────────────────────────────────────────────────────────────────────
def test_t25_bot_token_not_logged():
    """로그 핸들러에서 bot token 값이 출력되지 않음 확인."""
    import logging
    import io
    import services.slack_relay_svc as svc

    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    svc_logger = logging.getLogger("slack_relay_svc")
    svc_logger.addHandler(handler)

    fake_token = "xoxb-SHOULD-NOT-APPEAR-IN-LOGS"
    # _get_bot_token을 직접 호출해도 token 값이 로그에 찍히지 않아야 함
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
    """/slack/* 와일드카드는 공개하지 않음 — /slack/other 는 비공개."""
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
# 보조: _retry_delay 단위 테스트
# ─────────────────────────────────────────────────────────────────────────────
def test_retry_delay_values():
    assert _retry_delay(0) == 1
    assert _retry_delay(1) == 5
    assert _retry_delay(2) == 15
    assert _retry_delay(99) == 15  # 상한 클램프


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
