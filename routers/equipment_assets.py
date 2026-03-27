# routers/equipment_assets.py  v1.2.0
# 설비관리 API + 문제5: 모델 점검주기 자동반영 엔드포인트 추가

from datetime import datetime, timezone, date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from db.supabase_client import get_supabase

router = APIRouter(prefix="/equipment-assets", tags=["equipment_assets"])

VERSION = "1.2.0"

PATCH_ALLOWED = {
    "asset_name", "asset_code", "equipment_type_code", "equipment_category",
    "capacity_value", "capacity_unit", "quantity",
    "install_year", "manufacture_year", "manufacturer",
    "is_operating", "is_legal_target",
    "last_inspection_date", "next_inspection_date",
    "description", "location_detail", "floor_no",
    "ksic_code", "area_id", "building_id",
}


def _calc_next_date(base_date_str: str, cycle_months: int) -> str:
    """base_date에서 cycle_months 개월 후 날짜 계산"""
    base = date.fromisoformat(str(base_date_str))
    month = base.month - 1 + cycle_months
    year  = base.year + month // 12
    month = month % 12 + 1
    day   = min(base.day, 28)
    return date(year, month, day).isoformat()


# ────────────────────────────────────────────────────────────
# 1. GET /equipment-assets  — 목록
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
        if factory_id:           query = query.eq("factory_id", factory_id)
        if equipment_type_code:  query = query.eq("equipment_type_code", equipment_type_code)
        if is_legal_target is not None: query = query.eq("is_legal_target", is_legal_target)
        if is_operating is not None:    query = query.eq("is_operating", is_operating)
        if search:
            query = query.or_(f"asset_name.ilike.%{search}%,asset_code.ilike.%{search}%")

        res = query.order("created_at", desc=True).execute()
        rows = res.data or []
        total = len(rows)
        paged = rows[(page-1)*page_size: page*page_size]

        items = []
        for row in paged:
            f = row.pop("factories", {}) or {}
            c = f.pop("companies", {}) or {}
            row["factory_name"] = f.get("name")
            row["company_name"] = c.get("name")
            items.append(row)

        return {"status": "success", "data": {
            "items": items, "total": total, "page": page, "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total else 0,
        }}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ────────────────────────────────────────────────────────────
# overview — /{asset_id} 보다 먼저 선언
# ────────────────────────────────────────────────────────────
@router.get("/overview")
def get_assets_overview(
    search: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    supabase = get_supabase()
    try:
        eq_res  = supabase.table("equipment_assets").select(
            "factory_id, is_legal_target, is_operating, next_inspection_date"
        ).execute()
        fac_res = supabase.table("factories").select(
            "id, name, companies(id, name)"
        ).eq("is_active", True).execute()

        today = date.today().isoformat()
        agg: dict = {}
        for a in (eq_res.data or []):
            fid = a.get("factory_id")
            if not fid: continue
            if fid not in agg:
                agg[fid] = {"total_count": 0, "legal_target_count": 0, "operating_count": 0, "overdue_inspection_count": 0}
            agg[fid]["total_count"] += 1
            if a.get("is_legal_target"): agg[fid]["legal_target_count"] += 1
            if a.get("is_operating"):    agg[fid]["operating_count"] += 1
            nid = a.get("next_inspection_date")
            if nid and str(nid) < today: agg[fid]["overdue_inspection_count"] += 1

        items = []
        for f in (fac_res.data or []):
            fid          = str(f.get("id"))
            c            = f.get("companies") or {}
            factory_name = f.get("name", "")
            company_name = c.get("name", "") if isinstance(c, dict) else ""
            if search:
                s = search.lower()
                if s not in factory_name.lower() and s not in company_name.lower(): continue
            stats = agg.get(fid, {"total_count": 0, "legal_target_count": 0, "operating_count": 0, "overdue_inspection_count": 0})
            items.append({"factory_id": fid, "factory_name": factory_name, "company_name": company_name, **stats})

        items.sort(key=lambda x: x["total_count"], reverse=True)
        total = len(items)
        paged = items[(page-1)*page_size: page*page_size]
        return {"status": "success", "data": {"items": paged, "total": total, "page": page, "page_size": page_size}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ────────────────────────────────────────────────────────────
# 문제5 신규: 모델 점검주기 자동반영
# /factory/{factory_id}/... 는 /{asset_id} 보다 먼저 선언
# ────────────────────────────────────────────────────────────
@router.post("/factory/{factory_id}/apply-all-model-cycles")
async def apply_all_model_cycles(factory_id: str):
    """시설 내 모든 설비의 모델 점검주기 일괄 반영 (v1.2.0)"""
    supabase = get_supabase()

    assets = supabase.table("equipment_assets").select(
        "id, equipment_model_id, last_inspection_date"
    ).eq("factory_id", factory_id).execute()

    updated, skipped = 0, 0
    for asset in (assets.data or []):
        model_id = asset.get("equipment_model_id")
        if not model_id:
            skipped += 1
            continue
        try:
            model = supabase.table("equipment_model_master").select(
                "maintenance_cycle_months"
            ).eq("id", model_id).limit(1).execute()
            if not model.data:
                skipped += 1
                continue

            cycle_months = model.data[0].get("maintenance_cycle_months") or 12
            base_date    = asset.get("last_inspection_date") or date.today().isoformat()
            next_date    = _calc_next_date(str(base_date), cycle_months)

            supabase.table("equipment_assets").update({
                "next_inspection_date": next_date,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", asset["id"]).execute()
            updated += 1
        except Exception:
            skipped += 1

    return {
        "status": "success",
        "message": f"{updated}개 설비 점검일 갱신, {skipped}개 건너뜀",
        "data": {"factory_id": factory_id, "updated": updated, "skipped": skipped}
    }


# ────────────────────────────────────────────────────────────
# 2. GET /{asset_id}  — 단건 상세
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
# 3. POST  — 등록
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
        insert_data.update({"created_at": now, "updated_at": now})
        insert_data.pop("id", None)
        res = supabase.table("equipment_assets").insert(insert_data).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="설비 등록에 실패했습니다.")
        return {"status": "success", "message": "설비가 등록됐습니다.", "data": res.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ────────────────────────────────────────────────────────────
# 4. PATCH /{asset_id}  — 수정
# ────────────────────────────────────────────────────────────
@router.patch("/{asset_id}")
def update_asset(asset_id: str, body: dict):
    supabase = get_supabase()
    try:
        update_data = {k: v for k, v in body.items() if k in PATCH_ALLOWED}
        if not update_data:
            raise HTTPException(status_code=400, detail="수정할 필드가 없습니다.")
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        res = supabase.table("equipment_assets").update(update_data).eq("id", asset_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="설비를 찾을 수 없습니다.")
        return {"status": "success", "message": "설비가 수정됐습니다.", "data": res.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ────────────────────────────────────────────────────────────
# 5. DELETE /{asset_id}  — 삭제
# ────────────────────────────────────────────────────────────
@router.delete("/{asset_id}")
def delete_asset(asset_id: str):
    supabase = get_supabase()
    try:
        res = supabase.table("equipment_assets").delete().eq("id", asset_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="설비를 찾을 수 없습니다.")
        return {"status": "success", "message": f"설비 {asset_id} 삭제 완료"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ────────────────────────────────────────────────────────────
# 문제5: 단건 모델 점검주기 반영
# ────────────────────────────────────────────────────────────
@router.post("/{asset_id}/apply-model-cycle")
async def apply_model_cycle_to_asset(asset_id: str):
    """단일 설비의 모델 점검주기 → next_inspection_date 자동계산"""
    supabase = get_supabase()
    asset = supabase.table("equipment_assets").select(
        "id, equipment_model_id, last_inspection_date, next_inspection_date"
    ).eq("id", asset_id).limit(1).execute()

    rows = asset.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="설비를 찾을 수 없습니다.")
    a = rows[0]

    model_id = a.get("equipment_model_id")
    if not model_id:
        raise HTTPException(status_code=400, detail="모델이 연결되어 있지 않습니다.")

    model = supabase.table("equipment_model_master").select(
        "maintenance_cycle_months"
    ).eq("id", model_id).limit(1).execute()
    if not model.data:
        raise HTTPException(status_code=404, detail="모델을 찾을 수 없습니다.")

    cycle_months = model.data[0].get("maintenance_cycle_months") or 12
    base_date    = a.get("last_inspection_date") or date.today().isoformat()
    next_date    = _calc_next_date(str(base_date), cycle_months)

    supabase.table("equipment_assets").update({
        "next_inspection_date": next_date,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", asset_id).execute()

    return {
        "status": "success",
        "message": f"다음 점검일이 {next_date}으로 설정됐습니다.",
        "data": {
            "asset_id":             asset_id,
            "cycle_months":         cycle_months,
            "base_date":            str(base_date),
            "next_inspection_date": next_date,
        }
    }
