"""익명 무료 법령진단 — 관리자 조회/관리 라우터 (분리본).

WO-ISOLATE-001: routers/anonymous_diagnosis.py 에서 admin 핸들러만 분리.
- 생성(POST "")·조회(GET /{token})·claim·transform·recommend-plan 은 라이브 미사용이라
  registry 등록 해제로 격리한다.
- admin(/admin/*) 은 tai-admin(anon-diagnosis-list)이 라이브 데이터(anonymous_diagnosis_results,
  source_type=free_diag/paid_diag/site_free/site_free_leg 포함) 조회에 사용하므로 이 파일로 보존한다.
- 저장소 계약 불변: 동일 테이블 anonymous_diagnosis_results, 동일 URL(/anonymous-diagnosis/admin/*).

신청자 식별(이름·전화번호): 무료진단은 본인인증(diagnosis_auth_log) 또는 인증한 회원만 가능하므로,
anonymous_diagnosis_results.auth_log_id → diagnosis_auth_log(name, phone) 로 신청자를 구분한다.
FK 미설정이라 PostgREST embed 대신 페이지 단위 2-step fetch 로 병합한다(엔진/법령 로직 무관).
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


def _attach_applicant(supabase, items: list) -> list:
    """diagnosis_auth_log(name, phone) 를 auth_log_id 로 병합해 신청자 식별값을 부여한다.

    무료진단은 본인인증을 거치므로 실사용 레코드는 auth_log_id 를 가진다. auth_log_id 가 없는
    레코드(과거 테스트/익명 시드)는 applicant_name/applicant_phone 을 None 으로 둔다.
    페이지 단위 소량(최대 size건)만 조회하므로 목록 성능 영향은 무시할 수준이다.
    """
    ids = list({r["auth_log_id"] for r in items if r.get("auth_log_id")})
    log_map: dict = {}
    if ids:
        logs = (
            supabase.table("diagnosis_auth_log")
            .select("id,name,phone")
            .in_("id", ids)
            .execute()
            .data
        ) or []
        log_map = {row["id"]: row for row in logs}
    for r in items:
        log = log_map.get(r.get("auth_log_id")) or {}
        r["applicant_name"] = log.get("name")
        r["applicant_phone"] = log.get("phone")
    return items


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
        "id,public_token,input_data,created_at,expires_at,claimed_user_id,status,source_type,auth_log_id",
        count="exact",
    )
    if status: q = q.eq("status", status)
    kw = (keyword or "").strip()
    if kw:     q = q.ilike("public_token", f"%{kw}%")
    offset = (page - 1) * size
    res = q.order("created_at", desc=True).range(offset, offset + size - 1).execute()
    items = _attach_applicant(supabase, res.data or [])
    return {"status": "success", "data": {
        "items": items, "total": res.count, "page": page, "size": size,
        "total_pages": -(-res.count // size) if res.count else 0,
    }}


@router.get("/admin/detail/{record_id}")
def admin_get_anonymous_diagnosis_detail(record_id: str, current_user: dict = Depends(get_current_user)):
    supabase = get_supabase()
    res = supabase.table("anonymous_diagnosis_results").select("*").eq("id", record_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="레코드를 찾을 수 없습니다.")
    row = _attach_applicant(supabase, [res.data[0]])[0]
    return {"status": "success", "data": row}


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
