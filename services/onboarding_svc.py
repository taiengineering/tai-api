"""온보딩 체크리스트 서비스 (WO-17 OnboardingChecklist).

Goal: G-ms4je4z3-33eada
- 신규 회사의 서비스 시작 단계를 기존 데이터로 파생 판정(신설 테이블 없음).
- 4단계: 회사정보 → 사업장 등록 → 법령진단 → 구독 시작.
- 엔진/런타임 체크리스트 테이블(격리)은 미사용.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from db.supabase_client import get_supabase

log = logging.getLogger(__name__)

# 온보딩 4단계 정의
STEPS = [
    {"key": "company_info", "label": "회사정보 등록"},
    {"key": "factory_added", "label": "사업장 등록"},
    {"key": "diagnosis_done", "label": "법령진단"},
    {"key": "subscription_active", "label": "구독 시작"},
]


def _company_info_done(company: Dict[str, Any]) -> bool:
    return bool(company.get("name")) and bool(company.get("business_number"))


def get_checklist(company_id: str) -> Dict[str, Any]:
    """회사 온보딩 4단계 파생 판정."""
    supabase = get_supabase()

    # 1. 회사정보
    comp = (
        supabase.table("companies").select("id, name, business_number")
        .eq("id", company_id).is_("deleted_at", "null").limit(1).execute()
    )
    if not comp.data:
        return {"error": "회사를 찾을 수 없습니다.", "company_id": company_id}
    company = comp.data[0]
    company_info = _company_info_done(company)

    # 2. 사업장 등록 여부 + 3. 진단 여부(사업장 diagnosis_status)
    facs = (
        supabase.table("factories").select("id, diagnosis_status, last_diagnosis_at")
        .eq("company_id", company_id).is_("deleted_at", "null").execute()
    ).data or []
    factory_added = len(facs) > 0
    diagnosis_done = any(
        (f.get("diagnosis_status") and f["diagnosis_status"] != "NONE")
        or f.get("last_diagnosis_at")
        for f in facs
    )

    # 4. 구독 시작(ACTIVE)
    subs = (
        supabase.table("subscriptions").select("id, status")
        .eq("company_id", company_id).eq("status", "ACTIVE").limit(1).execute()
    ).data or []
    subscription_active = len(subs) > 0

    status_map = {
        "company_info": company_info,
        "factory_added": factory_added,
        "diagnosis_done": diagnosis_done,
        "subscription_active": subscription_active,
    }

    items = []
    next_step = None
    for step in STEPS:
        done = status_map[step["key"]]
        items.append({"key": step["key"], "label": step["label"], "done": done})
        if not done and next_step is None:
            next_step = {"key": step["key"], "label": step["label"]}

    completed = sum(1 for v in status_map.values() if v)
    total = len(STEPS)
    return {
        "company_id": company_id,
        "items": items,
        "completed": completed,
        "total": total,
        "progress_pct": round(completed / total * 100),
        "next_step": next_step,
        "is_complete": completed == total,
    }
