"""운영자 통계 — E 워커 활동 (작업 배정·워커 등록·교육·보고).

실측(2026-08-11, 운영DB): work_assignments 5,329(status 전부 READY·overdue 0·resolved 0),
worker_registry 10 · construction_workers 12 · education_history 9 · worker_attendance 0 ·
safety_reports 2 · emergency_reports 0.
→ 워커 PWA 실이행 데이터가 아직 비어 있음. 운영자 지시에 따라 0 지표도 그대로 표시(구조 선구축).

집계는 stats_dashboard_svc 헬퍼 재사용(Python 집계 · service_role · 페이지네이션).
RPC/마이그레이션 불필요.

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


def get_workers(days: int = 90) -> Dict[str, Any]:
    """워커 활동 현황.

    summary: registered_workers/site_workers, assignments_total/assignments_resolved/assignments_overdue,
             education_total, attendance_total, report_total
    chart:   일별 작업 배정 생성
    by_status: 작업 배정 상태 분포
    """
    days = max(7, min(int(days or 90), 365))
    axis = _date_axis(days)

    assigns = _fetch("work_assignments", "created_at, status_code, overdue_level, resolved_at")

    asg_idx = {d: 0 for d in axis}
    for r in assigns:
        d = _day(r.get("created_at"))
        if d in asg_idx:
            asg_idx[d] += 1

    resolved = sum(1 for r in assigns if r.get("resolved_at"))
    overdue = sum(1 for r in assigns if int(r.get("overdue_level") or 0) > 0)

    return {
        "range_days": days,
        "generated_at": _now(),
        "summary": {
            "registered_workers": _count("worker_registry"),
            "site_workers": _count("construction_workers"),
            "assignments_total": len(assigns),
            "assignments_resolved": resolved,
            "assignments_overdue": overdue,
            "education_total": _count("education_history"),
            "attendance_total": _count("worker_attendance"),
            "report_total": _count("safety_reports") + _count("emergency_reports"),
        },
        "chart": [{"date": d, "assignments": asg_idx[d]} for d in axis],
        "by_status": _breakdown(assigns, "status_code"),
    }
