"""운영자 통계 — 운영개요 (각 영역 헤드라인 집약).

A 진단 퍼널 / C 고객사·사업장 / B 매출·결제 / D 서비스 이행 / E 워커 활동 의
summary 를 모아 대표 KPI + 대표 추이(퍼널·매출)를 제공. 각 영역 서비스 재사용.
집계 자체는 각 영역과 동일(Python · service_role). RPC/마이그레이션 불필요.

Goal: G-msod7sao-b904a6
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from services.stats_fulfillment_svc import get_fulfillment
from services.stats_ops_svc import get_customers, get_funnel, get_revenue
from services.stats_workers_svc import get_workers


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_overview(days: int = 90) -> Dict[str, Any]:
    """운영개요 — 5개 영역 헤드라인 + 대표 추이(퍼널·매출)."""
    days = max(7, min(int(days or 90), 365))

    f = get_funnel(days)
    c = get_customers(days)
    r = get_revenue(days)
    d = get_fulfillment(days)
    w = get_workers(days)

    kpis = [
        {"area": "진단", "label": "실제 익명진단", "value": f["summary"]["anon_real"]},
        {"area": "진단", "label": "유료 전환", "value": f["summary"]["paid_total"]},
        {"area": "고객", "label": "고객사", "value": c["summary"]["companies_total"]},
        {"area": "고객", "label": "사업장", "value": c["summary"]["factories_total"]},
        {"area": "매출", "label": "완료 매출", "value": r["summary"]["completed_amount"], "money": True},
        {"area": "매출", "label": "완료 건수", "value": r["summary"]["completed_count"]},
        {"area": "이행", "label": "생성 문서", "value": d["summary"]["docs_total"]},
        {"area": "이행", "label": "점검셋", "value": d["summary"]["sets_total"]},
        {"area": "워커", "label": "작업 배정", "value": w["summary"]["assignments_total"]},
        {"area": "워커", "label": "등록 워커", "value": w["summary"]["registered_workers"]},
    ]

    return {
        "range_days": days,
        "generated_at": _now(),
        "kpis": kpis,
        "funnel_chart": f["chart"],
        "revenue_chart": r["chart"],
        "sections": {
            "funnel": f["summary"],
            "customers": c["summary"],
            "revenue": r["summary"],
            "fulfillment": d["summary"],
            "workers": w["summary"],
        },
    }
