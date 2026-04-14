# routers/public_pricing.py — 공개 가격 API (인증 불필요)
# v1.0.0 (2026-04-14): 신규 — 5분 캐시, CORS 허용
import time
from functools import lru_cache
from fastapi import APIRouter
from fastapi.middleware.cors import CORSMiddleware
from db.database import get_supabase

router = APIRouter(prefix="/public/pricing", tags=["공개 가격"])

# ── 5분 캐시 ──────────────────────────────────────────────────
_cache: dict = {}
CACHE_TTL = 300  # 5분


def _get_cached(key: str):
    entry = _cache.get(key)
    if entry and (time.time() - entry["ts"]) < CACHE_TTL:
        return entry["data"]
    return None


def _set_cache(key: str, data):
    _cache[key] = {"ts": time.time(), "data": data}


# ── SaaS 요금제 공개 API ─────────────────────────────────────

@router.get("/saas")
def public_saas_pricing(sector: str = None):
    """
    공개 SaaS 요금제 조회.
    sector: BUILDING | INDUSTRY | CONSTRUCTION (없으면 전체)
    """
    cache_key = f"saas:{sector or 'ALL'}"
    cached = _get_cached(cache_key)
    if cached:
        return {"status": "success", "cached": True, "data": cached}

    sb = get_supabase()
    q = sb.table("price_saas_plan").select(
        "plan_code, plan_name, display_name, description, sector_code,"
        "monthly_base_fee, annual_base_fee, annual_discount_rate, annual_free_months,"
        "included_users, extra_user_fee_v2, max_sites,"
        "include_task_assign, include_group_mgmt, include_miss_alert,"
        "include_law_alert, include_api_v2, include_safety_content, include_dashboard,"
        "badge_color, sort_order"
    ).eq("is_active", True)

    # 섹터별 필터: STARTER/PREMIUM/ENTERPRISE 코드만
    if sector:
        q = q.eq("sector_code", sector.upper()).in_(
            "plan_code",
            [f"{sector.upper()}_STARTER", f"{sector.upper()}_PREMIUM", f"{sector.upper()}_ENTERPRISE"]
        )
    else:
        # 공개 노출은 섹터별 신규 플랜만
        q = q.in_("sector_code", ["BUILDING", "INDUSTRY", "CONSTRUCTION"])

    res = q.order("sort_order").execute()
    data = res.data or []
    _set_cache(cache_key, data)
    return {"status": "success", "cached": False, "data": data}


# ── 법령진단 가격 공개 API ───────────────────────────────────

@router.get("/diagnosis")
def public_diagnosis_pricing():
    """
    공개 법령진단 요금 조회 (V2 — 건물/산업/건설 3종).
    """
    cached = _get_cached("diagnosis:v2")
    if cached:
        return {"status": "success", "cached": True, "data": cached}

    sb = get_supabase()
    res = sb.table("price_diagnosis_report").select(
        "facility_type_code, facility_type_name, sector_display,"
        "free_fee, total_report_fee, inquiry_label, price_version, sort_order"
    ).eq("is_active", True).eq("price_version", "v2").order("sort_order").execute()

    data = res.data or []
    _set_cache("diagnosis:v2", data)
    return {"status": "success", "cached": False, "data": data}


# ── 전체 가격 (SaaS + 진단) 한번에 ───────────────────────────

@router.get("/all")
def public_all_pricing(sector: str = None):
    """
    pricing.html에서 사용. SaaS + 법령진단 가격 동시 반환.
    """
    cached = _get_cached(f"all:{sector or 'ALL'}")
    if cached:
        return {"status": "success", "cached": True, **cached}

    sb = get_supabase()

    # SaaS
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

    # 진단
    diag = sb.table("price_diagnosis_report").select(
        "facility_type_code, facility_type_name, sector_display,"
        "free_fee, total_report_fee, inquiry_label, sort_order"
    ).eq("is_active", True).eq("price_version", "v2").order("sort_order").execute().data or []

    payload = {"saas_plans": saas, "diagnosis_plans": diag}
    _set_cache(f"all:{sector or 'ALL'}", payload)
    return {"status": "success", "cached": False, **payload}


# ── 캐시 초기화 (관리자용) ───────────────────────────────────

@router.delete("/cache")
def clear_pricing_cache():
    """관리자가 가격 변경 후 캐시를 수동으로 초기화합니다."""
    _cache.clear()
    return {"status": "success", "message": "가격 캐시가 초기화되었습니다"}
