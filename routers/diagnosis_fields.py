# routers/diagnosis_fields.py — 법령진단 입력항목 + 가격판단 API
# v1.0.0 (2026-04-15): 신규
#   GET /diagnosis/fields?sector=&tier=   — 동적 폼 데이터 (공개)
#   GET /diagnosis/pricing?sector=&total_floor_area=  — 가격 자동 판단 (공개)
#
# 섭터별 tier 맵핑:
#   BUILDING:     FREE(8) | PAID(36)   → 연면적 5000㎡ 기준 99K/249K
#   INDUSTRIAL:     FREE(3) | PAID1(15) | PAID2(+9=24) | PAID3(+12=36)
#   CONSTRUCTION: FREE(4) | PAID(24)  → 199K 고정
from collections import defaultdict
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from db.database import get_supabase
from constants.sectors import VALID_SECTORS, sector_codes_for_query
from services.legal_rules import normalize_sector_db

router = APIRouter(prefix="/diagnosis", tags=["다에진 입력항목"])

# 산업 누적 tier 순서
INDUSTRY_TIER_ORDER = ["PAID1", "PAID2", "PAID3"]


# ── GET /diagnosis/fields ──────────────────────────────────

@router.get("/fields")
def get_diagnosis_fields(
    sector: str = Query(..., description="BUILDING | INDUSTRIAL | CONSTRUCTION | SPECIAL_FACILITY"),
    tier:   str = Query(..., description="FREE | PAID | PAID1 | PAID2 | PAID3"),
):
    """
    섭터/티어별 진단 입력항목 조회.

    산업(INDUSTRIAL)는 누적 구조:
    - PAID2 요청 → PAID1 + PAID2 필드 합산
    - PAID3 요청 → PAID1 + PAID2 + PAID3 필드 합산

    인증 불필요 (공개 API).
    """
    sector = normalize_sector_db(sector)
    tier   = tier.upper()

    if sector not in VALID_SECTORS:
        raise HTTPException(status_code=400, detail=f"sector는 {sorted(VALID_SECTORS)} 중 하나여야 합니다")

    sb = get_supabase()

    # 산업 누적 tier 연산
    if sector == "INDUSTRIAL" and tier in INDUSTRY_TIER_ORDER:
        idx = INDUSTRY_TIER_ORDER.index(tier)
        tiers_to_fetch = ["FREE"] + INDUSTRY_TIER_ORDER[:idx + 1]
    else:
        tiers_to_fetch = [tier]

    res = sb.table("diagnosis_input_fields").select(
        "field_code, field_name, field_type, field_group, "
        "unit, is_required, placeholder, help_text, auto_source, "
        "input_options, sort_order, tier"
    ).in_("sector", list(sector_codes_for_query(sector))).eq("is_active", True).in_("tier", tiers_to_fetch).order("sort_order").execute()

    rows = res.data or []

    # field_group 물로의 가닥 성을 고려한 정렬된 그룹핑
    group_order: list = []
    group_map: dict = defaultdict(list)
    seen_groups: set = set()

    for row in rows:
        grp = row["field_group"]
        if grp not in seen_groups:
            group_order.append(grp)
            seen_groups.add(grp)
        group_map[grp].append({
            "field_code":    row["field_code"],
            "field_name":    row["field_name"],
            "field_type":    row["field_type"],
            "unit":          row.get("unit"),
            "is_required":   row["is_required"],
            "placeholder":   row.get("placeholder"),
            "help_text":     row.get("help_text"),
            "auto_source":   row.get("auto_source"),
            "input_options": row.get("input_options"),
            "tier":          row.get("tier"),
        })

    groups = [{"group": g, "fields": group_map[g]} for g in group_order]
    total_fields = sum(len(g["fields"]) for g in groups)

    return {
        "success": True,
        "data": {
            "sector":      sector,
            "tier":        tier,
            "tiers_fetched": tiers_to_fetch,
            "field_count": total_fields,
            "groups":      groups,
        },
    }


# ── GET /diagnosis/pricing ──────────────────────────────────

@router.get("/pricing")
def get_diagnosis_pricing(
    sector:           str = Query(..., description="BUILDING | INDUSTRIAL | CONSTRUCTION | SPECIAL_FACILITY"),
    total_floor_area: Optional[float] = Query(None, description="연면적(㎡) — BUILDING 에서 필수"),
    tier:             Optional[str]  = Query(None, description="INDUSTRIAL 에서 PAID1|PAID2|PAID3"),
):
    """
    섭터 + 조건별 진단 가격 자동 판단.

    BUILDING: total_floor_area >= 5000 → 249,000원 / < 5000 → 99,000원
    INDUSTRIAL: tier=PAID1 →79K / PAID2 →149K / PAID3 →249K
    CONSTRUCTION: 199,000원 고정

    인증 불필요 (공개 API).
    """
    sector = normalize_sector_db(sector)
    if sector not in VALID_SECTORS:
        raise HTTPException(status_code=400, detail=f"sector는 {sorted(VALID_SECTORS)} 중 하나여야 합니다")

    sb = get_supabase()

    if sector in ("BUILDING", "SPECIAL_FACILITY"):
        if total_floor_area is None:
            raise HTTPException(status_code=400, detail="BUILDING·SPECIAL_FACILITY 섭터는 total_floor_area(연면적 ㎡)가 필요합니다")

        AREA_THRESHOLD = 5000
        if total_floor_area >= AREA_THRESHOLD:
            code  = "BUILDING_LARGE_V2"
            label = "대형건물 (5,000㎡ 이상)"
        else:
            code  = "BUILDING_V2"
            label = "소형건물 (5,000㎡ 미만)"

        row = sb.table("price_diagnosis_report").select(
            "facility_type_code, facility_type_name, process_fee, total_report_fee"
        ).eq("facility_type_code", code).eq("is_active", True).limit(1).execute()

        if not row.data:
            raise HTTPException(status_code=404, detail=f"{code} 가격 데이터를 찾을 수 없습니다")

        p = row.data[0]
        return {
            "success": True,
            "data": {
                "sector":          sector,
                "determined_type": code,
                "label":           label,
                "free_fee":        0,
                "paid_fee":        int(p["process_fee"] or p["total_report_fee"]),
                "area_threshold":  AREA_THRESHOLD,
                "input_area":      total_floor_area,
            },
        }

    elif sector == "INDUSTRIAL":
        if not tier:
            raise HTTPException(status_code=400, detail="산업(INDUSTRIAL) 섭터는 tier(PAID1|PAID2|PAID3)가 필요합니다")

        tier = tier.upper()
        row = sb.table("price_diagnosis_report").select(
            "facility_type_code, process_fee, equipment_fee, total_report_fee"
        ).eq("facility_type_code", "INDUSTRY_V2").eq("is_active", True).limit(1).execute()

        if not row.data:
            raise HTTPException(status_code=404, detail="INDUSTRY_V2 가격 데이터를 찾을 수 없습니다")

        p = row.data[0]
        TIER_MAP = {
            "PAID1": {"fee": int(p["process_fee"]),   "label": "산업 PAID1 (기준)"},
            "PAID2": {"fee": int(p["equipment_fee"]),  "label": "산업 PAID2 (확장)"},
            "PAID3": {"fee": int(p["total_report_fee"]), "label": "산업 PAID3 (종합)"},
        }
        if tier not in TIER_MAP:
            raise HTTPException(status_code=400, detail="INDUSTRIAL tier는 PAID1|PAID2|PAID3 중 하나여야 합니다")

        t = TIER_MAP[tier]
        return {
            "success": True,
            "data": {
                "sector":          sector,
                "determined_type": f"INDUSTRY_{tier}_V2",
                "label":           t["label"],
                "free_fee":        0,
                "paid_fee":        t["fee"],
                "tier":            tier,
            },
        }

    else:  # CONSTRUCTION
        row = sb.table("price_diagnosis_report").select(
            "facility_type_code, process_fee, total_report_fee"
        ).eq("facility_type_code", "CONSTRUCTION_V2").eq("is_active", True).limit(1).execute()

        if not row.data:
            raise HTTPException(status_code=404, detail="CONSTRUCTION_V2 가격 데이터를 찾을 수 없습니다")

        p = row.data[0]
        return {
            "success": True,
            "data": {
                "sector":          sector,
                "determined_type": "CONSTRUCTION_V2",
                "label":           "건설현장",
                "free_fee":        0,
                "paid_fee":        int(p["process_fee"] or p["total_report_fee"]),
            },
        }


# ── GET /diagnosis/equipment-options (Nexas 동적 폼) ──

@router.get("/equipment-options")
def get_equipment_options():
    """설비 테이블 select 옵션 — system_codes equipment_type / capacity_unit."""
    sb = get_supabase()

    def _load(category: str) -> list:
        try:
            res = (
                sb.table("system_codes")
                .select("code, name_ko, label")
                .eq("category", category)
                .eq("is_active", True)
                .order("sort_order")
                .execute()
            )
        except Exception:
            return []
        out = []
        for row in res.data or []:
            code = row.get("code") or ""
            label = (row.get("name_ko") or row.get("label") or code).strip()
            if code:
                out.append({"code": code, "label": label})
        return out

    equipment_types = _load("equipment_type")
    capacity_units = _load("capacity_unit")
    if not capacity_units:
        capacity_units = [
            {"code": "kW", "label": "kW"},
            {"code": "kg", "label": "kg"},
            {"code": "m3", "label": "m³"},
            {"code": "ton", "label": "톤"},
        ]
    return {
        "status": "success",
        "data": {
            "equipment_types": equipment_types,
            "capacity_units": capacity_units,
        },
    }


# ── GET /diagnosis/process-options (Nexas searchable_select) ──

@router.get("/process-options")
def get_process_options(
    ksic_major: str = Query("", description="KSIC 대분류 문자 (예: C)"),
    ksic_sub: str = Query("", description="KSIC 세부 (예: 25)"),
):
    """KSIC 기반 공정 후보 — ksic_process_map."""
    sb = get_supabase()
    code = f"{(ksic_major or '').strip()}{(ksic_sub or '').strip()}".upper()
    try:
        q = sb.table("ksic_process_map").select(
            "process_id, process_lv1, process_lv2, process_lv4, industry_code_full"
        ).limit(500)
        if code:
            q = q.ilike("industry_code_full", f"{code}%")
        res = q.execute()
    except Exception:
        res = None
    processes = []
    for row in (res.data if res else []) or []:
        name = (row.get("process_lv4") or row.get("process_lv2") or "").strip()
        if not name:
            continue
        processes.append(
            {
                "process_id": row.get("process_id"),
                "process_name": name,
                "process_lv2": row.get("process_lv2") or "",
                "industry_code_full": row.get("industry_code_full") or "",
            }
        )
    return {"status": "success", "data": {"processes": processes}}
