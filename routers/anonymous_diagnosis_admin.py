"""익명 무료 법령진단 — 관리자 조회/관리 라우터 (분리본).

WO-ISOLATE-001: routers/anonymous_diagnosis.py 에서 admin 핸들러만 분리.
- 생성(POST "")·조회(GET /{token})·claim·transform·recommend-plan 은 라이브 미사용이라
  registry 등록 해제로 격리한다.
- admin(/admin/*) 은 tai-admin(anon-diagnosis-list)이 라이브 데이터(anonymous_diagnosis_results,
  source_type=free_diag/paid_diag/site_free/site_free_leg 포함) 조회에 사용하므로 이 파일로 보존한다.
- 저장소 계약 불변: 동일 테이블 anonymous_diagnosis_results, 동일 URL(/anonymous-diagnosis/admin/*).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services.time import now_kst

router = APIRouter(prefix="/anonymous-diagnosis", tags=["익명 무료진단 (관리자)"])

ADMIN_ALLOWED_STATUS = frozenset({"ACTIVE", "CLAIMED", "EXPIRED"})


def _now() -> datetime:
    return now_kst()


class AdminAnonDiagPatch(BaseModel):
    status: Optional[str] = Field(None, description="ACTIVE | CLAIMED | EXPIRED")


# ── 관리자 엔드포인트 ────────────────────────────────────────────────

@router.get("/admin/list")
def list_anonymous_diagnoses(
    page: int = 1, size: int = 20,
    status: Optional[str] = None, keyword: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    q = supabase.table("anonymous_diagnosis_results").select(
        "id,public_token,input_data,created_at,expires_at,claimed_user_id,status,source_type",
        count="exact",
    )
    if status: q = q.eq("status", status)
    kw = (keyword or "").strip()
    if kw:     q = q.ilike("public_token", f"%{kw}%")
    offset = (page - 1) * size
    res = q.order("created_at", desc=True).range(offset, offset + size - 1).execute()
    return {"status": "success", "data": {
        "items": res.data, "total": res.count, "page": page, "size": size,
        "total_pages": -(-res.count // size) if res.count else 0,
    }}


@router.get("/admin/detail/{record_id}")
def admin_get_anonymous_diagnosis_detail(record_id: str, current_user: dict = Depends(get_current_user)):
    supabase = get_supabase()
    res = supabase.table("anonymous_diagnosis_results").select("*").eq("id", record_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="레코드를 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}


@router.patch("/admin/{record_id}")
def admin_patch_anonymous_diagnosis(record_id: str, body: AdminAnonDiagPatch, current_user: dict = Depends(get_current_user)):
    if body.status is None:
        raise HTTPException(status_code=422, detail="변경할 status가 필요합니다.")
    if body.status not in ADMIN_ALLOWED_STATUS:
        raise HTTPException(status_code=422, detail="허용되지 않는 status입니다.")
    supabase = get_supabase()
    res = supabase.table("anonymous_diagnosis_results").update({"status": body.status}).eq("id", record_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="레코드를 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}


@router.post("/admin/expire-stale")
def expire_stale_records():
    supabase = get_supabase()
    now_iso = _now().isoformat()
    res = (supabase.table("anonymous_diagnosis_results")
           .update({"status": "EXPIRED"})
           .eq("status", "ACTIVE")
           .lt("expires_at", now_iso).execute())
    return {"status": "success", "expired_count": len(res.data) if res.data else 0}


@router.delete("/admin/{record_id}")
def delete_anonymous_diagnosis(record_id: str, current_user: dict = Depends(get_current_user)):
    supabase = get_supabase()
    res = supabase.table("anonymous_diagnosis_results").delete().eq("id", record_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="레코드를 찾을 수 없습니다.")
    return {"status": "success", "message": "삭제되었습니다."}
