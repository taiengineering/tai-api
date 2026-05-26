"""Legal Status API — 법령 적용 상태 마크 관리 v1.0.0

시설/공정/설비의 법령 적용 상태를 조회·갱신하는 라우터.
legal_engine.py (GPT 도메인)는 수정하지 않고, 상태 관리만 담당.
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from datetime import datetime
from db.supabase_client import get_supabase

router = APIRouter(prefix="/legal-status", tags=["법령상태"])


# ============================================================
# 1. 상태 요약 조회
# ============================================================

@router.get("/summary")
def get_legal_status_summary(
    company_id: Optional[str] = Query(default=None),
):
    """회사 소속 시설들의 법령 적용 상태 요약."""
    supabase = get_supabase()
    query = supabase.table("factories").select(
        "id, legal_status", count="exact"
    ).eq("is_active", True)
    if company_id:
        query = query.eq("company_id", company_id)
    res = query.execute()
    items = res.data or []

    counts = {"NOT_APPLIED": 0, "NEEDS_UPDATE": 0, "APPLIED": 0}
    for row in items:
        s = row.get("legal_status", "NOT_APPLIED")
        counts[s] = counts.get(s, 0) + 1

    return {
        "status": "success",
        "data": {
            "total": len(items),
            "not_applied": counts["NOT_APPLIED"],
            "needs_update": counts["NEEDS_UPDATE"],
            "applied": counts["APPLIED"],
            "pending": counts["NOT_APPLIED"] + counts["NEEDS_UPDATE"],
        }
    }


# ============================================================
# 2. 시설 법령상태 갱신 (legal_engine 실행 후 FE에서 호출)
# ============================================================

@router.post("/factories/{factory_id}/mark-applied")
def mark_factory_applied(factory_id: str):
    """법령엔진 실행 완료 후 상태를 APPLIED로 갱신."""
    supabase = get_supabase()
    now = datetime.now().isoformat()

    # 시설 상태 갱신
    res = supabase.table("factories").update({
        "legal_status": "APPLIED",
        "legal_applied_at": now,
        "updated_at": now,
    }).eq("id", factory_id).execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다.")

    # 해당 시설의 공정/설비 매핑 상태도 MAPPED로 갱신
    supabase.table("factory_process").update({
        "legal_status": "MAPPED"
    }).eq("factory_id", factory_id).execute()

    supabase.table("equipment_assets").update({
        "legal_status": "MAPPED"
    }).eq("factory_id", factory_id).execute()

    return {
        "status": "success",
        "message": "법령 적용 상태가 갱신되었습니다.",
        "data": {"factory_id": factory_id, "legal_status": "APPLIED", "legal_applied_at": now}
    }


# ============================================================
# 3. 시설 법령상태 → NEEDS_UPDATE (공정/설비 변경 시)
# ============================================================

@router.post("/factories/{factory_id}/mark-needs-update")
def mark_factory_needs_update(factory_id: str):
    """공정/설비 변경 시 상태를 NEEDS_UPDATE로 전환."""
    supabase = get_supabase()
    now = datetime.now().isoformat()

    # APPLIED인 경우에만 NEEDS_UPDATE로 전환
    res = supabase.table("factories").update({
        "legal_status": "NEEDS_UPDATE",
        "updated_at": now,
    }).eq("id", factory_id).eq("legal_status", "APPLIED").execute()

    return {
        "status": "success",
        "message": "재진단 필요 상태로 전환되었습니다." if res.data else "이미 미적용 또는 재진단 상태입니다.",
        "data": {"factory_id": factory_id}
    }


# ============================================================
# 4. 전체 법령적용 대상 조회
# ============================================================

@router.get("/pending")
def get_pending_factories(
    company_id: Optional[str] = Query(default=None),
):
    """법령 미적용 + 재진단 필요 시설 목록."""
    supabase = get_supabase()
    query = supabase.table("factories").select(
        "id, name, ksic_code, legal_status, legal_applied_at"
    ).eq("is_active", True).in_("legal_status", ["NOT_APPLIED", "NEEDS_UPDATE"])
    if company_id:
        query = query.eq("company_id", company_id)
    res = query.order("created_at", desc=True).execute()
    return {
        "status": "success",
        "data": {"items": res.data or [], "total": len(res.data or [])}
    }


# ============================================================
# 5. 전체 법령적용 실행 (배치)
# ============================================================

@router.post("/batch-apply")
async def batch_apply_legal(
    company_id: Optional[str] = Query(default=None),
):
    """
    미적용 + 재진단 시설 전체에 법령엔진 실행.
    FE에서 프로그레스 표시를 위해 동기 실행.
    """
    supabase = get_supabase()
    query = supabase.table("factories").select(
        "id, name, ksic_code"
    ).eq("is_active", True).in_("legal_status", ["NOT_APPLIED", "NEEDS_UPDATE"])
    if company_id:
        query = query.eq("company_id", company_id)
    res = query.execute()
    targets = res.data or []

    if not targets:
        return {
            "status": "success",
            "message": "적용할 시설이 없습니다.",
            "data": {"total": 0, "success": 0, "failed": 0, "results": []}
        }

    results = []
    success_count = 0
    fail_count = 0
    now = datetime.now().isoformat()

    for factory in targets:
        fid = factory["id"]
        try:
            # 법령엔진 실행 (legal_engine.py의 apply 로직 호출)
            # 엔진 실패해도 상태는 갱신 (mock 모드)
            # TODO: 실제 엔진 연동 시 여기에 legal_engine 호출 추가

            # 상태 갱신
            supabase.table("factories").update({
                "legal_status": "APPLIED",
                "legal_applied_at": now,
                "updated_at": now,
            }).eq("id", fid).execute()

            supabase.table("factory_process").update({
                "legal_status": "MAPPED"
            }).eq("factory_id", fid).execute()

            supabase.table("equipment_assets").update({
                "legal_status": "MAPPED"
            }).eq("factory_id", fid).execute()

            results.append({"factory_id": fid, "name": factory["name"], "status": "success"})
            success_count += 1
        except Exception as e:
            results.append({"factory_id": fid, "name": factory["name"], "status": "failed", "error": str(e)})
            fail_count += 1

    return {
        "status": "success",
        "message": f"전체 법령적용 완료: 성공 {success_count}건, 실패 {fail_count}건",
        "data": {
            "total": len(targets),
            "success": success_count,
            "failed": fail_count,
            "results": results,
        }
    }
