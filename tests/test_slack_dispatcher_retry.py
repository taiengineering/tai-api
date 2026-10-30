"""WO-TAI-QA-OPS-SLACK-RETRY-010 — slack_dispatcher.py retry 계약 검증.

테스트 항목:
  SR-01  최초 전송 성공 → return True
  SR-02  429 후 성공 (Retry-After 준수)
  SR-03  500/503 후 성공
  SR-04  Timeout 후 성공
  SR-05  400/401/403 즉시 종료 → return False (재시도 없음)
  SR-06  최대 재시도 초과 → return False
  SR-07  Retry-After 비정상 값 → 기본 딜레이 사용
  SR-08  ok=False + error=ratelimited 재시도
  SR-09  기존 호출 계약 회귀 (disabled, no token, no channel)

실제 Slack API 호출 없음 — httpx.AsyncClient 완전 mock.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── 환경 설정 헬퍼 ──────────────────────────────────────────────

def _env(extra: Optional[dict] = None) -> dict:
    base = {
        "SLACK_BOT_TOKEN1":      "xoxb-test-token",
        "SLACK_CH_QA":           "C_QA_TEST",
        "SLACK_WEBHOOK_ENABLED": "true",
    }
    if extra:
        base.update(extra)
    return base


# ── 응답 팩토리 ─────────────────────────────────────────────────

def _resp(status: int, ok: bool = True, error: str = "", headers: Optional[dict] = None) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.headers = headers or {}
    r.json.return_value = {"ok": ok, "error": error} if not ok else {"ok": True}
    return r


# ── 공통 send_slack 호출 래퍼 ───────────────────────────────────

def _call(mock_client, env_override: Optional[dict] = None):
    """QA_RUN_ERROR 이벤트로 send_slack 호출 (기본 환경변수 포함)."""
    from services.slack_dispatcher import send_slack
    env = _env(env_override)
    with patch.dict(os.environ, env, clear=False):
        return asyncio.run(
            send_slack(
                event_type="QA_RUN_ERROR",
                severity="INFO",
                title="Test QA Error",
            )
        )


# ════════════════════════════════════════════════════════════════
# SR-01: 최초 전송 성공
# ════════════════════════════════════════════════════════════════

def test_SR01_first_attempt_success():
    mock_post = AsyncMock(return_value=_resp(200))
    with patch("httpx.AsyncClient") as MockClient:
        MockClient.return_value.__aenter__ = AsyncMock(return_value=MagicMock(post=mock_post))
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
        result = _call(mock_post)
    assert result is True
    assert mock_post.call_count == 1


# ════════════════════════════════════════════════════════════════
# SR-02: 429 후 성공 (Retry-After 준수)
# ════════════════════════════════════════════════════════════════

def test_SR02_429_then_success():
    calls: List[Any] = []

    async def _mock_post(*a, **kw):
        calls.append(len(calls))
        if len(calls) == 1:
            return _resp(429, ok=False, headers={"Retry-After": "0.01"})
        return _resp(200)

    slept: List[float] = []

    async def _fake_sleep(secs: float):
        slept.append(secs)

    with patch("httpx.AsyncClient") as MockClient, \
         patch("services.slack_dispatcher.asyncio.sleep", side_effect=_fake_sleep):
        mock_client_inst = MagicMock()
        mock_client_inst.post = _mock_post
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_inst)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        env = _env()
        with patch.dict(os.environ, env, clear=False):
            from services.slack_dispatcher import send_slack
            result = asyncio.run(send_slack("QA_RUN_ERROR", "INFO", "Test 429"))

    assert result is True
    assert len(calls) == 2
    assert len(slept) == 1
    assert slept[0] == pytest.approx(0.01, abs=0.001)


# ════════════════════════════════════════════════════════════════
# SR-03: 500/503 후 성공
# ════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("status", [500, 503])
def test_SR03_5xx_then_success(status: int):
    calls: List[int] = []

    async def _mock_post(*a, **kw):
        calls.append(1)
        return _resp(status) if len(calls) == 1 else _resp(200)

    slept: List[float] = []

    async def _fake_sleep(secs: float):
        slept.append(secs)

    with patch("httpx.AsyncClient") as MockClient, \
         patch("services.slack_dispatcher.asyncio.sleep", side_effect=_fake_sleep):
        mock_client_inst = MagicMock()
        mock_client_inst.post = _mock_post
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_inst)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        env = _env()
        with patch.dict(os.environ, env, clear=False):
            from services.slack_dispatcher import send_slack
            result = asyncio.run(send_slack("QA_RUN_ERROR", "INFO", f"Test {status}"))

    assert result is True
    assert len(calls) == 2
    assert len(slept) == 1


# ════════════════════════════════════════════════════════════════
# SR-04: Timeout 후 성공
# ════════════════════════════════════════════════════════════════

def test_SR04_timeout_then_success():
    import httpx
    calls: List[int] = []

    async def _mock_post(*a, **kw):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ReadTimeout("timed out", request=None)
        return _resp(200)

    slept: List[float] = []

    async def _fake_sleep(secs: float):
        slept.append(secs)

    with patch("httpx.AsyncClient") as MockClient, \
         patch("services.slack_dispatcher.asyncio.sleep", side_effect=_fake_sleep):
        mock_client_inst = MagicMock()
        mock_client_inst.post = _mock_post
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_inst)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        env = _env()
        with patch.dict(os.environ, env, clear=False):
            from services.slack_dispatcher import send_slack
            result = asyncio.run(send_slack("QA_RUN_ERROR", "INFO", "Test timeout"))

    assert result is True
    assert len(calls) == 2
    assert len(slept) == 1


# ════════════════════════════════════════════════════════════════
# SR-05: 4xx (429 제외) 즉시 종료, 재시도 없음
# ════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("status", [400, 401, 403])
def test_SR05_4xx_no_retry(status: int):
    calls: List[int] = []

    async def _mock_post(*a, **kw):
        calls.append(1)
        return _resp(status)

    slept: List[float] = []

    async def _fake_sleep(secs: float):
        slept.append(secs)

    with patch("httpx.AsyncClient") as MockClient, \
         patch("services.slack_dispatcher.asyncio.sleep", side_effect=_fake_sleep):
        mock_client_inst = MagicMock()
        mock_client_inst.post = _mock_post
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_inst)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        env = _env()
        with patch.dict(os.environ, env, clear=False):
            from services.slack_dispatcher import send_slack
            result = asyncio.run(send_slack("QA_RUN_ERROR", "INFO", f"Test {status}"))

    assert result is False
    assert len(calls) == 1       # 재시도 없음
    assert len(slept) == 0


# ════════════════════════════════════════════════════════════════
# SR-06: 최대 재시도 초과 → return False
# ════════════════════════════════════════════════════════════════

def test_SR06_exhausted_retries():
    import httpx
    from services.slack_dispatcher import _RETRY_MAX

    calls: List[int] = []

    async def _mock_post(*a, **kw):
        calls.append(1)
        raise httpx.ReadTimeout("always timeout", request=None)

    async def _fake_sleep(_: float):
        pass

    with patch("httpx.AsyncClient") as MockClient, \
         patch("services.slack_dispatcher.asyncio.sleep", side_effect=_fake_sleep):
        mock_client_inst = MagicMock()
        mock_client_inst.post = _mock_post
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_inst)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        env = _env()
        with patch.dict(os.environ, env, clear=False):
            from services.slack_dispatcher import send_slack
            result = asyncio.run(send_slack("QA_RUN_ERROR", "INFO", "Test exhausted"))

    assert result is False
    assert len(calls) == _RETRY_MAX + 1   # 초기 1회 + _RETRY_MAX 재시도


# ════════════════════════════════════════════════════════════════
# SR-07: Retry-After 비정상 값 → 기본 딜레이 사용
# ════════════════════════════════════════════════════════════════

def test_SR07_invalid_retry_after_uses_default_delay():
    from services.slack_dispatcher import _RETRY_DELAYS

    calls: List[int] = []

    async def _mock_post(*a, **kw):
        calls.append(1)
        if len(calls) == 1:
            return _resp(429, ok=False, headers={"Retry-After": "not-a-number"})
        return _resp(200)

    slept: List[float] = []

    async def _fake_sleep(secs: float):
        slept.append(secs)

    with patch("httpx.AsyncClient") as MockClient, \
         patch("services.slack_dispatcher.asyncio.sleep", side_effect=_fake_sleep):
        mock_client_inst = MagicMock()
        mock_client_inst.post = _mock_post
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_inst)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        env = _env()
        with patch.dict(os.environ, env, clear=False):
            from services.slack_dispatcher import send_slack
            result = asyncio.run(send_slack("QA_RUN_ERROR", "INFO", "Test bad Retry-After"))

    assert result is True
    assert len(slept) == 1
    assert slept[0] == pytest.approx(_RETRY_DELAYS[0], abs=0.001)


# ════════════════════════════════════════════════════════════════
# SR-08: ok=False + error=ratelimited 재시도
# ════════════════════════════════════════════════════════════════

def test_SR08_ok_false_ratelimited_retries():
    calls: List[int] = []

    async def _mock_post(*a, **kw):
        calls.append(1)
        if len(calls) == 1:
            return _resp(200, ok=False, error="ratelimited", headers={"Retry-After": "0.01"})
        return _resp(200)

    slept: List[float] = []

    async def _fake_sleep(secs: float):
        slept.append(secs)

    with patch("httpx.AsyncClient") as MockClient, \
         patch("services.slack_dispatcher.asyncio.sleep", side_effect=_fake_sleep):
        mock_client_inst = MagicMock()
        mock_client_inst.post = _mock_post
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_inst)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        env = _env()
        with patch.dict(os.environ, env, clear=False):
            from services.slack_dispatcher import send_slack
            result = asyncio.run(send_slack("QA_RUN_ERROR", "INFO", "Test ratelimited ok=False"))

    assert result is True
    assert len(calls) == 2
    assert len(slept) == 1


# ════════════════════════════════════════════════════════════════
# SR-09: 기존 호출 계약 회귀 (disabled / no token / no channel)
# ════════════════════════════════════════════════════════════════

def test_SR09a_disabled_returns_false_without_http():
    called = []

    async def _mock_post(*a, **kw):
        called.append(1)
        return _resp(200)

    with patch("httpx.AsyncClient") as MockClient:
        mock_client_inst = MagicMock()
        mock_client_inst.post = _mock_post
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_inst)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        env = _env({"SLACK_WEBHOOK_ENABLED": "false"})
        with patch.dict(os.environ, env, clear=False):
            from services.slack_dispatcher import send_slack
            result = asyncio.run(send_slack("QA_RUN_ERROR", "INFO", "Test disabled"))

    assert result is False
    assert len(called) == 0      # HTTP 호출 없음


def test_SR09b_no_token_returns_false():
    called = []

    async def _mock_post(*a, **kw):
        called.append(1)
        return _resp(200)

    with patch("httpx.AsyncClient") as MockClient:
        mock_client_inst = MagicMock()
        mock_client_inst.post = _mock_post
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_inst)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        env = _env({"SLACK_BOT_TOKEN1": "", "SLACK_BOT_TOKEN": ""})
        with patch.dict(os.environ, env, clear=False):
            from services.slack_dispatcher import send_slack
            result = asyncio.run(send_slack("QA_RUN_ERROR", "INFO", "Test no token"))

    assert result is False
    assert len(called) == 0


def test_SR09c_no_channel_returns_false():
    called = []

    async def _mock_post(*a, **kw):
        called.append(1)
        return _resp(200)

    with patch("httpx.AsyncClient") as MockClient:
        mock_client_inst = MagicMock()
        mock_client_inst.post = _mock_post
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_inst)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        env = _env({"SLACK_CH_QA": ""})
        with patch.dict(os.environ, env, clear=False):
            from services.slack_dispatcher import send_slack
            result = asyncio.run(send_slack("QA_RUN_ERROR", "INFO", "Test no channel"))

    assert result is False
    assert len(called) == 0


def test_SR09d_ok_false_non_ratelimited_no_retry():
    """ok=False + error != ratelimited → 재시도 없이 즉시 False."""
    calls: List[int] = []

    async def _mock_post(*a, **kw):
        calls.append(1)
        return _resp(200, ok=False, error="invalid_auth")

    with patch("httpx.AsyncClient") as MockClient:
        mock_client_inst = MagicMock()
        mock_client_inst.post = _mock_post
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_inst)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        env = _env()
        with patch.dict(os.environ, env, clear=False):
            from services.slack_dispatcher import send_slack
            result = asyncio.run(send_slack("QA_RUN_ERROR", "INFO", "Test invalid_auth"))

    assert result is False
    assert len(calls) == 1
