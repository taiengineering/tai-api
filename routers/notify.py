"""통합 발송 라우터 (WO-8C NotifyDispatcher).

Goal: G-ms4je4z3-33eada
- POST /notify/send — 단일 발송(SMS/MAIL/PUSH).
- POST /notify/dry-run — 대량발송 전 미리보기(대상 수·유효/무효·샘플).
- 얇은 위임: services.notify_svc.
"""
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.notify_svc import NotifyError, dry_run_preview, send

router = APIRouter(prefix="/notify", tags=["통합발송"])


class SendBody(BaseModel):
    channel: str                        # SMS | MAIL | PUSH
    target: str                         # 수신번호 또는 수신메일
    message: Optional[str] = None       # SMS 본문 / MAIL text
    subject: Optional[str] = None       # MAIL 제목
    html: Optional[str] = None          # MAIL html
    title: Optional[str] = None         # SMS 제목(LMS)
    by: Optional[str] = None


class DryRunBody(BaseModel):
    channel: str
    targets: List[str]
    sample_size: int = 5


@router.post("/send")
def notify_send(body: SendBody):
    """단일 발송."""
    try:
        result = send(
            body.channel, target=body.target, message=body.message,
            subject=body.subject, html=body.html, title=body.title, actor_id=body.by,
        )
    except NotifyError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    return {"status": "success", "data": result}


@router.post("/dry-run")
def notify_dry_run(body: DryRunBody):
    """대량발송 전 미리보기 (실제 발송 없음)."""
    try:
        result = dry_run_preview(body.channel, body.targets, sample_size=body.sample_size)
    except NotifyError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    return {"status": "success", "data": result}
