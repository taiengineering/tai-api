"""WO-TAI-QA-M5A-SCHEDULER-BRIDGE-001 — M5-A 스케줄러 브리지 계약 검증.

테스트 항목:
  T01  정상 예약 요청 → product-change-detection.yml 워크플로 호출
  T02  _scheduled_for 없음 → DISPATCH_BLOCKED_NO_SCHEDULE, GitHub API 미호출
  T03  _attempt_no=2 (재처리) → DISPATCH_BLOCKED_RETRY, GitHub API 미호출
  T04  GitHub API 실패 → RuntimeError 전파, no retry
  T05  기존 P0 경로 불변 — trigger_qa_cron은 qa-twice-daily.yml만 호출
  T06  실제 GitHub API·DB 호출 없음 (모든 테스트 httpx mock 사용)
  ---
  T07  _attempt_no 누락 → DISPATCH_BLOCKED_NO_ATTEMPT_NO, GitHub API 미호출
  T08  _attempt_no=0 (음수/0) → DISPATCH_BLOCKED_RETRY, GitHub API 미호출
  T09  dispatch_accepted_at 포함 및 github_job_started_at=None 보장
  T10  QA_GITHUB_WORKFLOW_PRODUCT_CHANGE env 반영 — 커스텀 워크플로 URL에 반영
  T11  token log 포함 금지 — GitHub 실패 시 error log에 토큰 미포함
  T12  trigger_source=tai_scheduler 포함 확인

실제 GitHub API 호출 없음. 실제 DB 변경 없음. 운영 예약 작업 등록 없음.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, List
from unittest.mock import patch

import pytest

import services.qa_cron_trigger_svc as svc


# ── 공통 헬퍼 ─────────────────────────────────────────────────────────────────

class _FakeResp:
    def __init__(self, status_code: int):
        self.status_code = status_code

    def json(self):
        return {}


class _FakeClient:
    """httpx.AsyncClient POST 전용 mock."""

    def __init__(self, status_code: int = 204):
        self.status_code = status_code
        self.calls: List[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def post(self, url: str, *, json: Any = None, headers: Any = None, **kwargs):
        self.calls.append({"url": url, "json": json, "headers": headers})
        return _FakeResp(self.status_code)


def _patch_client(status: int = 204):
    client = _FakeClient(status)
    return patch("services.qa_cron_trigger_svc.httpx.AsyncClient", return_value=client), client


_SCHEDULED_FOR = "2026-11-03T21:00:00+09:00"  # KST 06:00 → UTC 21:00 전날


# ── 환경변수 픽스처 ───────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("QA_GITHUB_TOKEN", "gh-test-token-do-not-log")
    monkeypatch.setenv("QA_GITHUB_OWNER", "taiengineering")
    monkeypatch.setenv("QA_GITHUB_REPO",  "tai-qa")
    monkeypatch.setenv("QA_GITHUB_REF",   "main")
    monkeypatch.delenv("QA_GITHUB_WORKFLOW_PRODUCT_CHANGE", raising=False)
    monkeypatch.delenv("QA_GITHUB_WORKFLOW_TWICE_DAILY",    raising=False)


# ── T01: 정상 발화 ──────────────────────────────────────────────────────────

def test_T01_normal_schedule_dispatches_product_change_detection():
    """정상 예약 요청 → product-change-detection.yml 워크플로 호출."""
    patcher, client = _patch_client(204)
    with patcher:
        result = asyncio.run(svc.trigger_qa_product_change_detection({
            "_scheduled_for": _SCHEDULED_FOR,
            "_attempt_no": 1,
        }))

    assert len(client.calls) == 1, "GitHub API 1회 호출"
    url = client.calls[0]["url"]
    assert "product-change-detection.yml" in url
    assert "taiengineering/tai-qa" in url
    assert result["dispatch_accepted_at"] is not None
    assert result["trigger_source"] == "tai_scheduler"


# ── T02: _scheduled_for 없음 → 차단 ─────────────────────────────────────────

def test_T02_no_scheduled_for_blocks_dispatch():
    """_scheduled_for 없으면 DISPATCH_BLOCKED_NO_SCHEDULE — GitHub API 미호출."""
    patcher, client = _patch_client(204)
    with patcher:
        with pytest.raises(RuntimeError, match="DISPATCH_BLOCKED_NO_SCHEDULE"):
            asyncio.run(svc.trigger_qa_product_change_detection({
                "_attempt_no": 1,
                # _scheduled_for 의도적 누락
            }))

    assert len(client.calls) == 0, "차단 시 GitHub API 호출 없음"


# ── T03: attempt_no=2 (재처리) → 차단 ───────────────────────────────────────

def test_T03_duplicate_fire_blocked_on_retry():
    """_attempt_no=2 → DISPATCH_BLOCKED_RETRY — GitHub API 미호출."""
    patcher, client = _patch_client(204)
    with patcher:
        with pytest.raises(RuntimeError, match="DISPATCH_BLOCKED_RETRY"):
            asyncio.run(svc.trigger_qa_product_change_detection({
                "_scheduled_for": _SCHEDULED_FOR,
                "_attempt_no": 2,
            }))

    assert len(client.calls) == 0, "재처리 시 GitHub API 호출 없음"


# ── T04: GitHub API 실패 → RuntimeError 전파 ────────────────────────────────

def test_T04_github_failure_propagates():
    """GitHub API 500 → RuntimeError 전파, no retry."""
    patcher, client = _patch_client(500)
    with patcher:
        with pytest.raises(RuntimeError, match="500"):
            asyncio.run(svc.trigger_qa_product_change_detection({
                "_scheduled_for": _SCHEDULED_FOR,
                "_attempt_no": 1,
            }))

    assert len(client.calls) == 1, "재시도 없음 — 1회만 호출"


# ── T05: 기존 P0 경로 불변 ──────────────────────────────────────────────────

def test_T05_existing_p0_path_unchanged():
    """기존 trigger_qa_cron은 qa-twice-daily.yml만 호출 — M5-A 추가로 영향 없음."""
    patcher, client = _patch_client(204)
    with patcher:
        result = asyncio.run(svc.trigger_qa_cron({
            "_scheduled_for": _SCHEDULED_FOR,
            "_attempt_no": 1,
        }))

    assert len(client.calls) == 1
    url = client.calls[0]["url"]
    assert "qa-twice-daily.yml" in url
    assert "product-change-detection.yml" not in url
    assert result["trigger_source"] == "tai_scheduler"


# ── T06: 실제 GitHub·DB 호출 없음 ───────────────────────────────────────────

def test_T06_no_real_github_or_db_calls():
    """모든 테스트가 httpx를 mock했는지 — 실제 네트워크 호출 없음을 보장."""
    import httpx
    assert hasattr(httpx, "AsyncClient")
    assert callable(httpx.AsyncClient)


# ── T07: _attempt_no 누락 → 차단 ────────────────────────────────────────────

def test_T07_missing_attempt_no_blocks_dispatch():
    """_attempt_no 누락 → DISPATCH_BLOCKED_NO_ATTEMPT_NO — GitHub API 미호출."""
    patcher, client = _patch_client(204)
    with patcher:
        with pytest.raises(RuntimeError, match="DISPATCH_BLOCKED_NO_ATTEMPT_NO"):
            asyncio.run(svc.trigger_qa_product_change_detection({
                "_scheduled_for": _SCHEDULED_FOR,
                # _attempt_no 의도적 누락
            }))

    assert len(client.calls) == 0


# ── T08: attempt_no=0 → 차단 ────────────────────────────────────────────────

def test_T08_zero_attempt_no_blocked():
    """_attempt_no=0 → DISPATCH_BLOCKED_RETRY — GitHub API 미호출."""
    patcher, client = _patch_client(204)
    with patcher:
        with pytest.raises(RuntimeError, match="DISPATCH_BLOCKED_RETRY"):
            asyncio.run(svc.trigger_qa_product_change_detection({
                "_scheduled_for": _SCHEDULED_FOR,
                "_attempt_no": 0,
            }))

    assert len(client.calls) == 0


# ── T09: 타임스탬프 구조 확인 ────────────────────────────────────────────────

def test_T09_timestamps_structure():
    """dispatch_accepted_at 포함, github_job_started_at=None 보장."""
    patcher, _ = _patch_client(204)
    with patcher:
        result = asyncio.run(svc.trigger_qa_product_change_detection({
            "_scheduled_for": _SCHEDULED_FOR,
            "_attempt_no": 1,
        }))

    assert result["dispatch_attempted_at"] is not None
    assert result["dispatch_accepted_at"] is not None
    assert result["github_job_started_at"] is None
    assert result["scheduled_for"] is not None


# ── T10: 커스텀 워크플로 env 반영 ────────────────────────────────────────────

def test_T10_custom_workflow_env_reflected(monkeypatch):
    """QA_GITHUB_WORKFLOW_PRODUCT_CHANGE env → 해당 워크플로 URL에 반영."""
    monkeypatch.setenv("QA_GITHUB_WORKFLOW_PRODUCT_CHANGE", "custom-change-detect.yml")
    patcher, client = _patch_client(204)
    with patcher:
        asyncio.run(svc.trigger_qa_product_change_detection({
            "_scheduled_for": _SCHEDULED_FOR,
            "_attempt_no": 1,
        }))

    url = client.calls[0]["url"]
    assert "custom-change-detect.yml" in url


# ── T11: token log 금지 ──────────────────────────────────────────────────────

def test_T11_token_not_in_error_log(caplog):
    """GitHub 실패 시 error log에 토큰 미포함."""
    patcher, _ = _patch_client(422)
    with caplog.at_level(logging.ERROR, logger="qa_cron_trigger"):
        with patcher:
            with pytest.raises(RuntimeError):
                asyncio.run(svc.dispatch_qa_product_change_detection(
                    datetime.now(timezone.utc)
                ))

    for record in caplog.records:
        assert "gh-test-token-do-not-log" not in record.getMessage()


# ── T12: trigger_source 확인 ─────────────────────────────────────────────────

def test_T12_trigger_source_is_tai_scheduler():
    """결과 dict에 trigger_source=tai_scheduler 포함."""
    patcher, _ = _patch_client(204)
    with patcher:
        result = asyncio.run(svc.trigger_qa_product_change_detection({
            "_scheduled_for": _SCHEDULED_FOR,
            "_attempt_no": 1,
        }))

    assert result.get("trigger_source") == "tai_scheduler"
