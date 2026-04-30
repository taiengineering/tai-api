"""TBM 참석자 이상 표시 API (issue_flag + issue_note)

관리감독자가 TBM 참석자에게 이상 표시를 할 때 사용.
평상시는 issue_flag=false(기본값). 이상 시에만 true + 사유 기입.

엔드포인트:
  PATCH /tbm/{tbm_id}/attendees/{attendee_id}/issue
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db.supabase_client import get_supabase

router = APIRouter(prefix="/tbm", tags=["tbm"])


class IssueBody(BaseModel):
    issue_flag: bool = True
    issue_note: Optional[str] = None


@router.patch("/{tbm_id}/attendees/{attendee_id}/issue")
def update_attendee_issue(tbm_id: str, attendee_id: str, body: IssueBody):
    """
    참석자 이상 표시/해제.

    - issue_flag=true + issue_note="건강이상 - 피로 호소" → 이상 표시
    - issue_flag=false → 이상 해제 (오입력 시 복원)
    """
    supabase = get_supabase()
    update = {
        "issue_flag": body.issue_flag,
        "issue_note": body.issue_note if body.issue_flag else None,
    }
    res = (
        supabase.table("tbm_attendees")
        .update(update)
        .eq("id", attendee_id)
        .eq("meeting_id", tbm_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="참석자를 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}
