"""
엔진 설비 마스터 관리 라우터 — v1.2.1
v1.2.1: /stats에서 별도 count 쿼리 제거 → MV 집계만 사용 (병목 제거)
v1.2.0: MV(engine_equipment_summary) 기반으로 /stats, /list 교체 + POST /refresh
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import datetime, timezone
from db.supabase_client import get_supabase

router = APIRouter(prefix="/engine-equipment", tags=["엔진설비마스터"])

VERSION = "1.2.1"

CATEGORY_MAP = {
    "MECH":     "기계설비",
    "ELEC":     "전기설비",
    "FIRE":     "소방설비",
    "INDUSTRY": "산업설비",
    "ENV":      "환경설비",
    "HAZMAT":   "위험물설비",
    "GAS":      "가스설비",
    "ENERGY":   "에너지설비",
    "UTILITY":  "유틸리티",
    "LIFT":     "승강기설비",
    "BUILD":    "건축부속",
    "SAFETY":   "안전설비",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────────
# GET /engine-equipment/stats  (v1.2.1: count 쿼리 제거)
# ─────────────────────────────────────────────────────
@router.get("/stats")
async def get_equipment_stats():
    """MV(engine_equipment_summary) 단일 조회로 통계 — 빠른 응답"""
    supabase = get_supabase()
    try:
        res = supabase.table("engine_equipment_summary").select(
            "source_facility_category, top_band, needs_review, process_count, "
            "band_must, band_core, band_optional, band_reference"
        ).execute()
        rows = res.data or []

        total = len(rows)
        cat_count: dict = {}
        band_count = {"MUST": 0, "CORE": 0, "OPTIONAL": 0, "REFERENCE": 0}
        review_count = 0
        total_process_mappings = 0

        for row in rows:
            cat  = row.get("source_facility_category") or ""
            band = row.get("top_band") or ""
            rev  = row.get("needs_review", False)
            pc   = row.get("process_count") or 0

            cat_count[cat] = cat_count.get(cat, 0) + 1
            if band in band_count:
                band_count[band] += 1
            if rev:
                review_count += 1
            total_process_mappings += pc

        # 모델 마스터 수 (단순 count — 빠름)
        model_res = supabase.table("equipment_model_master").select(
            "id", count="exact"
        ).limit(0).execute()
        model_total = model_res.count or 0

        return {
            "status": "success",
            "data": {
                "total_mapping_rows":    total_process_mappings,
                "unique_equipment":      total,
                "model_master_total":    model_total,
                "needs_review_count":    review_count,
                "band_distribution":     band_count,
                "category_distribution": {
                    k: {"count": v, "label": CATEGORY_MAP.get(k, k)}
                    for k, v in sorted(cat_count.items(), key=lambda x: -x[1])
                },
                "version": VERSION,
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# GET /engine-equipment/list  (MV 기반 v1.2.0)
# ─────────────────────────────────────────────────────
@router.get("/list")
async def list_equipment_master(
    search:       Optional[str]  = Query(None),
    category:     Optional[str]  = Query(None),
    top_band:     Optional[str]  = Query(None),
    needs_review: Optional[bool] = Query(None),
    page:         int = Query(1, ge=1),
    page_size:    int = Query(50, ge=1, le=200),
):
    """MV(engine_equipment_summary) 기반 목록"""
    supabase = get_supabase()
    try:
        query = supabase.table("engine_equipment_summary").select("*")
        if category:
            query = query.eq("source_facility_category", category)
        if top_band:
            query = query.eq("top_band", top_band)
        if needs_review is not None:
            query = query.eq("needs_review", needs_review)
        if search:
            query = query.ilike("facility_name_std", f"%{search}%")

        query = query.order("process_count", desc=True)
        res = query.execute()
        rows = res.data or []

        for row in rows:
            row["category_label"] = CATEGORY_MAP.get(row.get("source_facility_category") or "", "")

        total = len(rows)
        offset = (page - 1) * page_size
        return {
            "status": "success",
            "data": {
                "items":       rows[offset: offset + page_size],
                "total":       total,
                "page":        page,
                "page_size":   page_size,
                "total_pages": (total + page_size - 1) // page_size if total else 0,
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# POST /engine-equipment/refresh  MV 갱신
# ─────────────────────────────────────────────────────
@router.post("/refresh")
async def refresh_engine_equipment():
    supabase = get_supabase()
    try:
        supabase.rpc("refresh_engine_equipment_summary").execute()
        return {
            "status": "success",
            "message": "engine_equipment_summary MV가 갱신됐습니다.",
            "data": {"refreshed_at": _now_iso()}
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# GET /engine-equipment/detail/{facility_name}
# ─────────────────────────────────────────────────────
@router.get("/detail/{facility_name}")
async def get_equipment_detail(facility_name: str):
    supabase = get_supabase()
    try:
        res = supabase.table("process_equipment_map").select(
            "id, process_id, process_path, process_lv1, process_lv2, process_lv3, process_lv4, "
            "industry_code_full, industry_name_full, "
            "match_band, match_score, source_type, needs_review, "
            "source_facility_category, category_path, equipment_role"
        ).eq("facility_name_std", facility_name).order("match_band").limit(500).execute()
        rows = res.data or []
        if not rows:
            raise HTTPException(status_code=404, detail="설비를 찾을 수 없습니다.")
        industry_set: dict = {}
        band_dist = {"MUST": 0, "CORE": 0, "OPTIONAL": 0, "REFERENCE": 0}
        for row in rows:
            ind = row.get("industry_code_full", "")
            if ind:
                industry_set[ind] = row.get("industry_name_full", ind)
            b = row.get("match_band", "")
            if b in band_dist:
                band_dist[b] += 1
        first = rows[0]
        return {"status": "success", "data": {
            "facility_name_std":        facility_name,
            "source_facility_category": first.get("source_facility_category") or "",
            "category_label":           CATEGORY_MAP.get(first.get("source_facility_category") or "", ""),
            "category_path":            first.get("category_path") or "",
            "equipment_role":           first.get("equipment_role") or "",
            "total_mappings":           len(rows),
            "industry_count":           len(industry_set),
            "band_distribution":        band_dist,
            "processes":                rows[:100],
        }}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/update/{facility_name}")
async def update_equipment_master(facility_name: str, body: dict):
    supabase = get_supabase()
    allowed = {"source_facility_category", "category_path", "needs_review", "equipment_role"}
    update_data = {k: v for k, v in body.items() if k in allowed}
    if not update_data:
        raise HTTPException(status_code=400, detail="수정할 항목이 없습니다.")
    res = supabase.table("process_equipment_map").update(update_data).eq("facility_name_std", facility_name).execute()
    return {"status": "success", "message": f"{len(res.data or [])}건 업데이트됐습니다.",
            "data": {"facility_name_std": facility_name, **update_data}}


@router.post("/review/approve")
async def bulk_approve_review(body: dict):
    supabase = get_supabase()
    names = body.get("facility_names", [])
    if not names:
        raise HTTPException(status_code=400, detail="facility_names가 필요합니다.")
    res = supabase.table("process_equipment_map").update({"needs_review": False}).in_("facility_name_std", names).execute()
    return {"status": "success", "message": f"{len(res.data or [])}건 검토 승인됐습니다.",
            "data": {"approved_count": len(res.data or [])}}


@router.get("/models")
async def list_equipment_models(
    search:        Optional[str] = Query(None),
    equipment_std: Optional[str] = Query(None),
    manufacturer:  Optional[str] = Query(None),
    source_type:   Optional[str] = Query(None),
    page:      int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
):
    supabase = get_supabase()
    offset = (page - 1) * page_size
    query = supabase.table("equipment_model_master").select(
        "id, manufacturer, model_name, equipment_std, primary_equipment_std, "
        "model_year, expected_life_years, maintenance_cycle_months, "
        "risk_score, criticality_score, source_type, cert_match_status, "
        "country_of_origin, equipment_lv2",
        count="exact"
    )
    if equipment_std: query = query.eq("equipment_std", equipment_std)
    if manufacturer:  query = query.ilike("manufacturer", f"%{manufacturer}%")
    if source_type:   query = query.eq("source_type", source_type)
    if search:        query = query.or_(f"model_name.ilike.%{search}%,manufacturer.ilike.%{search}%,equipment_std.ilike.%{search}%")
    query = query.order("equipment_std").order("manufacturer").range(offset, offset + page_size - 1)
    res = query.execute()
    return {"status": "success", "data": {
        "items": res.data or [], "total": res.count or 0, "page": page, "page_size": page_size,
        "total_pages": ((res.count or 0) + page_size - 1) // page_size,
    }}


@router.get("/models/{model_id}")
async def get_model_detail(model_id: str):
    supabase = get_supabase()
    res = supabase.table("equipment_model_master").select("*").eq("id", model_id).limit(1).execute()
    rows = res.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="모델을 찾을 수 없습니다.")
    return {"status": "success", "data": rows[0]}


@router.patch("/models/{model_id}")
async def update_model(model_id: str, body: dict):
    supabase = get_supabase()
    allowed = {"manufacturer", "model_name", "equipment_std", "model_year",
               "expected_life_years", "maintenance_cycle_months", "risk_score",
               "criticality_score", "source_type", "country_of_origin", "equipment_lv2"}
    update_data = {k: v for k, v in body.items() if k in allowed}
    if not update_data:
        raise HTTPException(status_code=400, detail="수정할 항목이 없습니다.")
    res = supabase.table("equipment_model_master").update(update_data).eq("id", model_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="모델을 찾을 수 없습니다.")
    return {"status": "success", "message": "모델이 수정됐습니다.", "data": res.data[0]}


@router.get("/categories")
async def get_categories():
    return {"status": "success", "data": [{"code": k, "label": v} for k, v in CATEGORY_MAP.items()]}
