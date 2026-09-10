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
from services import pricing_resolver_svc

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


# ── price_master 조회 (캐시 래퍼 — 조회 본문은 pricing_resolver_svc) ──

def _load(service_type: str, sector: str = None):
    """price_master에서 service_type(+sector) 활성 행을 features와 함께 로드."""
    return pricing_resolver_svc.load_prices(get_supabase(), service_type, sector)


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
    return pricing_resolver_svc.resolve_plan(get_supabase(), service_type, sector, value)


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
