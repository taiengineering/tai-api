"""공개 헬스 엔드포인트 (/health, /health/deep)."""
from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from db.database import get_supabase
from services.health_registry import (
    ERROR_MESSAGES_KO,
    build_alert_message_ko,
    build_sms_message_ko,
    get_overall_status,
    run_all_probes,
)

router = APIRouter(tags=["health"])


@router.get("/health/live")
def health_live():
    """
    프로세스 기동 확인 전용 (DB·외부 호출 없음).
    Railway / Docker 헬스체크에 권장 — 빠른 liveness.
    """
    return JSONResponse(status_code=200, content={"status": "live"})


@router.get("/health")
def health_check():
    checks = {}
    sb = None
    try:
        sb = get_supabase()
        sb.table("system_codes").select("code").limit(1).execute()
        checks["db"] = "ok"
    except Exception as e:
        checks["db"] = f"fail: {str(e)[:100]}"
    try:
        if sb is None:
            sb = get_supabase()
        res = sb.table("master_building_legal_rules").select("id").eq("is_active", True).limit(1).execute()
        checks["law_engine"] = "ok" if res.data else "empty"
    except Exception as e:
        checks["law_engine"] = f"fail: {str(e)[:100]}"
    try:
        if sb is None:
            sb = get_supabase()
        res = sb.table("fix_chat_sessions").select("id").limit(1).execute()
        checks["fix_chat"] = "ok"
    except Exception as e:
        checks["fix_chat"] = f"fail: {str(e)[:100]}"
    all_ok = all(v == "ok" for v in checks.values())
    return JSONResponse(
        status_code=200,
        content={"status": "healthy" if all_ok else "degraded", "checks": checks},
    )


@router.get("/health/deep")
async def health_deep(secret: str = Query(...)):
    """
    등록된 모든 서비스 프로브를 실행하여 상태 확인.
    6시간마다 GitHub Actions 또는 수동 호출.
    """
    expected = os.environ.get("HEALTH_DEEP_SECRET", "tai-health-2026")
    if secret != expected:
        raise HTTPException(status_code=403, detail="Invalid secret")

    results = await run_all_probes()
    status = get_overall_status(results)

    failed = [k for k, v in results.items() if v.get("status") == "fail"]

    response = {
        "status": status,
        "status_ko": ERROR_MESSAGES_KO.get(status, ""),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "probe_count": len(results),
        "fail_count": len(failed),
        "warn_count": sum(1 for v in results.values() if v.get("status") == "warn"),
        "probes": results,
    }

    if failed:
        response["alert_ko"] = build_alert_message_ko(status, failed, results)
        response["sms_ko"] = build_sms_message_ko(status, failed, results)

    return response
