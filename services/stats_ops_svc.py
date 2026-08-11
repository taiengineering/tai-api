"""운영자 통계 — 신규 설계 서비스 (기존 부실 /stats/dashboard 대체 계열).

영역: A 진단 퍼널 / C 고객사·사업장 / B 매출·결제 / D 서비스 이행 / E 워커 활동 / 운영개요.
집계 방식은 stats_dashboard_svc 와 동일: Python 집계 · supabase service_role · 페이지네이션.
RPC/마이그레이션/운영자 적용 불필요 — push 시 자동배포.

기존 부실 지점 해결:
- 퍼널: 테스트/엔진 트래픽(factory_test·runtime_compiler_projection) = 실제 리드에서 분리.
- 기간 필터: summary·chart 모두 days 범위 반영(기존은 전 기간 합계 혼재).
- 고객 분포: 업종 라벨 대소문자 불일치 정규화(building/BUILDING→건축물 등), companies 기준
  (factories 는 분석축 미충전이라 등록수/추이만).

Goal: G-msod7sao-b904a6
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from services.stats_dashboard_svc import (
    _breakdown,
    _date_axis,
    _day,
    _fetch,
    _since_iso,
)

# 실측 검증(2026-08-11): factory_test 5,624 · runtime_compiler_projection 2 = 테스트/엔진 트래픽.
TEST_SOURCES = {"factory_test", "runtime_compiler_projection"}

# 업종 라벨 정규화 — 실측 distinct: building/BUILDING, construction/CONSTRUCTION, manufacturing,
# service, logistics, INDUSTRY. lower(trim) 로 대소문자 병합 후 한글 라벨 매핑.
SECTOR_LABELS = {
    "building": "건축물",
    "construction": "건설",
    "manufacturing": "제조",
    "service": "서비스",
    "logistics": "물류",
    "industry": "산업",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm_sector(raw: str) -> str:
    s = (raw or "").strip().lower()
    return SECTOR_LABELS.get(s, (raw or "").strip() or "(미지정)")


# ── A. 진단 퍼널 ─────────────────────────────────────────────────────
def get_funnel(days: int = 90) -> Dict[str, Any]:
    """익명진단(실제/테스트 분리) → 공개요청 → 유료전환 퍼널.

    summary: anon_total/anon_real/anon_test/paid_total/pub_total/pub_pending/conv_rate
    chart:   일별 익명진단 total/real
    by_source: 유입 경로별, pub_status: 공개요청 상태별
    """
    days = max(7, min(int(days or 90), 365))
    axis = _date_axis(days)
    since = _since_iso(days)

    anon = _fetch("anonymous_diagnosis_results", "created_at, source_type, paid_amount", since=since)
    pub = _fetch("public_diagnosis_requests", "created_at, status_code", since=since)

    total_idx = {d: 0 for d in axis}
    real_idx = {d: 0 for d in axis}
    anon_real = anon_test = paid_total = 0
    for r in anon:
        is_real = r.get("source_type") not in TEST_SOURCES
        if is_real:
            anon_real += 1
        else:
            anon_test += 1
        if int(r.get("paid_amount") or 0) > 0:
            paid_total += 1
        d = _day(r.get("created_at"))
        if d in total_idx:
            total_idx[d] += 1
            if is_real:
                real_idx[d] += 1

    anon_total = len(anon)
    pub_total = len(pub)
    pub_pending = sum(1 for r in pub if r.get("status_code") == "NEW")
    conv_rate = round(paid_total * 100 / anon_real, 2) if anon_real else 0

    return {
        "range_days": days,
        "generated_at": _now(),
        "summary": {
            "anon_total": anon_total,
            "anon_real": anon_real,
            "anon_test": anon_test,
            "paid_total": paid_total,
            "pub_total": pub_total,
            "pub_pending": pub_pending,
            "conv_rate": conv_rate,
        },
        "chart": [{"date": d, "total": total_idx[d], "real": real_idx[d]} for d in axis],
        "by_source": _breakdown(anon, "source_type"),
        "pub_status": _breakdown(pub, "status_code"),
    }


# ── C. 고객사·사업장 ─────────────────────────────────────────────────
def get_customers(days: int = 90) -> Dict[str, Any]:
    """고객사(회사)·사업장(시설) 현황.

    summary:  companies_total/factories_total(자산 총계) + new_companies/new_factories(기간 신규)
    chart:    일별 신규 등록(회사/시설)
    by_sector: 업종 분포(라벨 정규화), by_region: 지역(시도) 분포, by_size: 직원수 구간 분포
              — 전부 companies 기준(factories 는 분석축 미충전).
    """
    days = max(7, min(int(days or 90), 365))
    axis = _date_axis(days)

    companies_all = _fetch("companies", "created_at, deleted_at, business_sector, address_sido, employee_count")
    companies = [c for c in companies_all if not c.get("deleted_at")]
    factories_all = _fetch("factories", "created_at, deleted_at")
    factories = [f for f in factories_all if not f.get("deleted_at")]

    co_idx = {d: 0 for d in axis}
    fa_idx = {d: 0 for d in axis}
    for c in companies:
        d = _day(c.get("created_at"))
        if d in co_idx:
            co_idx[d] += 1
    for f in factories:
        d = _day(f.get("created_at"))
        if d in fa_idx:
            fa_idx[d] += 1

    # 업종 분포(정규화)
    sector: Dict[str, int] = {}
    for c in companies:
        bs = c.get("business_sector")
        if not bs:
            continue
        lbl = _norm_sector(bs)
        sector[lbl] = sector.get(lbl, 0) + 1
    by_sector = sorted(
        [{"label": k, "count": v} for k, v in sector.items()],
        key=lambda x: x["count"], reverse=True,
    )[:10]

    # 지역 분포
    region: Dict[str, int] = {}
    for c in companies:
        sd = c.get("address_sido")
        if not sd:
            continue
        region[sd] = region.get(sd, 0) + 1
    by_region = sorted(
        [{"label": k, "count": v} for k, v in region.items()],
        key=lambda x: x["count"], reverse=True,
    )[:15]

    # 규모(직원수) 분포
    order = ["5인 미만", "5-49인", "50-299인", "300인 이상", "미상"]
    size = {k: 0 for k in order}
    for c in companies:
        e = int(c.get("employee_count") or 0)
        if e <= 0:
            k = "미상"
        elif e < 5:
            k = "5인 미만"
        elif e < 50:
            k = "5-49인"
        elif e < 300:
            k = "50-299인"
        else:
            k = "300인 이상"
        size[k] += 1
    by_size = [{"label": k, "count": size[k]} for k in order]

    return {
        "range_days": days,
        "generated_at": _now(),
        "summary": {
            "companies_total": len(companies),
            "factories_total": len(factories),
            "new_companies": sum(co_idx.values()),
            "new_factories": sum(fa_idx.values()),
        },
        "chart": [{"date": d, "companies": co_idx[d], "factories": fa_idx[d]} for d in axis],
        "by_sector": by_sector,
        "by_region": by_region,
        "by_size": by_size,
    }
