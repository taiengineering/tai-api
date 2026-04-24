"""
작업자 현장 점검 제출 API — v1.1.0

v1.1.0 (2026-04-24):
  [ADD] Authorization 검증 (Optional — 있으면 검증, 없으면 phone 기반)
  [ADD] items[].photo_urls 필드 수용
  [ADD] worker_id, factory_id, schedule_id, inspection_type 필드

API:
  POST /worker-check/submit   점검 결과 저장
  GET  /worker-check/recent   최근 점검 이력 조회
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from db.supabase_client import get_supabase

log = logging.getLogger(__name__)
router = APIRouter(prefix="/worker-check", tags=["WorkerCheck"])


def _optional_auth(authorization: Optional[str] = Header(None)) -> Optional[dict]:
    """Authorization이 있으면 검증, 없으면 None 반환."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.replace("Bearer ", "")
    supabase = get_supabase()
    try:
        ur = supabase.auth.get_user(token)
        if not ur or not ur.user:
            raise HTTPException(status_code=401, detail={"error": "AUTH_EXPIRED"})
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail={"error": "AUTH_EXPIRED"})
    res = supabase.table("users").select("*").eq("auth_id", str(ur.user.id)).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
    return res.data[0]


class CheckItem(BaseModel):
    name: str
    result: str            # ok | bad
    memo: Optional[str] = None
    note: Optional[str] = None       # 구버전 호환
    photo_urls: Optional[List[str]] = None


class CheckSubmitBody(BaseModel):
    phone: str             # 점검자 전화번호
    worker_id: Optional[str] = None
    factory_id: Optional[str] = None
    schedule_id: Optional[str] = None
    inspection_type: Optional[str] = None  # BEFORE_WORK | BEFORE_WORK_CON
    asset_name: Optional[str] = None       # 설비명
    items: List[CheckItem]
    factory_name: Optional[str] = None
    submitted_at: Optional[str] = None


@router.post("/submit")
def submit_check(
    body: CheckSubmitBody,
    current_user: Optional[dict] = Depends(_optional_auth),
):
    """
    작업자 점검 제출.
    1. users 테이블에서 전화번호로 inspector_id 조회
    2. safety_inspections 점검 세션 생성
    3. safety_inspection_results 항목별 결과 저장
    """
    supabase = get_supabase()
    now = datetime.now(timezone.utc).isoformat()
    clean_phone = body.phone.replace("-", "").replace(" ", "")

    # 1. 점검자 ID 조회 (users 또는 worker_registry)
    inspector_id = None
    u = supabase.table("users").select("id, name").eq("phone", clean_phone).limit(1).execute()
    if not u.data:
        fmt = f"{clean_phone[:3]}-{clean_phone[3:7]}-{clean_phone[7:]}"
        u = supabase.table("users").select("id, name").eq("phone", fmt).limit(1).execute()
    if u.data:
        inspector_id = u.data[0]["id"]
        inspector_name = u.data[0].get("name", "")
    else:
        # worker_registry fallback
        w = supabase.table("worker_registry").select("id, name").eq("phone", clean_phone).limit(1).execute()
        if w.data:
            inspector_id = w.data[0]["id"]
            inspector_name = w.data[0].get("name", "")
        else:
            inspector_name = clean_phone

    # 2. safety_inspections 점검 세션 생성
    has_issue = any(item.result == "bad" for item in body.items)
    status_code = "ISSUE" if has_issue else "COMPLETED"

    ins_res = supabase.table("safety_inspections").insert({
        "inspector_id": inspector_id,
        "inspection_date": now,
        "status_code": status_code,
        # asset_id 없으면 널로
    }).execute()

    if not ins_res.data:
        raise HTTPException(status_code=500, detail="점검 세션 생성 실패")

    inspection_id = ins_res.data[0]["id"]

    # 3. 항목별 결과 저장
    result_rows = []
    for item in body.items:
        row_data = {
            "inspection_id": inspection_id,
            "item_name": item.name,
            "result_code": "NORMAL" if item.result == "ok" else "ABNORMAL",
            "value_text": item.result,
            "note": item.memo or item.note or "",
            "checked_at": now,
        }
        if item.photo_urls:
            row_data["photo_urls"] = item.photo_urls
        result_rows.append(row_data)

    if result_rows:
        supabase.table("safety_inspection_results").insert(result_rows).execute()

    issue_items = [i.name for i in body.items if i.result == "bad"]
    log.info(f"[WorkerCheck] 저장 inspection_id={inspection_id} phone={clean_phone} issues={issue_items}")

    return {
        "status": "success",
        "message": "점검 결과가 저장됐습니다.",
        "data": {
            "inspection_id": inspection_id,
            "status": status_code,
            "has_issue": has_issue,
            "issue_items": issue_items,
            "inspector": inspector_name,
            "total_items": len(body.items),
        }
    }


@router.get("/recent")
def get_recent_checks(phone: str, limit: int = 5):
    """
    점검자의 최근 점검 이력 조회
    """
    supabase = get_supabase()
    clean = phone.replace("-", "").replace(" ", "")

    inspector_id = None
    u = supabase.table("users").select("id").eq("phone", clean).limit(1).execute()
    if not u.data:
        u = supabase.table("users").select("id").eq("phone", f"{clean[:3]}-{clean[3:7]}-{clean[7:]}").limit(1).execute()
    if u.data:
        inspector_id = u.data[0]["id"]

    if not inspector_id:
        return {"status": "success", "data": {"items": []}}

    res = supabase.table("safety_inspections") \
        .select("id, inspection_date, status_code") \
        .eq("inspector_id", inspector_id) \
        .order("inspection_date", desc=True) \
        .limit(limit).execute()

    return {"status": "success", "data": {"items": res.data or []}}
