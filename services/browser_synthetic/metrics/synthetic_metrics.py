"""Synthetic Metrics - 운영 상태 관측.

측정: success ratio, avg response time, fail ratio, timeout ratio.
주의: Business SLA 계산 금지 (현재 단계).
"""
from __future__ import annotations

import logging

from db.supabase_client import get_supabase
from services.browser_synthetic.schemas import SyntheticMetricsOut

logger = logging.getLogger(__name__)


async def compute_metrics(
    check_code: str, limit: int = 100
) -> SyntheticMetricsOut:
    """check_code별 최근 실행 기준 메트릭 계산.

    Args:
        check_code: 대상 체크 코드
        limit: 집계 대상 최대 건수

    Returns:
        SyntheticMetricsOut
    """
    sb = get_supabase()
    resp = (
        sb.table("browser_synthetic_execution_log")
        .select("execution_status, duration_ms")
        .eq("check_code", check_code)
        .order("started_at", desc=True)
        .limit(limit)
        .execute()
    )
    rows = resp.data or []
    total = len(rows)

    if total == 0:
        return SyntheticMetricsOut(
            check_code=check_code,
            total_executions=0,
            success_count=0,
            fail_count=0,
            timeout_count=0,
            error_count=0,
            success_ratio=0.0,
            fail_ratio=0.0,
            timeout_ratio=0.0,
            avg_duration_ms=None,
        )

    success = sum(1 for r in rows if r["execution_status"] == "SUCCESS")
    failed = sum(1 for r in rows if r["execution_status"] == "FAILED")
    timeout = sum(1 for r in rows if r["execution_status"] == "TIMEOUT")
    error = sum(1 for r in rows if r["execution_status"] == "ERROR")

    durations = [
        r["duration_ms"] for r in rows
        if r.get("duration_ms") is not None
    ]
    avg_dur = sum(durations) / len(durations) if durations else None

    return SyntheticMetricsOut(
        check_code=check_code,
        total_executions=total,
        success_count=success,
        fail_count=failed,
        timeout_count=timeout,
        error_count=error,
        success_ratio=round(success / total, 4),
        fail_ratio=round(failed / total, 4),
        timeout_ratio=round(timeout / total, 4),
        avg_duration_ms=round(avg_dur, 2) if avg_dur else None,
    )


async def compute_all_metrics() -> list[SyntheticMetricsOut]:
    """활성 체크 전체 메트릭."""
    sb = get_supabase()
    resp = (
        sb.table("browser_synthetic_check_registry")
        .select("check_code")
        .eq("enabled", True)
        .execute()
    )
    checks = resp.data or []
    results = []
    for c in checks:
        m = await compute_metrics(c["check_code"])
        results.append(m)
    return results
