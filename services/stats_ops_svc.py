"""운영자 통계 — 신규 설계 서비스 (기존 부실 /stats/dashboard 대체 계열).

영역: A 진단 퍼널 / C 고객사·사업장 / B 매출·결제 / D 서비스 이행 / E 워커 활동 / 운영개요.
집계 방식은 stats_dashboard_svc 와 동일: Python 집계 · supabase service_role · 페이지네이션.
RPC/마이그레이션/운영자 적용 불필요 — push 시 자동배포.

기존 부실 지점 해결:
- 퍼널: 테스트/엔진 트래픽(factory_test·runtime_compiler_projection) = 실제 리드에서 분리.
- 기간 필터: summary·chart 모두 days 범위 반영(기존은 전 기간 합계 혼재).

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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
