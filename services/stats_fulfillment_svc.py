"""운영자 통계 — D 서비스 이행 (문서 생성·점검셋·작업배정 백로그).

실측(2026-08-11, 운영DB vwlahtguyggrhvslabax):
- generated_document 1,543 (status: PENDING 1,526 · GENERATED 9 · TEMPLATE_MISSING 4 · FAILED 4; export 전부 PDF; 2026-05-14~08-01)
- inspection_sets 327 (status_code: PENDING_ANCHOR 268 · ACTIVE 58 · UPCOMING 1)
- work_assignments 5,329 (status_code 전부 READY · overdue 0 · resolved 0 = 미실행 백로그)
- risk_assessments 11
→ 이행 파이프라인이 대부분 '대기' 단계라는 실지표(문서 생성완료 9 · 점검셋 anchor 미확정 268).

집계는 stats_dashboard_svc 헬퍼 재사용(Python 집계 · service_role · 페이지네이션).
대상 소량이라 since 없이 전체 조회 후 Python 에서 기간 필터. RPC/마이그레이션 불필요.

Goal: G-msod7sao-b904a6
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from services.stats_dashboard_svc import (
    _breakdown,
    _count,
    _date_axis,
    _day,
    _fetch,
)
from services.time import now_kst, serialize_external_utc


def _now() -> str:
    return serialize_external_utc(now_kst())


def get_fulfillment(days: int = 90) -> Dict[str, Any]:
    """서비스 이행 현황.

    summary: docs_total/docs_generated, sets_total/sets_active, assignments_total, risk_total
    chart:   일별 문서 생성/배정 생성
    by_doc_status: 문서 상태 분포, by_set_status: 점검셋 상태 분포
    """
    days = max(7, min(int(days or 90), 365))
    axis = _date_axis(days)

    docs = _fetch("generated_document", "created_at, status")
    sets = _fetch("inspection_sets", "created_at, status_code")
    assigns = _fetch("work_assignments", "created_at, status_code")

    def daily(rows):
        idx = {d: 0 for d in axis}
        for r in rows:
            d = _day(r.get("created_at"))
            if d in idx:
                idx[d] += 1
        return idx

    doc_idx = daily(docs)
    asg_idx = daily(assigns)

    docs_generated = sum(1 for r in docs if r.get("status") == "GENERATED")
    sets_active = sum(1 for r in sets if r.get("status_code") == "ACTIVE")
    risk_total = _count("risk_assessments")

    return {
        "range_days": days,
        "generated_at": _now(),
        "summary": {
            "docs_total": len(docs),
            "docs_generated": docs_generated,
            "sets_total": len(sets),
            "sets_active": sets_active,
            "assignments_total": len(assigns),
            "risk_total": risk_total,
        },
        "chart": [{"date": d, "documents": doc_idx[d], "assignments": asg_idx[d]} for d in axis],
        "by_doc_status": _breakdown(docs, "status"),
        "by_set_status": _breakdown(sets, "status_code"),
    }
