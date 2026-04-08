from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime, timezone
from db.supabase_client import get_supabase

router = APIRouter(prefix="/equipment-assets", tags=["equipment_assets"])

VERSION = "1.4.0"
"""
equipment_assets.py v1.4.0
v1.4.0: /model/search 개선
  - equipment_model_master + v_equipment_unified.facility_name_std 동시 검색
  - 지게차처럼 마스터에 없고 unified뷰에만 있는 설비명도 검색 가능
v1.3.0: 설비 마스터 검색 엔드포인트 추가
v1.2.0: QR/RFID 체크인 관련 엔드포인트 추가
v1.1.0: POST 실행 시 INSTALL 이벤트 트리거 추가

⚠ 라우팅 순서:
  /scan            (고정경로) → 먼저 선언
  /model/search    (고정경로)
  /area/{area_id}  (고정경로)
  /{asset_id}      (파라미터) → 마지막에 선언
"""


# ── 모델 ─────────────────────────────────
class EquipmentAssetCreate(BaseModel):
    factory_id:           str
    asset_name:           str
    equipment_type_code:  Optional[str] = None
    equipment_category:   Optional[str] = None
    asset_code:           Optional[str] = None
    description:          Optional[str] = None
    quantity:             Optional[int] = 1
    capacity_value:       Optional[float] = None
    capacity_unit:        Optional[str] = None
    manufacturer:         Optional[str] = None
    install_year:         Optional[int] = None
    manufacture_year:     Optional[int] = None
    location_detail:      Optional[str] = None
    is_legal_target:      Optional[bool] = True
    is_operating:         Optional[bool] = True
    equipment_model_id:   Optional[str] = None
    area_id:              Optional[str] = None
    ksic_code:            Optional[str] = None


class EquipmentAssetUpdate(BaseModel):
    asset_name:           Optional[str] = None
    equipment_type_code:  Optional[str] = None
    equipment_category:   Optional[str] = None
    asset_code:           Optional[str] = None
    description:          Optional[str] = None
    quantity:             Optional[int] = None
    capacity_value:       Optional[float] = None
    capacity_unit:        Optional[str] = None
    manufacturer:         Optional[str] = None
    install_year:         Optional[int] = None
    location_detail:      Optional[str] = None
    is_legal_target:      Optional[bool] = None
    is_operating:         Optional[bool] = None
    equipment_model_id:   Optional[str] = None
    last_inspection_date: Optional[str] = None
    next_inspection_date: Optional[str] = None


# ── 목록 조회 ────────────────────────────────
@router.get("")
def get_assets(
    factory_id:           Optional[str] = Query(None),
    area_id:              Optional[str] = Query(None),
    equipment_type_code:  Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    supabase = get_supabase()
    query = supabase.table("equipment_assets").select(
        "id, factory_id, area_id, asset_name, asset_code, "
        "equipment_type_code, equipment_category, "
        "quantity, capacity_value, capacity_unit, "
        "install_year, manufacturer, equipment_model_id, "
        "last_inspection_date, next_inspection_date, "
        "is_legal_target, is_operating, description, "
        "location_detail, created_at",
        count="exact"
    )
    if factory_id:
        query = query.eq("factory_id", factory_id)
    if area_id:
        query = query.eq("area_id", area_id)
    if equipment_type_code:
        query = query.eq("equipment_type_code", equipment_type_code)
    offset = (page - 1) * size
    res = query.order("created_at", desc=True).range(offset, offset + size - 1).execute()
    return {
        "status": "success",
        "data": {
            "items": res.data,
            "total": res.count or 0,
            "page":  page,
            "size":  size,
        }
    }


# ── v1.2.0: QR/RFID 스캔 조회 (인증 불필요) ─────────────────
@router.get("/scan")
def scan_equipment(
    id:   Optional[str] = Query(None, description="equipment_asset_id"),
    rfid: Optional[str] = Query(None, description="RFID 태그 ID"),
):
    supabase = get_supabase()
    if not id and not rfid:
        raise HTTPException(status_code=422, detail="id 또는 rfid 파라미터가 필요합니다")

    q = supabase.table("equipment_assets").select(
        "id, asset_name, asset_code, equipment_type_code, equipment_category, "
        "main_image_url, description, factory_id, factory_process_id, "
        "rfid_tag, rfid_tag_type, location_detail, qr_code"
    )
    if id:
        q = q.eq("id", id)
    else:
        q = q.eq("rfid_tag", rfid)

    asset_res = q.limit(1).execute()
    if not asset_res.data:
        raise HTTPException(status_code=404, detail="등록된 설비를 찾을 수 없습니다")

    asset      = asset_res.data[0]
    factory_id = asset.get("factory_id")
    factory_info = {}
    company_info = {}
    company_id   = None
    if factory_id:
        fac = supabase.table("factories").select("id, name, company_id").eq("id", factory_id).limit(1).execute()
        if fac.data:
            factory_info = {"id": fac.data[0]["id"], "name": fac.data[0]["name"]}
            company_id   = fac.data[0].get("company_id")
            if company_id:
                comp = supabase.table("companies").select("id, name").eq("id", company_id).limit(1).execute()
                if comp.data:
                    company_info = {"id": comp.data[0]["id"], "name": comp.data[0]["name"]}

    process_info       = {}
    factory_process_id = asset.get("factory_process_id")
    if factory_process_id:
        proc = supabase.table("factory_process").select(
            "id, process_path, process_name_manual, process_lv1, process_lv2, process_lv3"
        ).eq("id", factory_process_id).limit(1).execute()
        if proc.data:
            process_info = proc.data[0]

    today = date.today().isoformat()
    pending_schedules = []
    if factory_id:
        sched = supabase.table("work_schedules").select(
            "id, description, planned_date, status_code, law_name, law_article"
        ).eq("factory_id", factory_id).eq("planned_date", today).neq("status_code", "DONE").limit(10).execute()
        pending_schedules = sched.data or []

    return {
        "status": "success",
        "data": {
            "equipment":         asset,
            "factory":           factory_info,
            "company":           company_info,
            "process":           process_info,
            "pending_schedules": pending_schedules,
            "scan_method":       "RFID" if rfid else "QR",
        }
    }


# ── v1.4.0: 설비 마스터 검색 ────────────────────────────────
# equipment_model_master + v_equipment_unified 동시 검색
@router.get("/model/search")
def search_equipment_model(
    q:    str            = Query(..., description="설비명 검색어 (ILIKE)"),
    lv2:  Optional[str] = Query(None, description="카테고리 필터"),
    size: int            = Query(20, ge=1, le=100),
):
    """
    v1.4.0: equipment_model_master + v_equipment_unified 동시 검색.
    두 소스에서 결과를 합쳐 중복 제거 후 반환.
    지게차처럼 마스터에 없고 unified뷰에만 있는 설비도 정상 검색.
    """
    supabase = get_supabase()
    seen: set = set()
    unique: list = []

    # 1. equipment_model_master 검색
    mq = supabase.table("equipment_model_master").select(
        "id, equipment_std, equipment_lv2, certification_class, maintenance_cycle_months, risk_score"
    ).ilike("equipment_std", f"%{q.strip()}%")
    if lv2:
        mq = mq.eq("equipment_lv2", lv2)
    master_res = mq.order("equipment_std").limit(size).execute()
    for row in (master_res.data or []):
        name = row["equipment_std"]
        if name and name not in seen:
            seen.add(name)
            unique.append({
                "id":           row["id"],
                "name":         name,
                "category":     row.get("equipment_lv2") or "기타",
                "cert_class":   row.get("certification_class"),
                "cycle_months": row.get("maintenance_cycle_months"),
                "risk_score":   row.get("risk_score"),
                "source":       "master",
            })

    # 2. v_equipment_unified 검색 (마스터에 없는 설비명 보완)
    if len(unique) < size:
        remain = size - len(unique)
        uq = supabase.table("v_equipment_unified").select(
            "facility_name_std, source_type"
        ).ilike("facility_name_std", f"%{q.strip()}%").order("facility_name_std").limit(remain * 3).execute()
        for row in (uq.data or []):
            name = row.get("facility_name_std", "")
            if name and name not in seen:
                seen.add(name)
                unique.append({
                    "id":           None,  # 마스터 ID 없음
                    "name":         name,
                    "category":     row.get("source_type") or "기타",
                    "cert_class":   None,
                    "cycle_months": None,
                    "risk_score":   None,
                    "source":       "unified",
                })

    # size 제한
    unique = unique[:size]
    unique.sort(key=lambda x: x["name"])

    return {
        "status": "success",
        "data": {"q": q, "items": unique, "total": len(unique)}
    }


# ── area별 조회 ──────────────────────────────────────────────
@router.get("/area/{area_id}")
def get_area_assets(area_id: str):
    supabase = get_supabase()
    result = supabase.table("equipment_assets").select("*").eq("area_id", area_id).execute()
    return {"status": "success", "data": result.data}


# ── 단건 조회 ────────────────────────────────────────────────
@router.get("/{asset_id}")
def get_asset(asset_id: str):
    supabase = get_supabase()
    result = supabase.table("equipment_assets").select("*").eq("id", asset_id).limit(1).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="설비를 찾을 수 없습니다")
    return {"status": "success", "data": result.data[0]}


# ── 설비 등록 ────────────────────────────────────────────────
@router.post("")
async def create_asset(body: EquipmentAssetCreate):
    supabase = get_supabase()
    if not body.asset_name.strip():
        raise HTTPException(status_code=422, detail="asset_name은 필수입니다.")

    fac = supabase.table("factories").select("company_id").eq("id", body.factory_id).limit(1).execute()
    company_id = (fac.data[0] if fac.data else {}).get("company_id")

    insert_data = {
        "factory_id":          body.factory_id,
        "asset_name":          body.asset_name.strip(),
        "asset_code":          body.asset_code,
        "equipment_type_code": body.equipment_type_code,
        "equipment_category":  body.equipment_category,
        "description":         body.description,
        "quantity":            body.quantity or 1,
        "capacity_value":      body.capacity_value,
        "capacity_unit":       body.capacity_unit,
        "manufacturer":        body.manufacturer,
        "install_year":        body.install_year,
        "manufacture_year":    body.manufacture_year,
        "location_detail":     body.location_detail,
        "is_legal_target":     body.is_legal_target if body.is_legal_target is not None else True,
        "is_operating":        body.is_operating if body.is_operating is not None else True,
        "equipment_model_id":  body.equipment_model_id,
        "area_id":             body.area_id,
        "ksic_code":           body.ksic_code,
    }
    insert_data = {k: v for k, v in insert_data.items() if v is not None}

    res = supabase.table("equipment_assets").insert(insert_data).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="설비 등록 실패")
    new_asset = res.data[0]

    try:
        from routers.event_trigger import trigger_event_schedules
        await trigger_event_schedules(
            factory_id = body.factory_id,
            event_type = "INSTALL",
            event_date = date.today(),
            context    = {"equipment_id": new_asset["id"], "equipment_name": body.asset_name, "company_id": company_id},
        )
    except Exception as e:
        print(f"[EQUIPMENT] INSTALL 트리거 실패 (asset={new_asset.get('id')}): {e}")

    return {"status": "success", "message": f"설비 '{body.asset_name}' 등록 완료", "data": new_asset}


# ── v1.2.0: QR URL 생성 ──────────────────────────────────────
@router.post("/{asset_id}/generate-qr")
def generate_qr(asset_id: str):
    supabase = get_supabase()
    asset_res = supabase.table("equipment_assets").select("id, asset_name, asset_code, factory_id").eq("id", asset_id).limit(1).execute()
    if not asset_res.data:
        raise HTTPException(status_code=404, detail="설비를 찾을 수 없습니다")
    asset   = asset_res.data[0]
    qr_url  = f"https://safe.taieng.co.kr/checkin?id={asset_id}"
    now_iso = datetime.now(timezone.utc).isoformat()
    supabase.table("equipment_assets").update({"qr_code": qr_url, "qr_code_generated_at": now_iso}).eq("id", asset_id).execute()
    return {"status": "success", "data": {"qr_url": qr_url, "asset_id": asset_id, "asset_name": asset["asset_name"], "asset_code": asset.get("asset_code"), "generated_at": now_iso}}


# ── v1.2.0: QR 출력 횟수 ────────────────────────────────────
@router.post("/{asset_id}/qr-printed")
def increment_qr_print(asset_id: str):
    supabase = get_supabase()
    asset_res = supabase.table("equipment_assets").select("qr_print_count").eq("id", asset_id).limit(1).execute()
    if not asset_res.data:
        raise HTTPException(status_code=404, detail="설비를 찾을 수 없습니다")
    current = asset_res.data[0].get("qr_print_count") or 0
    supabase.table("equipment_assets").update({"qr_print_count": current + 1}).eq("id", asset_id).execute()
    return {"status": "success", "qr_print_count": current + 1}


# ── 설비 수정 ────────────────────────────────────────────────
@router.patch("/{asset_id}")
def update_asset(asset_id: str, body: EquipmentAssetUpdate):
    supabase = get_supabase()
    update_data = {k: v for k, v in body.dict().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=422, detail="수정할 내용이 없습니다.")
    res = supabase.table("equipment_assets").update(update_data).eq("id", asset_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="설비를 찾을 수 없습니다.")
    return {"status": "success", "message": "수정 완료", "data": res.data[0]}


# ── 설비 삭제 (soft) ─────────────────────────────────────────
@router.delete("/{asset_id}")
def delete_asset(asset_id: str):
    supabase = get_supabase()
    res = supabase.table("equipment_assets").update({"is_operating": False}).eq("id", asset_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="설비를 찾을 수 없습니다.")
    return {"status": "success", "message": "설비가 비활성화됐습니다."}
