# routers/public_pricing.py — 공개 가격 API (인증 불필요)
# v2.0.0 (2026-05-16): features/target/is_recommended/is_custom 필드 추가, 프론트 완전 연동
# v1.1.0 (2026-04-14): /saas-plans + /diagnosis-reports 엔드포인트 추가
import time
from fastapi import APIRouter
from db.supabase_client import get_supabase

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


# ══════════════════════════════════════════════════════════════
# SaaS Plans
# ══════════════════════════════════════════════════════════════

SAAS_FIELDS = (
    "id, plan_code, plan_name, display_name, description, sector_code, billing_unit,"
    "monthly_base_fee, annual_discount_rate, included_users, extra_user_fee_v2,"
    "sms_included, kakao_included, doc_included, include_tbm,"
    "include_task_assign, include_group_mgmt, include_miss_alert,"
    "include_safety_content, include_dashboard, annual_free_months,"
    "badge_color, sort_order, is_active, target, features, is_recommended, is_custom"
)


@router.get("/saas-plans")
def get_saas_plans(sector: str = None):
    """SaaS 구독 플랜 목록 (is_active=true, 인증 불필요)."""
    cache_key = f"saas_plans_v2:{sector or 'ALL'}"
    cached = _get_cached(cache_key)
    if cached:
        return {"data": cached}

    sb = get_supabase()
    q = sb.table("price_saas_plan").select(SAAS_FIELDS).eq("is_active", True)
    if sector:
        q = q.eq("sector_code", sector.upper())
    res = q.order("sort_order").execute()
    data = res.data or []
    _set_cache(cache_key, data)
    return {"data": data}


# ══════════════════════════════════════════════════════════════
# Diagnosis Reports
# ══════════════════════════════════════════════════════════════

DIAG_FIELDS = (
    "id, facility_type_code, facility_type_name, sector_display,"
    "basic_fee, process_fee, equipment_fee, total_report_fee,"
    "free_fee, inquiry_label, price_version, sort_order, is_active,"
    "features, icon, goods_name, is_recommended, is_special, sub_label"
)


@router.get("/diagnosis-reports")
def get_diagnosis_reports():
    """법령진단 리포트 단건 가격 목록 (is_active=true, 인증 불필요)."""
    cached = _get_cached("diagnosis_reports_v2")
    if cached:
        return {"data": cached}

    sb = get_supabase()
    res = (
        sb.table("price_diagnosis_report")
        .select(DIAG_FIELDS)
        .eq("is_active", True)
        .eq("price_version", "v2")
        .order("sort_order")
        .execute()
    )
    data = res.data or []
    _set_cache("diagnosis_reports_v2", data)
    return {"data": data}


# ══════════════════════════════════════════════════════════════
# 통합 (pricing.html 원스톱)
# ══════════════════════════════════════════════════════════════

@router.get("/all")
def public_all_pricing(sector: str = None):
    """pricing.html에서 사용. SaaS + 법령진단 가격 동시 반환."""
    cached = _get_cached(f"all_v2:{sector or 'ALL'}")
    if cached is not None:
        return {"status": "success", "cached": True, **cached}

    sb = get_supabase()

    saas_q = sb.table("price_saas_plan").select(SAAS_FIELDS).eq("is_active", True)
    if sector:
        saas_q = saas_q.eq("sector_code", sector.upper())
    saas = saas_q.order("sort_order").execute().data or []

    diag = (
        sb.table("price_diagnosis_report")
        .select(DIAG_FIELDS)
        .eq("is_active", True)
        .eq("price_version", "v2")
        .order("sort_order")
        .execute()
        .data or []
    )

    payload = {"saas_plans": saas, "diagnosis_plans": diag}
    _set_cache(f"all_v2:{sector or 'ALL'}", payload)
    return {"status": "success", "cached": False, **payload}


# ── 레거시 호환 ──────────────────────────────────────────────

@router.get("/saas")
def public_saas_pricing(sector: str = None):
    """레거시 — /saas-plans 사용 권장."""
    return get_saas_plans(sector)


@router.get("/diagnosis")
def public_diagnosis_pricing():
    """레거시 — /diagnosis-reports 사용 권장."""
    return get_diagnosis_reports()


@router.delete("/cache")
def clear_pricing_cache():
    """가격 변경 후 캐시 수동 초기화 (관리자용)."""
    _cache.clear()
    return {"status": "success", "message": "가격 캐시가 초기화되었습니다"}
