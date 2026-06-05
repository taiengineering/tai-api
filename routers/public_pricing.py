# routers/public_pricing.py — 공개 가격 API (인증 불필요)
# v3.0.0 (2026-06-05): price_master 단일 테이블로 통합. price_saas_plan/price_diagnosis_report 직접 참조 제거.
#   - 데이터 소스: price_master + price_service_feature (SSOT)
#   - 기존 응답 키(saas_plans/diagnosis_plans, features 등) 호환 유지
#   - 신규: GET /public/pricing/resolve — 기준값(연면적/근로자수/공사금액)으로 플랜 자동 산정
# v2.0.0 (2026-05-16): features/target/is_recommended/is_custom 필드 추가
# v1.1.0 (2026-04-14): /saas-plans + /diagnosis-reports 추가
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


# ── price_master 조회 + feature 조인 ──────────────────────────

MASTER_FIELDS = (
    "id, service_type, sector, tier_code, criteria_type, criteria_min, criteria_max,"
    "amount, vat_included, vat_rate, billing_unit, display_name, sub_label, icon,"
    "is_recommended, is_active, sort_order"
)


def _load(service_type: str, sector: str = None):
    """price_master에서 service_type(+sector) 활성 행을 features와 함께 로드."""
    sb = get_supabase()
    q = (
        sb.table("price_master")
        .select(MASTER_FIELDS)
        .eq("service_type", service_type)
        .eq("is_active", True)
    )
    if sector:
        q = q.eq("sector", sector.upper())
    rows = q.order("sort_order").execute().data or []

    ids = [r["id"] for r in rows]
    feat_map: dict = {}
    if ids:
        feats = (
            sb.table("price_service_feature")
            .select("price_id, feature_text, feature_type, icon, sort_order, is_active")
            .in_("price_id", ids)
            .eq("is_active", True)
            .order("sort_order")
            .execute()
            .data or []
        )
        for f in feats:
            feat_map.setdefault(f["price_id"], []).append(f["feature_text"])

    for r in rows:
        r["features"] = feat_map.get(r["id"], [])
    return rows


# ══════════════════════════════════════════════════════════════
# SaaS Plans
# ══════════════════════════════════════════════════════════════

@router.get("/saas-plans")
def get_saas_plans(sector: str = None):
    """SaaS 구독 플랜 목록 (price_master service_type=SAAS, 인증 불필요)."""
    cache_key = f"saas_plans_v3:{sector or 'ALL'}"
    cached = _get_cached(cache_key)
    if cached:
        return {"data": cached}
    data = _load("SAAS", sector)
    _set_cache(cache_key, data)
    return {"data": data}


# ══════════════════════════════════════════════════════════════
# Diagnosis Reports
# ══════════════════════════════════════════════════════════════

@router.get("/diagnosis-reports")
def get_diagnosis_reports(sector: str = None):
    """법령진단 단건 가격 목록 (price_master service_type=DIAGNOSIS, 인증 불필요)."""
    cache_key = f"diagnosis_reports_v3:{sector or 'ALL'}"
    cached = _get_cached(cache_key)
    if cached:
        return {"data": cached}
    data = _load("DIAGNOSIS", sector)
    _set_cache(cache_key, data)
    return {"data": data}


# ══════════════════════════════════════════════════════════════
# 통합 (pricing.html 원스톱)
# ══════════════════════════════════════════════════════════════

@router.get("/all")
def public_all_pricing(sector: str = None):
    """pricing.html에서 사용. SaaS + 법령진단 가격 동시 반환."""
    cache_key = f"all_v3:{sector or 'ALL'}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return {"status": "success", "cached": True, **cached}
    payload = {
        "saas_plans": _load("SAAS", sector),
        "diagnosis_plans": _load("DIAGNOSIS", sector),
    }
    _set_cache(cache_key, payload)
    return {"status": "success", "cached": False, **payload}


# ══════════════════════════════════════════════════════════════
# 가격 자동 산정 (기준값 → 플랜)
# ══════════════════════════════════════════════════════════════

@router.get("/resolve")
def resolve_price(service_type: str, sector: str, value: float = None):
    """기준값으로 적용 플랜을 산정.
    - service_type: DIAGNOSIS / SAAS
    - sector: BUILDING(연면적) / INDUSTRY(근로자수) / CONSTRUCTION(공사금액)
    - value: 기준값. criteria_min <= value < criteria_max 인 행을 반환(FLAT은 value 무관).
    """
    rows = _load(service_type.upper(), sector.upper())
    if not rows:
        return {"status": "not_found", "data": None}

    if value is None:
        # 기준값 미입력 → 추천 우선, 없으면 첫 행
        chosen = next((r for r in rows if r.get("is_recommended")), rows[0])
        return {"status": "success", "data": chosen, "matched_by": "default"}

    match = None
    for r in rows:
        cmin = r.get("criteria_min")
        cmax = r.get("criteria_max")
        lo_ok = cmin is None or value >= float(cmin)
        hi_ok = cmax is None or value < float(cmax)
        if r.get("criteria_type") == "FLAT":
            continue
        if lo_ok and hi_ok:
            match = r
            break
    if match is None:
        # 구간 초과 시 FLAT(맞춤) 또는 마지막 행
        match = next((r for r in rows if r.get("criteria_type") == "FLAT"), rows[-1])
    return {"status": "success", "data": match, "matched_by": "criteria"}


# ── 레거시 호환 ──────────────────────────────────────────────

@router.get("/saas")
def public_saas_pricing(sector: str = None):
    """레거시 — /saas-plans 사용 권장."""
    return get_saas_plans(sector)


@router.get("/diagnosis")
def public_diagnosis_pricing(sector: str = None):
    """레거시 — /diagnosis-reports 사용 권장."""
    return get_diagnosis_reports(sector)


@router.delete("/cache")
def clear_pricing_cache():
    """가격 변경 후 캐시 수동 초기화 (관리자용)."""
    _cache.clear()
    return {"status": "success", "message": "가격 캐시가 초기화되었습니다"}
