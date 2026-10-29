"""Slack Relay 수동 복구 진입점 — POST /internal/slack-relay/recover.

COR-01: run_relay_recovery_once() 실행 경로 완성.
운영 스케줄러 미설정 환경에서 관리자가 수동으로 복구를 트리거한다.
운영 스케줄러 등록은 별도 Owner Gate로 유지한다.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services.company_scope import _require_admin

router = APIRouter(prefix="/internal/slack-relay", tags=["slack-relay-internal"])


def _require_relay_admin(current: dict = Depends(get_current_user)) -> dict:
    _require_admin(current, get_supabase())
    return current


@router.post("/recover")
async def trigger_relay_recovery(
    current: dict = Depends(_require_relay_admin),
) -> JSONResponse:
    """PENDING/RETRY 행 수동 복구 트리거.

    스케줄러 없이 수동으로 복구 Worker를 실행한다.
    운영 DB에 직접 쓰지 않으며 기존 relay_svc 계약을 그대로 사용한다.
    """
    from services.slack_relay_svc import run_relay_recovery_once
    processed = await run_relay_recovery_once()
    return JSONResponse({"ok": True, "processed": processed})
