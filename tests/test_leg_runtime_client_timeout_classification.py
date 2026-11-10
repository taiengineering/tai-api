"""WP-10B: leg_runtime_client.py timeout 오류 분류 단위 테스트.

BOUNDARY_OBSERVED_CASES: CST-0411/0428/0445/0460/0461 — C4 HTTP read timeout.

Test registry:
  TC1  ConnectTimeout -> LegRuntimeError("connect timeout: ...")
  TC2  ReadTimeout    -> LegRuntimeError("read timeout: ...")
  TC3  TimeoutException(base) -> LegRuntimeError("request timeout: ...")
  TC4  기타 네트워크 예외 -> LegRuntimeError("request failed: ...")
  TC5  LEG_RUNTIME_TIMEOUT 기본값 >= 30.0 (5건 관측 기준 충분)
  TC6  evaluate_rtm ConnectTimeout → LegRuntimeError("connect timeout: ...")
  TC7  evaluate_rtm ReadTimeout    → LegRuntimeError("read timeout: ...")
  TC8  fetch_source_texts ReadTimeout → LegRuntimeError("read timeout: ...")
  TC9  fetch_evidence_rows ReadTimeout → LegRuntimeError("read timeout: ...")
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

import httpx
import clients.leg_runtime_client as leg


# ── helpers ──────────────────────────────────────────────────────────────────

def _enable(monkeypatch):
    monkeypatch.setattr(leg, "LEG_RUNTIME_URL", "http://leg.test")


# ── TC1: evaluate() ConnectTimeout ──────────────────────────────────────────

def test_tc1_evaluate_connect_timeout(monkeypatch):
    """TC1: ConnectTimeout -> LegRuntimeError 메시지가 'connect timeout' 포함."""
    _enable(monkeypatch)
    monkeypatch.setattr(leg.httpx, "post", MagicMock(
        side_effect=httpx.ConnectTimeout("connect timed out")
    ))
    with pytest.raises(leg.LegRuntimeError, match="connect timeout"):
        leg.evaluate({})


# ── TC2: evaluate() ReadTimeout ─────────────────────────────────────────────

def test_tc2_evaluate_read_timeout(monkeypatch):
    """TC2: ReadTimeout -> LegRuntimeError 메시지가 'read timeout' 포함."""
    _enable(monkeypatch)
    monkeypatch.setattr(leg.httpx, "post", MagicMock(
        side_effect=httpx.ReadTimeout("read timed out")
    ))
    with pytest.raises(leg.LegRuntimeError, match="read timeout"):
        leg.evaluate({})


# ── TC3: evaluate() TimeoutException(base) ──────────────────────────────────

def test_tc3_evaluate_generic_timeout(monkeypatch):
    """TC3: httpx.TimeoutException base -> LegRuntimeError 메시지가 'request timeout' 포함."""
    _enable(monkeypatch)
    monkeypatch.setattr(leg.httpx, "post", MagicMock(
        side_effect=httpx.TimeoutException("pool timeout")
    ))
    with pytest.raises(leg.LegRuntimeError, match="request timeout"):
        leg.evaluate({})


# ── TC4: evaluate() 기타 예외 ───────────────────────────────────────────────

def test_tc4_evaluate_other_exception(monkeypatch):
    """TC4: ConnectionError 등 기타 예외 -> LegRuntimeError("request failed: ...")."""
    _enable(monkeypatch)
    monkeypatch.setattr(leg.httpx, "post", MagicMock(
        side_effect=ConnectionError("DNS fail")
    ))
    with pytest.raises(leg.LegRuntimeError, match="request failed"):
        leg.evaluate({})


# ── TC5: LEG_RUNTIME_TIMEOUT 기본값 >=30.0 ──────────────────────────────────

def test_tc5_default_timeout_sufficient():
    """TC5: LEG_RUNTIME_TIMEOUT 기본값이 30.0 이상 — 5건 관측 임계값 보증."""
    # env override 없는 순수 default: os.getenv fallback "30.0"
    # 모듈 로드 시 이미 float 변환됨. 현재 값이 30.0 이상인지 확인.
    assert leg.LEG_RUNTIME_TIMEOUT >= 30.0, (
        f"LEG_RUNTIME_TIMEOUT={leg.LEG_RUNTIME_TIMEOUT} < 30.0 — "
        "CST-0411/0428/0445/0460/0461 read timeout 재발 위험"
    )


# ── TC6: evaluate_rtm() ConnectTimeout ──────────────────────────────────────

def test_tc6_evaluate_rtm_connect_timeout(monkeypatch):
    """TC6: evaluate_rtm ConnectTimeout -> LegRuntimeError("connect timeout: ...")."""
    _enable(monkeypatch)
    monkeypatch.setattr(leg.httpx, "post", MagicMock(
        side_effect=httpx.ConnectTimeout("connect timed out")
    ))
    with pytest.raises(leg.LegRuntimeError, match="connect timeout"):
        leg.evaluate_rtm({})


# ── TC7: evaluate_rtm() ReadTimeout ─────────────────────────────────────────

def test_tc7_evaluate_rtm_read_timeout(monkeypatch):
    """TC7: evaluate_rtm ReadTimeout -> LegRuntimeError("read timeout: ...")."""
    _enable(monkeypatch)
    monkeypatch.setattr(leg.httpx, "post", MagicMock(
        side_effect=httpx.ReadTimeout("read timed out")
    ))
    with pytest.raises(leg.LegRuntimeError, match="read timeout"):
        leg.evaluate_rtm({})


# ── TC8: fetch_source_texts() ReadTimeout ───────────────────────────────────

def test_tc8_fetch_source_texts_read_timeout(monkeypatch):
    """TC8: fetch_source_texts ReadTimeout -> LegRuntimeError("read timeout: ...")."""
    _enable(monkeypatch)
    monkeypatch.setattr(leg.httpx, "post", MagicMock(
        side_effect=httpx.ReadTimeout("read timed out")
    ))
    with pytest.raises(leg.LegRuntimeError, match="read timeout"):
        leg.fetch_source_texts(["atom-1"])


# ── TC9: fetch_evidence_rows() ReadTimeout ──────────────────────────────────

def test_tc9_fetch_evidence_rows_read_timeout(monkeypatch):
    """TC9: fetch_evidence_rows ReadTimeout -> LegRuntimeError("read timeout: ...")."""
    _enable(monkeypatch)
    monkeypatch.setattr(leg.httpx, "post", MagicMock(
        side_effect=httpx.ReadTimeout("read timed out")
    ))
    with pytest.raises(leg.LegRuntimeError, match="read timeout"):
        leg.fetch_evidence_rows(["산업안전보건법"], [38])
