"""Internal Scheduler — WO-QA-CONTROL-PHASE2E-001.

POST /internal/scheduler/qa/tick  — QA scheduler tick (X-Internal-Secret 인증).

호출 주체: Railway cron 또는 외부 scheduler.
"""
import logging
import os
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, status

from db.supabase_client import get_supabase
from services.qa_scheduler_svc import scheduler_tick

log = logging.getLogger("internal_scheduler")

router = APIRouter(prefix="/internal/scheduler", tags=["internal-scheduler"])


def _auth(x_internal_secret: Optional[str]) -> None:
    expected = os.environ.get("INTERNAL_API_SECRET")
    if not expected or x_internal_secret != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid internal secret")


@router.post("/qa/tick")
async def qa_scheduler_tick(
    x_internal_secret: Optional[str] = Header(None, alias="X-Internal-Secret"),
):
    """QA scheduler 한 틱 실행.

    due schedule 조회 → 중복 방지 → run 생성 → GitHub dispatch → next_run_at 갱신.
    """
    _auth(x_internal_secret)
    supabase = get_supabase()
    result = await scheduler_tick(supabase)
    return {"status": "ok", "result": result}
