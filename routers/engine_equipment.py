"""
엔진 설비 마스터 관리 라우터 — v1.0.0

대상 테이블:
  - process_equipment_map  : 공정↔설비 매핑 마스터 (118만 건, 고유 설비 508개)
  - equipment_model_master : 설비 모델 마스터 (2,874건)

엔드포인트:
  GET  /engine-equipment/list          설비 마스터 목록 (facility_name_std 집계)
  GET  /engine-equipment/detail/{name} 설비 상세 (매핑 공정 목록 포함)
  PATCH /engine-equipment/update/{name} 설비 메타 수정 (카테고리/검토상태)
  GET  /engine-equipment/models        모델 마스터 목록
  GET  /engine-equipment/models/{id}   모델 상세
  PATCH /engine-equipment/models/{id}  모델 수정
  GET  /engine-equipment/stats         전체 통계
  POST /engine-equipment/review/approve 검토필요 항목 일괄 승인
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import datetime, timezone
from db.supabase_client import get_supabase

router = APIRouter(prefix="/engine-equipment", tags=["엔진설비마스터"])

# 카테고리 코드 → 한글 매핑
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

# match_band 우선순위
BAND_PRIORITY = {"MUST": 1, "CORE": 2, "OPTIONAL": 3, "REFERENCE": 4}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────────
# GET /engine-equipment/stats  전체 통계
# ─────────────────────────────────────────────────────
@router.get("/stats")
async def get_equipment_stats():
    """엔진 설비 마스터 전체 통계 조회"""
    supabase = get_supabase()

    # 전체 집계 (고유 설비 기준)
    all_res = supabase.table("process_equipment_map").select(
        "facility_name_std, source_facility_category, match_band, needs_review",
        count="exact"
    ).limit(0).execute()
    total_rows = all_res.count or 0

    # 고유 설비명 수
    unique_res = supabase.rpc("count_distinct_equipment", {}).execute() if False else None
    # 직접 집계: match_band별
    band_res = supabase.table("process_equipment_map").select(
        "match_band"
    ).limit(2000).execute()

    # 카테고리별 고유 설비 수 (샘플 집계)
    cat_sample = supabase.table("process_equipment_map").select(
        "facility_name_std, source_facility_category, match_band, needs_review"
    ).limit(10000).execute()
    sample = cat_sample.data or []

    seen = set()
    cat_count: dict = {}
    band_count: dict = {"MUST": 0, "CORE": 0, "OPTIONAL": 0, "REFERENCE": 0}
    review_count = 0

    for row in sample:
        name = row.get("facility_name_std", "")
        cat  = row.get("source_facility_category") or ""
        band = row.get("match_band") or ""
        rev  = row.get("needs_review", False)

        if name not in seen:
            seen.add(name)
            cat_count[cat] = cat_count.get(cat, 0) + 1
            if band in band_count:
                band_count[band] += 1
            if rev:
                review_count += 1

    # 모델 마스터 수
    model_res = supabase.table("equipment_model_master").select(
        "id", count="exact"
    ).limit(0).execute()
    model_total = model_res.count or 0

    return {
        "status": "success",
        "data": {
            "total_mapping_rows": total_rows,
            "unique_equipment_approx": len(seen),
            "model_master_total": model_total,
            "needs_review_approx": review_count,
            "band_distribution": band_count,
            "category_distribution": {
                k: {"count": v, "label": CATEGORY_MAP.get(k, k)}
                for k, v in sorted(cat_count.items(), key=lambda x: -x[1])
            },
        }
    }


# ─────────────────────────────────────────────────────
# GET /engine-equipment/list  설비 마스터 목록
# facility_name_std 기준 집계 — 고유 설비 508개 관리
# ─────────────────────────────────────────────────────
@router.get("/list")
async def list_equipment_master(
    search:    Optional[str]  = Query(None, description="설비명 검색"),
    category:  Optional[str]  = Query(None, description="source_facility_category 필터"),
    band:      Optional[str]  = Query(None, description="match_band 필터 (MUST/CORE/OPTIONAL/REFERENCE)"),
    needs_review: Optional[bool] = Query(None, description="검토 필요 여부 필터"),
    page:      int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """
    고유 설비명(facility_name_std) 기준 집계 목록.
    페이지당 50건 기본, 최대 200건.
    데이터 규모(118만)로 인해 Python 측 집계 방식 사용.
    """
    supabase = get_supabase()

    # 필터 조건 구성
    query = supabase.table("process_equipment_map").select(
        "facility_name_std, source_facility_category, category_path, "
        "match_band, match_score, source_type, needs_review, "
        "equipment_role, equipment_source_file"
    )

    if category:
        query = query.eq("source_facility_category", category)
    if band:
        query = query.eq("match_band", band)
    if needs_review is not None:
        query = query.eq("needs_review", needs_review)

    # 데이터 크기 제한: 최대 50000건 fetch 후 Python 집계
    query = query.limit(50000)
    res = query.execute()
    rows = res.data or []

    # facility_name_std 기준 집계
    equip_map: dict = {}
    for row in rows:
        name = row.get("facility_name_std", "") or ""
        if not name:
            continue
        if name not in equip_map:
            equip_map[name] = {
                "facility_name_std":      name,
                "source_facility_category": row.get("source_facility_category") or "",
                "category_label":         CATEGORY_MAP.get(row.get("source_facility_category") or "", ""),
                "category_path":          row.get("category_path") or "",
                "best_band":              row.get("match_band") or "",
                "best_score":             float(row.get("match_score") or 0),
                "process_count":          0,
                "needs_review":           False,
                "source_types":           set(),
            }
        e = equip_map[name]
        e["process_count"] += 1
        if row.get("needs_review"):
            e["needs_review"] = True
        if row.get("source_type"):
            e["source_types"].add(row["source_type"])
        # 최우선 밴드 업데이트
        cur_pri = BAND_PRIORITY.get(e["best_band"], 99)
        new_pri = BAND_PRIORITY.get(row.get("match_band") or "", 99)
        if new_pri < cur_pri:
            e["best_band"]  = row["match_band"]
            e["best_score"] = float(row.get("match_score") or 0)

    # 검색 필터 (Python 측)
    equip_list = list(equip_map.values())
    if search:
        s = search.lower()
        equip_list = [e for e in equip_list if s in e["facility_name_std"].lower()]

    # set → list 변환
    for e in equip_list:
        e["source_types"] = sorted(e["source_types"])

    # 이름순 정렬
    equip_list.sort(key=lambda x: x["facility_name_std"])

    total = len(equip_list)
    offset = (page - 1) * page_size
    page_items = equip_list[offset: offset + page_size]

    return {
        "status": "success",
        "data": {
            "items":       page_items,
            "total":       total,
            "page":        page,
            "page_size":   page_size,
            "total_pages": (total + page_size - 1) // page_size,
        }
    }


# ─────────────────────────────────────────────────────
# GET /engine-equipment/detail/{facility_name}
# 설비 상세 — 매핑된 공정 목록 포함
# ─────────────────────────────────────────────────────
@router.get("/detail/{facility_name}")
async def get_equipment_detail(facility_name: str):
    """설비명 기준 상세 — 연결된 공정 목록, 업종 분포 포함"""
    supabase = get_supabase()

    res = supabase.table("process_equipment_map").select(
        "id, process_id, process_path, process_lv1, process_lv2, process_lv3, process_lv4, "
        "industry_code_full, industry_name_full, "
        "match_band, match_score, source_type, needs_review, "
        "source_facility_category, category_path, equipment_role"
    ).eq("facility_name_std", facility_name).order("match_band").limit(500).execute()

    rows = res.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="설비를 찾을 수 없습니다.")

    # 업종 분포
    industry_set: dict = {}
    band_dist: dict = {"MUST": 0, "CORE": 0, "OPTIONAL": 0, "REFERENCE": 0}
    for row in rows:
        ind = row.get("industry_code_full", "")
        if ind:
            industry_set[ind] = row.get("industry_name_full", ind)
        b = row.get("match_band", "")
        if b in band_dist:
            band_dist[b] += 1

    first = rows[0]
    return {
        "status": "success",
        "data": {
            "facility_name_std":      facility_name,
            "source_facility_category": first.get("source_facility_category") or "",
            "category_label":         CATEGORY_MAP.get(first.get("source_facility_category") or "", ""),
            "category_path":          first.get("category_path") or "",
            "equipment_role":         first.get("equipment_role") or "",
            "total_mappings":         len(rows),
            "industry_count":         len(industry_set),
            "band_distribution":      band_dist,
            "processes":              rows[:100],  # 최대 100건만 반환
        }
    }


# ─────────────────────────────────────────────────────
# PATCH /engine-equipment/update/{facility_name}
# 설비 메타 수정 (카테고리/검토상태/카테고리경로)
# ─────────────────────────────────────────────────────
@router.patch("/update/{facility_name}")
async def update_equipment_master(facility_name: str, body: dict):
    """
    facility_name_std 기준으로 process_equipment_map 전체 행 일괄 업데이트.
    수정 가능: source_facility_category, category_path, needs_review, equipment_role
    """
    supabase = get_supabase()

    allowed = {"source_facility_category", "category_path", "needs_review", "equipment_role"}
    update_data = {k: v for k, v in body.items() if k in allowed}

    if not update_data:
        raise HTTPException(status_code=400, detail="수정할 항목이 없습니다.")

    res = supabase.table("process_equipment_map").update(
        update_data
    ).eq("facility_name_std", facility_name).execute()

    updated_count = len(res.data or [])
    return {
        "status": "success",
        "message": f"{updated_count}건 업데이트됐습니다.",
        "data": {"facility_name_std": facility_name, "updated_count": updated_count, **update_data}
    }


# ─────────────────────────────────────────────────────
# POST /engine-equipment/review/approve
# 검토 필요 항목 일괄 승인 (needs_review → false)
# ─────────────────────────────────────────────────────
@router.post("/review/approve")
async def bulk_approve_review(body: dict):
    """
    facility_names 배열을 받아 needs_review = false 일괄 처리.
    body: { "facility_names": ["설비명1", "설비명2", ...] }
    """
    supabase = get_supabase()

    names = body.get("facility_names", [])
    if not names:
        raise HTTPException(status_code=400, detail="facility_names가 필요합니다.")

    res = supabase.table("process_equipment_map").update(
        {"needs_review": False}
    ).in_("facility_name_std", names).execute()

    updated = len(res.data or [])
    return {
        "status": "success",
        "message": f"{updated}건 검토 승인 처리됐습니다.",
        "data": {"approved_count": updated}
    }


# ─────────────────────────────────────────────────────
# GET /engine-equipment/models  모델 마스터 목록
# ─────────────────────────────────────────────────────
@router.get("/models")
async def list_equipment_models(
    search:       Optional[str] = Query(None, description="모델명/제조사 검색"),
    equipment_std: Optional[str] = Query(None, description="설비표준명 필터"),
    manufacturer: Optional[str] = Query(None, description="제조사 필터"),
    source_type:  Optional[str] = Query(None, description="소스 타입 필터"),
    page:      int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
):
    """모델 마스터 목록 조회"""
    supabase = get_supabase()
    offset = (page - 1) * page_size

    query = supabase.table("equipment_model_master").select(
        "id, manufacturer, model_name, equipment_std, primary_equipment_std, "
        "model_year, expected_life_years, maintenance_cycle_months, "
        "risk_score, criticality_score, certification_class, "
        "source_type, cert_match_status, certification_status, "
        "country_of_origin, equipment_lv2",
        count="exact"
    )

    if equipment_std:
        query = query.eq("equipment_std", equipment_std)
    if manufacturer:
        query = query.ilike("manufacturer", f"%{manufacturer}%")
    if source_type:
        query = query.eq("source_type", source_type)
    if search:
        query = query.or_(
            f"model_name.ilike.%{search}%,manufacturer.ilike.%{search}%,equipment_std.ilike.%{search}%"
        )

    query = query.order("equipment_std").order("manufacturer").range(offset, offset + page_size - 1)
    res = query.execute()

    return {
        "status": "success",
        "data": {
            "items":       res.data or [],
            "total":       res.count or 0,
            "page":        page,
            "page_size":   page_size,
            "total_pages": ((res.count or 0) + page_size - 1) // page_size,
        }
    }


# ─────────────────────────────────────────────────────
# GET /engine-equipment/models/{model_id}  모델 상세
# ─────────────────────────────────────────────────────
@router.get("/models/{model_id}")
async def get_model_detail(model_id: str):
    """모델 마스터 단건 상세"""
    supabase = get_supabase()

    res = supabase.table("equipment_model_master").select("*").eq(
        "id", model_id
    ).single().execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="모델을 찾을 수 없습니다.")

    return {"status": "success", "data": res.data}


# ─────────────────────────────────────────────────────
# PATCH /engine-equipment/models/{model_id}  모델 수정
# ─────────────────────────────────────────────────────
@router.patch("/models/{model_id}")
async def update_model(model_id: str, body: dict):
    """모델 마스터 수정 (허용 필드만)"""
    supabase = get_supabase()

    allowed = {
        "manufacturer", "model_name", "equipment_std",
        "model_year", "expected_life_years", "maintenance_cycle_months",
        "risk_score", "criticality_score", "certification_class",
        "source_type", "country_of_origin", "equipment_lv2"
    }
    update_data = {k: v for k, v in body.items() if k in allowed}

    if not update_data:
        raise HTTPException(status_code=400, detail="수정할 항목이 없습니다.")

    res = supabase.table("equipment_model_master").update(
        update_data
    ).eq("id", model_id).execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="모델을 찾을 수 없습니다.")

    return {
        "status": "success",
        "message": "모델이 수정됐습니다.",
        "data": res.data[0]
    }


# ─────────────────────────────────────────────────────
# GET /engine-equipment/categories  카테고리 목록
# ─────────────────────────────────────────────────────
@router.get("/categories")
async def get_categories():
    """설비 카테고리 코드 목록 (필터용)"""
    return {
        "status": "success",
        "data": [
            {"code": k, "label": v}
            for k, v in CATEGORY_MAP.items()
        ]
    }
