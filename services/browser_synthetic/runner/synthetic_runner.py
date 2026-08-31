"""Synthetic Runner - Browser 기반 사용자 흐름 실행.

현재 단계: 실제 브라우저 자동화 최소화.
- URL 접근 + 응답 시간 측정 (httpx)
- Playwright skeleton (mock abstraction)
- 결과 저장 + Event 생성

절대 금지: Workflow Engine 직접 제어, Business Logic, 자동 복구.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx

from services.browser_synthetic.schemas import (
    ExecutionLogCreate,
    SyntheticEvent,
)
from services.browser_synthetic.events.execution_log_store import (
    create_execution_log,
)
from services.browser_synthetic.hooks.integrity_hook import (
    emit_synthetic_integrity_event,
)
from services.time import now_kst

logger = logging.getLogger(__name__)


async def run_check(check: dict) -> dict:
    """단일 synthetic check 실행.

    Args:
        check: browser_synthetic_check_registry row

    Returns:
        execution log dict
    """
    check_code = check.get("check_code", "UNKNOWN")
    target_url = check.get("target_url", "")
    timeout_sec = check.get("timeout_sec", 30)
    expected = check.get("expected_result") or {}
    check_type = check.get("check_type", "PAGE_LOAD")
    workflow_type = check.get("workflow_type", "COMMON")

    trace_id = f"syn-{uuid4().hex[:12]}"
    started_at = now_kst()
    start_ts = time.monotonic()

    execution_status = "SUCCESS"
    error_message = None
    payload: dict[str, Any] = {}

    try:
        result = await _execute_http_check(
            target_url, timeout_sec, expected, check_type
        )
        execution_status = result["status"]
        error_message = result.get("error")
        payload = result.get("payload", {})
    except Exception as e:
        execution_status = "ERROR"
        error_message = str(e)
        logger.error("Synthetic check %s error: %s", check_code, e)

    elapsed_ms = int((time.monotonic() - start_ts) * 1000)
    completed_at = now_kst()

    # Execution Log 저장
    log_entry = ExecutionLogCreate(
        check_code=check_code,
        trace_id=trace_id,
        execution_status=execution_status,
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=elapsed_ms,
        error_message=error_message,
        payload=payload,
    )
    saved = await create_execution_log(log_entry)

    # Synthetic Event → Hook (Integrity 연결 준비)
    event = SyntheticEvent(
        synthetic_check=check_code,
        workflow_type=workflow_type,
        execution_status=execution_status,
        duration_ms=elapsed_ms,
        trace_id=trace_id,
        occurred_at=completed_at,
        payload=payload,
    )
    await emit_synthetic_integrity_event(event)

    return saved


async def _execute_http_check(
    url: str,
    timeout_sec: int,
    expected: dict,
    check_type: str,
) -> dict:
    """최소 HTTP 체크 실행.

    현재 단계: httpx 기반 URL 접근 + 응답 코드 검증.
    향후: Playwright 기반 브라우저 자동화 확장.
    """
    # 상대 경로면 기본 base URL 붙임
    if url.startswith("/"):
        # TODO: 환경변수에서 base URL 읽기
        base = "http://localhost:8000"
        full_url = f"{base}{url}"
    else:
        full_url = url

    expected_status = expected.get("status_code", 200)

    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            resp = await client.get(full_url)

        actual_status = resp.status_code
        payload = {
            "url": full_url,
            "status_code": actual_status,
            "expected_status": expected_status,
            "check_type": check_type,
        }

        if actual_status == expected_status:
            return {"status": "SUCCESS", "payload": payload}
        else:
            return {
                "status": "FAILED",
                "error": f"Expected {expected_status}, got {actual_status}",
                "payload": payload,
            }

    except httpx.TimeoutException:
        return {
            "status": "TIMEOUT",
            "error": f"Timeout after {timeout_sec}s",
            "payload": {"url": full_url, "check_type": check_type},
        }
    except httpx.HTTPError as e:
        return {
            "status": "ERROR",
            "error": str(e),
            "payload": {"url": full_url, "check_type": check_type},
        }
