# routers/public_pricing.py — 공개 가격 API (인증 불필요)
# v1.1.0 (2026-04-14): /saas-plans, /diagnosis-reports 추가 (pricing.js v2 호환)
# v1.0.0 (2026-04-14): 신규 — 5분 캐시
import time
from fastapi import APIRouter
from db.database import get_supabase

router = APIRouter(prefix="/public/pricing", tags=["공개 가격"])

# ── 5분 인메모리 캐시 ─────────────────────────────────────────
_cache: dict = {}
CACHE_TTL = 300


def _get_cached(key: str):
    entry = _cache.get(key)
    if entry and (time.time() - entry["ts"]) < CACHE_TTL:
        return entry["data"]
    return None


def _set_cache(key: str, data):
    _cache[key] = {"ts": time.time(), "data": data}


# ════════════════════════════════════════════════════════════════
# v2 엔드포인트 — pricing.js v2 호환 (새 URL)
# ════════════════════════════════════════════════════════════════

@router.get("/saas-plans")
def get_saas_plans():
    """
    SaaS 플랜 가격 목록 (pricing.js v2 호환).
    반환 필드: plan_code, monthly_base_fee, sector_code
    sector_code: BUILDING / INDUSTRY / CONSTRUCTION
    """
    cached = _get_cached("saas-plans")
    if cached is not None:
        return {"success": True, "cached": True, "data": cached}

    sb = get_supabase()
    res = sb.table("price_saas_plan").select(
        "plan_code, display_name, sector_code, monthly_base_fee, is_active, sort_order"
    ).eq("is_active", True).in_(
        "sector_code", ["BUILDING", "INDUSTRY", "CONSTRUCTION"]
    ).order("sort_order").execute()

    data = res.data or []
    _set_cache("saas-plans", data)
    return {"success": True, "cached": False, "data": data}


@router.get("/diagnosis-reports")
def get_diagnosis_reports():
    """
    법령진단 단건 가격 목록 (pricing.js v2 호환).
    반환 필드: facility_type_code, basic_fee, equipment_fee, total_report_fee
    facility_type_code: BUILDING_V2 / INDUSTRY_V2 / CONSTRUCTION_V2
    """
    cached = _get_cached("diagnosis-reports")
    if cached is not None:
        return {"success": True, "cached": True, "data": cached}

    sb = get_supabase()
    res = sb.table("price_diagnosis_report").select(
        "facility_type_code, facility_type_name, "
        "basic_fee, process_fee, equipment_fee, total_report_fee, "
        "free_fee, is_active, price_version, sort_order"
    ).eq("is_active", True).eq("price_version", "v2").order("sort_order").execute()

    data = res.data or []
    _set_cache("diagnosis-reports", data)
    return {"success": True, "cached": False, "data": data}


# ════════════════════════════════════════════════════════════════
# 기존 엔드포인트 (하위 호환 유지)
# ════════════════════════════════════════════════════════════════

@router.get("/saas")
def public_saas_pricing(sector: str = None):
    """공개 SaaS 요금제 조회 (레거시 — /saas-plans 사용 권장)."""
    cache_key = f"saas:{sector or 'ALL'}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return {"status": "success", "cached": True, "data": cached}

    sb = get_supabase()
    q = sb.table("price_saas_plan").select(
        "plan_code, plan_name, display_name, description, sector_code,"
        "monthly_base_fee, annual_base_fee, annual_discount_rate, annual_free_months,"
        "included_users, extra_user_fee_v2, max_sites,"
        "include_task_assign, include_group_mgmt, include_miss_alert,"
        "include_law_alert, include_api_v2, include_safety_content, include_dashboard,"
        "badge_color, sort_order"
    ).eq("is_active", True).in_("sector_code", ["BUILDING", "INDUSTRY", "CONSTRUCTION"])

    if sector:
        q = q.eq("sector_code", sector.upper())

    res = q.order("sort_order").execute()
    data = res.data or []
    _set_cache(cache_key, data)
    return {"status": "success", "cached": False, "data": data}


@router.get("/diagnosis")
def public_diagnosis_pricing():
    """공개 법령진단 요금 조회 (레거시 — /diagnosis-reports 사용 권장)."""
    cached = _get_cached("diagnosis:v2")
    if cached is not None:
        return {"status": "success", "cached": True, "data": cached}

    sb = get_supabase()
    res = sb.table("price_diagnosis_report").select(
        "facility_type_code, facility_type_name, sector_display,"
        "free_fee, basic_fee, equipment_fee, total_report_fee,"
        "inquiry_label, price_version, sort_order"
    ).eq("is_active", True).eq("price_version", "v2").order("sort_order").execute()

    data = res.data or []
    _set_cache("diagnosis:v2", data)
    return {"status": "success", "cached": False, "data": data}


@router.get("/all")
def public_all_pricing(sector: str = None):
    """SaaS + 법령진단 가격 동시 반환."""
    cached = _get_cached(f"all:{sector or 'ALL'}")
    if cached is not None:
        return {"status": "success", "cached": True, **cached}

    sb = get_supabase()

    saas_q = sb.table("price_saas_plan").select(
        "plan_code, display_name, description, sector_code,"
        "monthly_base_fee, annual_base_fee, annual_free_months,"
        "included_users, extra_user_fee_v2,"
        "include_task_assign, include_group_mgmt, include_miss_alert,"
        "include_law_alert, include_api_v2, badge_color, sort_order"
    ).eq("is_active", True).in_("sector_code", ["BUILDING", "INDUSTRY", "CONSTRUCTION"])
    if sector:
        saas_q = saas_q.eq("sector_code", sector.upper())
    saas = saas_q.order("sort_order").execute().data or []

    diag = sb.table("price_diagnosis_report").select(
        "facility_type_code, facility_type_name, sector_display,"
        "free_fee, basic_fee, equipment_fee, total_report_fee,"
        "inquiry_label, sort_order"
    ).eq("is_active", True).eq("price_version", "v2").order("sort_order").execute().data or []

    payload = {"saas_plans": saas, "diagnosis_plans": diag}
    _set_cache(f"all:{sector or 'ALL'}", payload)
    return {"status": "success", "cached": False, **payload}


@router.delete("/cache")
def clear_pricing_cache():
    """가격 변경 후 캐시 수동 초기화 (관리자용)."""
    _cache.clear()
    return {"status": "success", "message": "가격 캐시가 초기화되었습니다"}
