# routers/equipment_assets.py  v1.1.0
# 설비관리 API — 6개 엔드포인트
# is_active 컬럼 없음 → DELETE 실제 삭제

from datetime import datetime, timezone, date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from db.supabase_client import get_supabase

router = APIRouter(prefix="/equipment-assets", tags=["equipment_assets"])

VERSION = "1.1.0"

# ── 허용 수정 필드 ─────────────────────────────────────────
PATCH_ALLOWED = {
    "asset_name", "asset_code", "equipment_type_code", "equipment_category",
    "capacity_value", "capacity_unit", "quantity",
    "install_year", "manufacture_year", "manufacturer",
    "is_operating", "is_legal_target",
    "last_inspection_date", "next_inspection_date",
    "description", "location_detail", "floor_no",
    "ksic_code", "area_id", "building_id",
}


# ────────────────────────────────────────────────────────────
# 1. GET /equipment-assets  — 설비 목록 (페이지네이션 + 필터)
# ────────────────────────────────────────────────────────────
@router.get("")
def list_assets(
    factory_id: Optional[str] = None,
    equipment_type_code: Optional[str] = None,
    is_legal_target: Optional[bool] = None,
    is_operating: Optional[bool] = None,
    search: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    supabase = get_supabase()
    try:
        query = supabase.table("equipment_assets").select(
            "*, factories!inner(id, name, company_id, companies(id, name))"
        )

        if factory_id:
            query = query.eq("factory_id", factory_id)
        if equipment_type_code:
            query = query.eq("equipment_type_code", equipment_type_code)
        if is_legal_target is not None:
            query = query.eq("is_legal_target", is_legal_target)
        if is_operating is not None:
            query = query.eq("is_operating", is_operating)
        if search:
            query = query.or_(
                f"asset_name.ilike.%{search}%,asset_code.ilike.%{search}%"
            )

        res = query.order("created_at", desc=True).execute()
        rows = res.data or []

        total = len(rows)
        start = (page - 1) * page_size
        paged = rows[start: start + page_size]

        items = []
        for row in paged:
            f = row.pop("factories", {}) or {}
            c = f.pop("companies", {}) or {}
            row["factory_name"] = f.get("name")
            row["company_name"] = c.get("name")
            items.append(row)

        return {
            "status": "success",
            "data": {
                "items": items,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size if total else 0,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ────────────────────────────────────────────────────────────
# 6. GET /equipment-assets/overview  — 시설별 설비 현황 집계
#    ※ /{asset_id} 보다 먼저 등록해야 라우팅 충돌 없음
# ────────────────────────────────────────────────────────────
@router.get("/overview")
def get_assets_overview(
    search: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    supabase = get_supabase()
    try:
        # 전체 설비 가져오기
        eq_res = supabase.table("equipment_assets").select(
            "factory_id, is_legal_target, is_operating, next_inspection_date"
        ).execute()
        assets = eq_res.data or []

        # 시설 목록 + 회사명
        fac_res = supabase.table("factories").select(
            "id, name, companies(id, name)"
        ).eq("is_active", True).execute()
        factories = fac_res.data or []

        today = date.today().isoformat()

        # 시설별 집계
        agg: dict = {}
        for a in assets:
            fid = a.get("factory_id")
            if not fid:
                continue
            if fid not in agg:
                agg[fid] = {
                    "total_count": 0,
                    "legal_target_count": 0,
                    "operating_count": 0,
                    "overdue_inspection_count": 0,
                }
            agg[fid]["total_count"] += 1
            if a.get("is_legal_target"):
                agg[fid]["legal_target_count"] += 1
            if a.get("is_operating"):
                agg[fid]["operating_count"] += 1
            nid = a.get("next_inspection_date")
            if nid and str(nid) < today:
                agg[fid]["overdue_inspection_count"] += 1

        items = []
        for f in factories:
            fid = str(f.get("id"))
            c = f.get("companies") or {}
            factory_name = f.get("name", "")
            company_name = c.get("name", "") if isinstance(c, dict) else ""

            if search:
                s = search.lower()
                if s not in factory_name.lower() and s not in company_name.lower():
                    continue

            stats = agg.get(fid, {
                "total_count": 0,
                "legal_target_count": 0,
                "operating_count": 0,
                "overdue_inspection_count": 0,
            })

            items.append({
                "factory_id": fid,
                "factory_name": factory_name,
                "company_name": company_name,
                **stats,
            })

        # 설비 많은 순 정렬
        items.sort(key=lambda x: x["total_count"], reverse=True)

        total = len(items)
        start = (page - 1) * page_size
        paged = items[start: start + page_size]

        return {
            "status": "success",
            "data": {
                "items": paged,
                "total": total,
                "page": page,
                "page_size": page_size,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ────────────────────────────────────────────────────────────
# 2. GET /equipment-assets/{asset_id}  — 설비 단건 상세
# ────────────────────────────────────────────────────────────
@router.get("/{asset_id}")
def get_asset(asset_id: str):
    supabase = get_supabase()
    try:
        res = supabase.table("equipment_assets").select(
            "*, factories!inner(id, name, companies(id, name))"
        ).eq("id", asset_id).limit(1).execute()

        rows = res.data or []
        if not rows:
            raise HTTPException(status_code=404, detail="설비를 찾을 수 없습니다.")

        row = rows[0]
        f = row.pop("factories", {}) or {}
        c = f.pop("companies", {}) or {}
        row["factory_name"] = f.get("name")
        row["company_name"] = c.get("name")

        return {"status": "success", "data": row}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ────────────────────────────────────────────────────────────
# 3. POST /equipment-assets  — 설비 등록
# ────────────────────────────────────────────────────────────
@router.post("")
def create_asset(body: dict):
    supabase = get_supabase()
    try:
        if not body.get("factory_id"):
            raise HTTPException(status_code=400, detail="factory_id는 필수입니다.")
        if not body.get("asset_name", "").strip():
            raise HTTPException(status_code=400, detail="asset_name은 필수입니다.")

        now = datetime.now(timezone.utc).isoformat()
        insert_data = {k: v for k, v in body.items() if v is not None}
        insert_data["created_at"] = now
        insert_data["updated_at"] = now

        # id 자동생성 (uuid)
        insert_data.pop("id", None)

        res = supabase.table("equipment_assets").insert(insert_data).execute()

        if not res.data:
            raise HTTPException(status_code=500, detail="설비 등록에 실패했습니다.")

        return {
            "status": "success",
            "message": "설비가 등록됐습니다.",
            "data": res.data[0],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ────────────────────────────────────────────────────────────
# 4. PATCH /equipment-assets/{asset_id}  — 설비 수정
# ────────────────────────────────────────────────────────────
@router.patch("/{asset_id}")
def update_asset(asset_id: str, body: dict):
    supabase = get_supabase()
    try:
        update_data = {k: v for k, v in body.items() if k in PATCH_ALLOWED}
        if not update_data:
            raise HTTPException(status_code=400, detail="수정할 필드가 없습니다.")

        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        res = supabase.table("equipment_assets").update(update_data).eq(
            "id", asset_id
        ).execute()

        if not res.data:
            raise HTTPException(status_code=404, detail="설비를 찾을 수 없습니다.")

        return {
            "status": "success",
            "message": "설비가 수정됐습니다.",
            "data": res.data[0],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ────────────────────────────────────────────────────────────
# 5. DELETE /equipment-assets/{asset_id}  — 설비 삭제 (실제 삭제)
#    is_active 컬럼 없음 → hard delete
# ────────────────────────────────────────────────────────────
@router.delete("/{asset_id}")
def delete_asset(asset_id: str):
    supabase = get_supabase()
    try:
        res = supabase.table("equipment_assets").delete().eq(
            "id", asset_id
        ).execute()

        if not res.data:
            raise HTTPException(status_code=404, detail="설비를 찾을 수 없습니다.")

        return {
            "status": "success",
            "message": f"설비 {asset_id} 삭제 완료",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
