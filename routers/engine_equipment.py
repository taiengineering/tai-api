"""
엔진 설비 마스터 관리 라우터 — v4.4.0
v4.4.0: 수리 완료 후 anchor 재설정
  - PATCH /assets/{asset_id}: is_operating + repair_date 필드 추가
    - is_operating=false: 설비만 업데이트, work_schedules 건드리지 않음
    - is_operating=true + repair_date: factory의 MANUAL ACTIVE inspection_sets 재생성
v4.3.3: assets-list 응답을 data.items 형태로 통일
v4.3.2: stats 확장 + GET /assets-list + PATCH /assets/{asset_id}
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date, timezone
from dateutil.relativedelta import relativedelta
from db.supabase_client import get_supabase

router = APIRouter(prefix="/engine-equipment", tags=["엔진설비마스터"])

VERSION = "4.4.0"

CATEGORY_MAP = {
    "MECH":     "기계설비", "ELEC":     "전기설비", "FIRE":     "소방설비",
    "INDUSTRY": "산업설비", "ENV":      "환경설비", "HAZMAT":   "위험물설비",
    "GAS":      "가스설비", "ENERGY":   "에너지설비", "UTILITY":  "유틸리티",
    "LIFT":     "승강기설비", "BUILD":    "건축부속", "SAFETY":   "안전설비",
}

# cycle_unit → relativedelta
DELTA_MAP = {
    "day":       lambda v: relativedelta(days=v),
    "week":      lambda v: relativedelta(weeks=v),
    "month":     lambda v: relativedelta(months=v),
    "quarter":   lambda v: relativedelta(months=3 * v),
    "half_year": lambda v: relativedelta(months=6 * v),
    "year":      lambda v: relativedelta(years=v),
}
REPEAT_TYPE_MAP = {
    "day": "daily", "week": "weekly", "month": "monthly",
    "quarter": "quarterly", "half_year": "half_yearly", "year": "yearly",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_schedules_for_repair(iset: dict, anchor: date, end: date) -> list:
    """수리 완료 후 anchor 기준 1년치 반복 일정 rows 생성."""
    cycle_unit  = (iset.get("cycle_unit") or "year").lower()
    cycle_value = int(iset.get("cycle_value") or 1)
    fn          = DELTA_MAP.get(cycle_unit)
    delta       = fn(cycle_value) if fn else relativedelta(years=cycle_value)
    repeat_type = REPEAT_TYPE_MAP.get(cycle_unit, "yearly")

    rows, cursor = [], anchor
    while cursor <= end:
        rows.append({
            "factory_id":        iset["factory_id"],
            "company_id":        iset.get("company_id"),
            "inspection_set_id": iset["id"],
            "planned_date":      cursor.isoformat(),
            "start_date":        cursor.isoformat(),
            "end_date":          cursor.isoformat(),
            "repeat_type":       repeat_type,
            "repeat_interval":   cycle_value,
            "status_code":       "SCHEDULED",
            "source_type":       "MANUAL",
            "obligation_type":   iset.get("inspection_category") or "GENERAL",
            "summary":           iset.get("inspection_set_name") or "",
            "active_yn":         True,
        })
        cursor += delta
    return rows


# ───────────────────────────────────────────────────
# Pydantic 모델
# ───────────────────────────────────────────────────

class AssetPatchBody(BaseModel):
    last_inspection_date:  Optional[date] = None
    next_inspection_date:  Optional[date] = None
    equipment_model_id:    Optional[str]  = None
    model_id:              Optional[str]  = None  # 별칭 → equipment_model_id
    is_legal_target:       Optional[bool] = None
    # v4.4.0 신규
    is_operating:          Optional[bool] = None  # True=정상운전, False=고장/정지
    repair_date:           Optional[str]  = None  # 수리완료일 'YYYY-MM-DD' (is_operating=True일 때만 유효)


# ───────────────────────────────────────────────────
# GET /engine-equipment/stats
# ───────────────────────────────────────────────────
@router.get("/stats")
async def get_equipment_stats():
    supabase = get_supabase()
    try:
        res = supabase.table("engine_equipment_summary").select(
            "source_facility_category, top_band, needs_review, process_count"
        ).execute()
        rows = res.data or []

        total = len(rows)
        cat_count: dict = {}
        band_count = {"MUST": 0, "CORE": 0, "OPTIONAL": 0, "REFERENCE": 0}
        review_count = 0
        total_mappings = 0

        for row in rows:
            cat  = row.get("source_facility_category") or ""
            band = row.get("top_band") or ""
            cat_count[cat] = cat_count.get(cat, 0) + 1
            if band in band_count:
                band_count[band] += 1
            if row.get("needs_review"):
                review_count += 1
            total_mappings += row.get("process_count") or 0

        model_res = supabase.table("equipment_model_master").select("id", count="exact").limit(0).execute()

        asset_total_res = supabase.table("equipment_assets").select("id", count="exact").limit(0).execute()
        asset_total = asset_total_res.count or 0

        asset_no_model_res = supabase.table("equipment_assets").select("id", count="exact")\
            .is_("equipment_model_id", "null").limit(0).execute()
        asset_no_model = asset_no_model_res.count or 0

        asset_no_insp_res = supabase.table("equipment_assets").select("id", count="exact")\
            .is_("last_inspection_date", "null").limit(0).execute()
        asset_no_inspection = asset_no_insp_res.count or 0

        legal_target_res = supabase.table("master_legal_inspection_target").select("id", count="exact").limit(0).execute()
        legal_target_count = legal_target_res.count or 0

        legal_rows = supabase.table("master_legal_inspection_target").select("equipment_name").execute()
        legal_names = [r.get("equipment_name", "") for r in (legal_rows.data or []) if r.get("equipment_name")]
        unmapped_count = 0
        for lname in legal_names:
            chk = supabase.table("equipment_assets").select("id", count="exact")\
                .ilike("asset_name", f"%{lname[:6]}%").limit(0).execute()
            if (chk.count or 0) == 0:
                unmapped_count += 1

        return {"status": "success", "data": {
            "total_mapping_rows":    total_mappings,
            "unique_equipment":      total,
            "model_master_total":    model_res.count or 0,
            "needs_review_count":    review_count,
            "band_distribution":     band_count,
            "category_distribution": {
                k: {"count": v, "label": CATEGORY_MAP.get(k, k)}
                for k, v in sorted(cat_count.items(), key=lambda x: -x[1])
            },
            "asset_registered_total":       asset_total,
            "asset_no_model":               asset_no_model,
            "asset_no_inspection":          asset_no_inspection,
            "legal_inspection_target_count": legal_target_count,
            "legal_inspection_unmapped":    unmapped_count,
            "version": VERSION,
        }}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ───────────────────────────────────────────────────
# GET /engine-equipment/assets-list
# ───────────────────────────────────────────────────
def _enrich_asset_row(row: dict) -> dict:
    mid = row.get("equipment_model_id") or row.get("model_id")
    row["has_model"] = mid is not None
    row["facility_category"] = row.get("equipment_type_code") or ""
    row["rule_count"] = 0
    row["has_inspection"] = bool(row.get("last_inspection_date"))
    row["has_failure"] = False
    return row


@router.get("/assets-list")
async def list_assets(
    page:                int           = Query(1, ge=1),
    page_size:           int           = Query(50, ge=1, le=5000),
    search:              Optional[str] = Query(None),
    has_model:           Optional[bool] = Query(None),
    no_inspection:       Optional[bool] = Query(None),
    is_legal_target:     Optional[bool] = Query(None),
    equipment_type_code: Optional[str] = Query(None),
):
    supabase = get_supabase()
    try:
        def _apply_filters(q):
            if search:
                q = q.ilike("asset_name", f"%{search.strip()}%")
            if has_model is True:
                q = q.not_.is_("equipment_model_id", "null")
            elif has_model is False:
                q = q.is_("equipment_model_id", "null")
            if no_inspection is True:
                q = q.is_("last_inspection_date", "null")
            elif no_inspection is False:
                q = q.not_.is_("last_inspection_date", "null")
            if is_legal_target is not None:
                q = q.eq("is_legal_target", is_legal_target)
            if equipment_type_code:
                q = q.eq("equipment_type_code", equipment_type_code)
            return q

        count_q = _apply_filters(supabase.table("equipment_assets").select("id", count="exact"))
        total = (count_q.limit(0).execute().count) or 0

        offset = (page - 1) * page_size
        data_q = _apply_filters(supabase.table("equipment_assets").select("*"))
        data_q = data_q.order("created_at", desc=True).range(offset, offset + page_size - 1)
        res = data_q.execute()

        items = [_enrich_asset_row(dict(r)) for r in (res.data or [])]
        return {
            "status": "success",
            "data": {
                "items": items, "total": total, "page": page, "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size if total else 0,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ───────────────────────────────────────────────────
# PATCH /engine-equipment/assets/{asset_id}  v4.4.0
# ───────────────────────────────────────────────────
@router.patch("/assets/{asset_id}")
async def patch_asset(asset_id: str, body: AssetPatchBody):
    """
    v4.4.0: is_operating + repair_date 수리완료 로직 추가.
    - is_operating=False: 설비만 업데이트, work_schedules 건드리지 않음
    - is_operating=True + repair_date: factory의 MANUAL ACTIVE inspection_sets
      SCHEDULED 일정 삭제 훈 repair_date 기준 1년치 재생성
    """
    supabase = get_supabase()
    try:
        # equipment_assets 업데이트 데이터 구성
        update_data = {}
        if body.last_inspection_date is not None:
            update_data["last_inspection_date"] = body.last_inspection_date.isoformat()
        if body.next_inspection_date is not None:
            update_data["next_inspection_date"] = body.next_inspection_date.isoformat()
        if body.is_legal_target is not None:
            update_data["is_legal_target"] = body.is_legal_target
        if body.is_operating is not None:
            update_data["is_operating"] = body.is_operating
        # model_id / equipment_model_id 별칭 처리
        if body.model_id and not body.equipment_model_id:
            update_data["equipment_model_id"] = body.model_id
        elif body.equipment_model_id:
            update_data["equipment_model_id"] = body.equipment_model_id

        if not update_data:
            raise HTTPException(status_code=400, detail="수정할 항목이 없습니다.")

        update_data["updated_at"] = _now_iso()

        res = supabase.table("equipment_assets").update(update_data).eq("id", asset_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="자산을 찾을 수 없습니다.")

        asset = res.data[0]
        repair_result = {"schedules_reset": 0, "sets_processed": 0}

        # ── v4.4.0: 수리 완료 시 anchor 재설정 ──
        # is_operating=True 이고 repair_date가 있을 때만 실행
        if body.is_operating is True and body.repair_date:
            try:
                repair_date = date.fromisoformat(body.repair_date)
                end_date    = repair_date + relativedelta(years=1)
                factory_id  = asset.get("factory_id")

                if factory_id:
                    # 해당 시설의 MANUAL ACTIVE inspection_sets 조회
                    sets_res = supabase.table("inspection_sets").select(
                        "id, factory_id, company_id, cycle_value, cycle_unit, "
                        "inspection_set_name, inspection_category"
                    ).eq("factory_id", factory_id).eq("source", "MANUAL").eq(
                        "status_code", "ACTIVE"
                    ).eq("is_active", True).execute()

                    sets = sets_res.data or []
                    total_created = 0

                    for iset in sets:
                        try:
                            # 기존 SCHEDULED 일정 삭제 (COMPLETED 유지)
                            supabase.table("work_schedules").delete().eq(
                                "inspection_set_id", iset["id"]
                            ).eq("status_code", "SCHEDULED").execute()

                            # repair_date 기준 1년치 재생성
                            rows = _build_schedules_for_repair(iset, repair_date, end_date)

                            # inspection_sets anchor 업데이트
                            next_date = repair_date + (DELTA_MAP.get(
                                (iset.get("cycle_unit") or "year").lower(),
                                lambda v: relativedelta(years=v)
                            )(int(iset.get("cycle_value") or 1)))
                            supabase.table("inspection_sets").update({
                                "schedule_anchor_date": repair_date.isoformat(),
                                "schedule_end_date":    end_date.isoformat(),
                                "next_planned_date":    next_date.isoformat(),
                            }).eq("id", iset["id"]).execute()

                            # 20건씩 배치 INSERT
                            for i in range(0, len(rows), 20):
                                r = supabase.table("work_schedules").insert(rows[i:i + 20]).execute()
                                total_created += len(r.data or [])

                        except Exception as e:
                            print(f"[REPAIR] inspection_set={iset['id']} 일정 재생성 실패: {e}")

                    repair_result = {
                        "schedules_reset": total_created,
                        "sets_processed":  len(sets),
                        "repair_date":     repair_date.isoformat(),
                        "end_date":        end_date.isoformat(),
                    }
            except Exception as e:
                print(f"[REPAIR] anchor 재설정 실패 (asset_id={asset_id}): {e}")
                # 엔진 상태 업데이트는 성공했으므로 일정 실패는 응답을 막지 않음

        return {
            "status": "success",
            "data":   {**asset, "repair_result": repair_result},
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ───────────────────────────────────────────────────
# GET /engine-equipment/list
# ───────────────────────────────────────────────────
@router.get("/list")
async def list_equipment_master(
    search:       Optional[str]  = Query(None),
    category:     Optional[str]  = Query(None),
    top_band:     Optional[str]  = Query(None),
    needs_review: Optional[bool] = Query(None),
    page:         int = Query(1, ge=1),
    page_size:    int = Query(50, ge=1, le=200),
):
    supabase = get_supabase()
    try:
        count_q = supabase.table("engine_equipment_summary").select("facility_name_std", count="exact")
        if category:     count_q = count_q.eq("source_facility_category", category)
        if top_band:     count_q = count_q.eq("top_band", top_band)
        if needs_review is not None: count_q = count_q.eq("needs_review", needs_review)
        if search:       count_q = count_q.ilike("facility_name_std", f"%{search}%")
        total = (count_q.limit(0).execute().count) or 0

        offset = (page - 1) * page_size
        data_q = supabase.table("engine_equipment_summary").select("*")
        if category:     data_q = data_q.eq("source_facility_category", category)
        if top_band:     data_q = data_q.eq("top_band", top_band)
        if needs_review is not None: data_q = data_q.eq("needs_review", needs_review)
        if search:       data_q = data_q.ilike("facility_name_std", f"%{search}%")
        data_q = data_q.order("process_count", desc=True).range(offset, offset + page_size - 1)
        res = data_q.execute()

        rows = res.data or []
        for row in rows:
            row["category_label"] = CATEGORY_MAP.get(row.get("source_facility_category") or "", "")

        return {"status": "success", "data": {
            "items":       rows,
            "total":       total,
            "page":        page,
            "page_size":   page_size,
            "total_pages": (total + page_size - 1) // page_size if total else 0,
        }}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/refresh")
async def refresh_engine_equipment():
    supabase = get_supabase()
    try:
        supabase.rpc("refresh_engine_equipment_summary").execute()
        return {"status": "success", "message": "MV가 갱신됐습니다.", "data": {"refreshed_at": _now_iso()}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/detail/{facility_name}")
async def get_equipment_detail(facility_name: str):
    supabase = get_supabase()
    try:
        res = supabase.table("process_equipment_map").select(
            "id, process_id, process_path, process_lv1, process_lv2, process_lv3, process_lv4, "
            "industry_code_full, industry_name_full, match_band, match_score, source_type, "
            "needs_review, source_facility_category, category_path, equipment_role"
        ).eq("facility_name_std", facility_name).order("match_band").limit(500).execute()
        rows = res.data or []
        if not rows:
            raise HTTPException(status_code=404, detail="설비를 찾을 수 없습니다.")
        industry_set: dict = {}
        band_dist = {"MUST": 0, "CORE": 0, "OPTIONAL": 0, "REFERENCE": 0}
        for row in rows:
            ind = row.get("industry_code_full", "")
            if ind: industry_set[ind] = row.get("industry_name_full", ind)
            b = row.get("match_band", "")
            if b in band_dist: band_dist[b] += 1
        first = rows[0]
        return {"status": "success", "data": {
            "facility_name_std": facility_name,
            "source_facility_category": first.get("source_facility_category") or "",
            "category_label": CATEGORY_MAP.get(first.get("source_facility_category") or "", ""),
            "category_path": first.get("category_path") or "",
            "equipment_role": first.get("equipment_role") or "",
            "total_mappings": len(rows), "industry_count": len(industry_set),
            "band_distribution": band_dist, "processes": rows[:100],
        }}
    except HTTPException: raise
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))


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
    return {"status": "success", "message": f"{len(res.data or [])}건 승인됐습니다.",
            "data": {"approved_count": len(res.data or [])}}


@router.get("/models")
async def list_equipment_models(
    search:        Optional[str] = Query(None),
    equipment_std: Optional[str] = Query(None),
    manufacturer:  Optional[str] = Query(None),
    source_type:   Optional[str] = Query(None),
    page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100),
):
    supabase = get_supabase()
    offset = (page - 1) * page_size
    q = supabase.table("equipment_model_master").select(
        "id, manufacturer, model_name, equipment_std, primary_equipment_std, "
        "model_year, expected_life_years, maintenance_cycle_months, risk_score, "
        "criticality_score, source_type, cert_match_status, country_of_origin, equipment_lv2",
        count="exact"
    )
    if equipment_std: q = q.eq("equipment_std", equipment_std)
    if manufacturer:  q = q.ilike("manufacturer", f"%{manufacturer}%")
    if source_type:   q = q.eq("source_type", source_type)
    if search:        q = q.or_(f"model_name.ilike.%{search}%,manufacturer.ilike.%{search}%,equipment_std.ilike.%{search}%")
    q = q.order("equipment_std").order("manufacturer").range(offset, offset + page_size - 1)
    res = q.execute()
    return {"status": "success", "data": {
        "items": res.data or [], "total": res.count or 0, "page": page, "page_size": page_size,
        "total_pages": ((res.count or 0) + page_size - 1) // page_size,
    }}


@router.get("/models/{model_id}")
async def get_model_detail(model_id: str):
    supabase = get_supabase()
    res = supabase.table("equipment_model_master").select("*").eq("id", model_id).limit(1).execute()
    rows = res.data or []
    if not rows: raise HTTPException(status_code=404, detail="모델을 찾을 수 없습니다.")
    return {"status": "success", "data": rows[0]}


@router.patch("/models/{model_id}")
async def update_model(model_id: str, body: dict):
    supabase = get_supabase()
    allowed = {"manufacturer", "model_name", "equipment_std", "model_year",
               "expected_life_years", "maintenance_cycle_months", "risk_score",
               "criticality_score", "source_type", "country_of_origin", "equipment_lv2"}
    update_data = {k: v for k, v in body.items() if k in allowed}
    if not update_data: raise HTTPException(status_code=400, detail="수정할 항목이 없습니다.")
    res = supabase.table("equipment_model_master").update(update_data).eq("id", model_id).execute()
    if not res.data: raise HTTPException(status_code=404, detail="모델을 찾을 수 없습니다.")
    return {"status": "success", "message": "모델이 수정됐습니다.", "data": res.data[0]}


@router.get("/categories")
async def get_categories():
    return {"status": "success", "data": [{"code": k, "label": v} for k, v in CATEGORY_MAP.items()]}
