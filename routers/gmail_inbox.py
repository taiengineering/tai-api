"""Gmail 수신 폴링 라우터 (WO-8B).

Goal: G-ms4je4z3-33eada
- POST /mail/pull — Gmail 받은편지함 신규 메일을 mail_logs에 적재(수동/스케줄러 트리거).
- 얇은 위임: services.gmail_inbox_svc.pull_inbox.
- prefix /mail (기존 메일 네임스페이스와 동일).
"""
from fastapi import APIRouter, HTTPException, Query

from services.gmail_channel import GmailError

router = APIRouter(prefix="/mail", tags=["메일수신"])


@router.post("/pull")
def pull_gmail_inbox(
    query: str = Query(default="in:inbox", description="Gmail 검색 쿼리"),
    max_results: int = Query(default=50, ge=1, le=200),
):
    """Gmail 받은편지함 신규 메일을 어드민(mail_logs)으로 적재."""
    from services.gmail_inbox_svc import pull_inbox
    try:
        result = pull_inbox(query=query, max_results=max_results)
    except GmailError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    return {"status": "success", "data": result}
