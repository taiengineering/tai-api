"""
TAI Fix 공급자 서비스 가격 관리 라우터 — v1.0.0
prefix: /connect/provider

엔드포인트:
  GET  /connect/provider/profile              내 공급자 프로필 조회/자동생성
  GET  /connect/services                      서비스 목록 (대분류 필터)
  GET  /connect/provider/services             내 서비스 가격 목록
  POST /connect/provider/services/upsert      서비스 가격 등록/수정 (단건)
  POST /connect/provider/services/batch       서비스 가격 일괄 저장
  DELETE /connect/provider/services/{id}      서비스 가격 삭제
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional, List
from datetime import datetime, timezone
from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services.time import now_kst, serialize_external_utc

router = APIRouter(tags=["TAI Fix 공급자"])

def _now_iso() -> str:
    return serialize_external_utc(now_kst())


# ─────────────────────────────────────────────────────
# 공급자 프로필 조회/자동생성
# ─────────────────────────────────────────────────────
@router.get("/connect/provider/profile")
async def get_provider_profile(current_user: dict = Depends(get_current_user)):
    supabase = get_supabase()
    user_id = current_user.get("id")
    try:
        res = supabase.table("connect_providers").select("*").eq("user_id", user_id).limit(1).execute()
        if res.data:
            return {"status": "success", "data": res.data[0]}
        # 없으면 자동 생성 (최소 프로필)
        now = _now_iso()
        insert = {
            "user_id":      user_id,
            "company_name": current_user.get("name", "") + " 업체",
            "status":       "PENDING",
            "created_at":   now,
            "updated_at":   now,
        }
        ins_res = supabase.table("connect_providers").insert(insert).execute()
        return {"status": "success", "data": ins_res.data[0] if ins_res.data else insert}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# 서비스 마스터 목록 (대분류 필터, 인증 불필요)
# ─────────────────────────────────────────────────────
@router.get("/connect/services")
async def list_connect_services(
    category: Optional[str] = Query(None, description="대분류 (소방/전기/기계설비 등)"),
    keyword:  Optional[str] = Query(None, description="검색어"),
):
    supabase = get_supabase()
    try:
        query = supabase.table("connect_service_master").select(
            "id, service_name, category, sectors, license_required, license_detail, "
            "is_legal_duty, demand_frequency, price_min, price_max, price_unit, keywords"
        ).order("category").order("service_name")
        if category:
            query = query.eq("category", category)
        if keyword:
            query = query.or_(f"service_name.ilike.%{keyword}%,keywords.cs.{{{keyword}}}")
        res = query.execute()
        # 대분류별 그룹핑
        grouped: dict = {}
        for row in (res.data or []):
            cat = row["category"]
            grouped.setdefault(cat, [])
            grouped[cat].append(row)
        categories = list(grouped.keys())
        return {"status": "success", "data": {
            "categories": categories,
            "services": grouped,
            "total": len(res.data or []),
        }}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# 내 서비스 가격 목록
# ─────────────────────────────────────────────────────
@router.get("/connect/provider/services")
async def get_my_provider_services(
    category: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user)
):
    supabase = get_supabase()
    user_id = current_user.get("id")
    try:
        # 내 공급자 ID 조회
        prov_res = supabase.table("connect_providers").select("id").eq("user_id", user_id).limit(1).execute()
        if not prov_res.data:
            return {"status": "success", "data": []}
        provider_id = prov_res.data[0]["id"]

        # 내 서비스 가격 목록 (서비스마스터 JOIN)
        query = supabase.table("connect_provider_services").select(
            "id, service_id, price_min, price_max, price_unit, note, is_available, updated_at, "
            "connect_service_master(id, service_name, category, price_unit)"
        ).eq("provider_id", provider_id)
        res = query.execute()
        items = []
        for row in (res.data or []):
            svc = row.get("connect_service_master") or {}
            if category and svc.get("category") != category:
                continue
            items.append({
                "id":           row["id"],
                "service_id":   row["service_id"],
                "service_name": svc.get("service_name", ""),
                "category":     svc.get("category", ""),
                "price_min":    row.get("price_min"),
                "price_max":    row.get("price_max"),
                "price_unit":   row.get("price_unit") or svc.get("price_unit", ""),
                "note":         row.get("note", ""),
                "is_available": row.get("is_available", True),
                "updated_at":   row.get("updated_at"),
            })
        return {"status": "success", "data": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# 서비스 가격 단건 등록/수정 (upsert)
# ─────────────────────────────────────────────────────
@router.post("/connect/provider/services/upsert")
async def upsert_provider_service(
    body: dict,
    current_user: dict = Depends(get_current_user)
):
    supabase = get_supabase()
    user_id = current_user.get("id")
    try:
        service_id = body.get("service_id")
        if not service_id:
            raise HTTPException(status_code=400, detail="service_id는 필수입니다.")

        # 공급자 프로필 조회 (없으면 자동생성)
        prov_res = supabase.table("connect_providers").select("id").eq("user_id", user_id).limit(1).execute()
        if prov_res.data:
            provider_id = prov_res.data[0]["id"]
        else:
            now = _now_iso()
            ins = supabase.table("connect_providers").insert({
                "user_id":      user_id,
                "company_name": current_user.get("name", "") + " 업체",
                "status":       "PENDING",
                "created_at":   now,
                "updated_at":   now,
            }).execute()
            provider_id = ins.data[0]["id"]

        now = _now_iso()
        upsert_data = {
            "provider_id":  provider_id,
            "service_id":   int(service_id),
            "price_min":    body.get("price_min"),
            "price_max":    body.get("price_max"),
            "price_unit":   body.get("price_unit"),
            "note":         body.get("note", ""),
            "is_available": body.get("is_available", True),
            "updated_at":   now,
        }
        # 기존 레코드 확인
        exist = supabase.table("connect_provider_services").select("id").eq(
            "provider_id", provider_id).eq("service_id", int(service_id)).limit(1).execute()
        if exist.data:
            res = supabase.table("connect_provider_services").update(upsert_data).eq(
                "id", exist.data[0]["id"]).execute()
        else:
            upsert_data["created_at"] = now
            res = supabase.table("connect_provider_services").insert(upsert_data).execute()

        return {"status": "success", "message": "저장됐습니다.", "data": res.data[0] if res.data else {}}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# 서비스 가격 일괄 저장
# ─────────────────────────────────────────────────────
@router.post("/connect/provider/services/batch")
async def batch_upsert_provider_services(
    body: dict,
    current_user: dict = Depends(get_current_user)
):
    supabase = get_supabase()
    user_id = current_user.get("id")
    try:
        items = body.get("items", [])
        if not items:
            raise HTTPException(status_code=400, detail="items가 비어 있습니다.")

        # 공급자 프로필 조회/생성
        prov_res = supabase.table("connect_providers").select("id").eq("user_id", user_id).limit(1).execute()
        if prov_res.data:
            provider_id = prov_res.data[0]["id"]
        else:
            now = _now_iso()
            ins = supabase.table("connect_providers").insert({
                "user_id":      user_id,
                "company_name": current_user.get("name", "") + " 업체",
                "status":       "PENDING",
                "created_at":   now, "updated_at": now,
            }).execute()
            provider_id = ins.data[0]["id"]

        now = _now_iso()
        saved = []
        for item in items:
            service_id = item.get("service_id")
            if not service_id:
                continue
            upsert_data = {
                "provider_id":  provider_id,
                "service_id":   int(service_id),
                "price_min":    item.get("price_min"),
                "price_max":    item.get("price_max"),
                "price_unit":   item.get("price_unit"),
                "note":         item.get("note", ""),
                "is_available": item.get("is_available", True),
                "updated_at":   now,
            }
            exist = supabase.table("connect_provider_services").select("id").eq(
                "provider_id", provider_id).eq("service_id", int(service_id)).limit(1).execute()
            if exist.data:
                res = supabase.table("connect_provider_services").update(upsert_data).eq(
                    "id", exist.data[0]["id"]).execute()
            else:
                upsert_data["created_at"] = now
                res = supabase.table("connect_provider_services").insert(upsert_data).execute()
            if res.data:
                saved.append(res.data[0])

        return {"status": "success", "message": f"{len(saved)}개 저장됐습니다.", "data": saved}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# 서비스 가격 삭제
# ─────────────────────────────────────────────────────
@router.delete("/connect/provider/services/{record_id}")
async def delete_provider_service(
    record_id: str,
    current_user: dict = Depends(get_current_user)
):
    supabase = get_supabase()
    user_id = current_user.get("id")
    try:
        prov_res = supabase.table("connect_providers").select("id").eq("user_id", user_id).limit(1).execute()
        if not prov_res.data:
            raise HTTPException(status_code=404, detail="공급자 프로필이 없습니다.")
        provider_id = prov_res.data[0]["id"]
        res = supabase.table("connect_provider_services").delete().eq(
            "id", record_id).eq("provider_id", provider_id).execute()
        return {"status": "success", "message": "삭제됐습니다."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
