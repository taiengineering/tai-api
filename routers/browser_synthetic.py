"""Browser Synthetic API Router.

Endpoints (경로 우선순위 순서):
- GET  /synthetic/checks/list          → 전체 체크 조회
- GET  /synthetic/metrics/all           → 전체 메트릭
- GET  /synthetic/metrics/{check_code}  → 체크별 메트릭
- GET  /synthetic/executions/recent     → 최근 실행 로그
- GET  /synthetic/executions/{check_code} → 체크별 실행 로그
- POST /synthetic/run/{check_code}      → 단건 체크 실행
- POST /synthetic/run-all               → 전체 실행
- GET  /synthetic/timeline/{trace_id}   → Timeline 조회

주의: 구체 경로를 파라미터 경로보다 먼저 선언.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from services.browser_synthetic.registry.check_registry import (
    get_all_checks,
    get_check_by_code,
    get_enabled_checks,
)
from services.browser_synthetic.runner.synthetic_runner import run_check
from services.browser_synthetic.events.execution_log_store import (
    get_executions_by_check,
    get_recent_executions,
)
from services.browser_synthetic.timeline.synthetic_timeline import (
    get_synthetic_timeline,
)
from services.browser_synthetic.metrics.synthetic_metrics import (
    compute_metrics,
    compute_all_metrics,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/synthetic", tags=["browser-synthetic"])


# ── 구체 경로 먼저 ─────────────────────────────────────────


@router.get("/checks/list")
async def api_list_checks():
    """전체 Synthetic 체크 조회."""
    try:
        checks = await get_all_checks()
        return {"ok": True, "data": checks}
    except Exception as e:
        logger.error("Checks list error: %s", e)
        raise HTTPException(500, detail=str(e))


@router.get("/metrics/all")
async def api_all_metrics():
    """전체 Synthetic 메트릭."""
    try:
        metrics = await compute_all_metrics()
        return {
            "ok": True,
            "data": [m.model_dump() for m in metrics],
        }
    except Exception as e:
        logger.error("All metrics error: %s", e)
        raise HTTPException(500, detail=str(e))


@router.get("/metrics/{check_code}")
async def api_check_metrics(check_code: str):
    """체크별 Synthetic 메트릭."""
    try:
        m = await compute_metrics(check_code)
        return {"ok": True, "data": m.model_dump()}
    except Exception as e:
        logger.error("Check metrics error: %s", e)
        raise HTTPException(500, detail=str(e))


@router.get("/executions/recent")
async def api_recent_executions(
    limit: int = Query(100, ge=1, le=500),
):
    """최근 Synthetic 실행 로그."""
    try:
        logs = await get_recent_executions(limit)
        return {"ok": True, "data": logs}
    except Exception as e:
        logger.error("Recent executions error: %s", e)
        raise HTTPException(500, detail=str(e))


@router.get("/executions/{check_code}")
async def api_check_executions(
    check_code: str,
    limit: int = Query(50, ge=1, le=500),
):
    """체크별 Synthetic 실행 로그."""
    try:
        logs = await get_executions_by_check(check_code, limit)
        return {"ok": True, "data": logs}
    except Exception as e:
        logger.error("Check executions error: %s", e)
        raise HTTPException(500, detail=str(e))


# ── 실행 ─────────────────────────────────────────────────


@router.post("/run/{check_code}")
async def api_run_check(check_code: str):
    """단건 Synthetic 체크 실행."""
    try:
        check = await get_check_by_code(check_code)
        if not check:
            raise HTTPException(404, detail=f"Check not found: {check_code}")
        if not check.get("enabled"):
            raise HTTPException(400, detail=f"Check disabled: {check_code}")
        result = await run_check(check)
        return {"ok": True, "data": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Run check error: %s", e)
        raise HTTPException(500, detail=str(e))


@router.post("/run-all")
async def api_run_all():
    """전체 활성 체크 실행."""
    try:
        checks = await get_enabled_checks()
        results = []
        for check in checks:
            try:
                r = await run_check(check)
                results.append(r)
            except Exception as e:
                logger.error("Run check %s failed: %s", check.get("check_code"), e)
                results.append({
                    "check_code": check.get("check_code"),
                    "execution_status": "ERROR",
                    "error_message": str(e),
                })
        return {"ok": True, "data": results, "total": len(results)}
    except Exception as e:
        logger.error("Run all error: %s", e)
        raise HTTPException(500, detail=str(e))


# ── Timeline (파라미터 경로 마지막) ───────────────────────────


@router.get("/timeline/{trace_id}")
async def api_synthetic_timeline(trace_id: str):
    """Synthetic Timeline 조회."""
    try:
        result = await get_synthetic_timeline(trace_id)
        return {"ok": True, "data": result}
    except Exception as e:
        logger.error("Synthetic timeline error: %s", e)
        raise HTTPException(500, detail=str(e))
