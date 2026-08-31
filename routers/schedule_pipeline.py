"""
진단→일정 자동생성 + D-7/D-3/당일 알림 파이프 — v1.1.0
============================================================
v1.1.0 (2026-04-09) Pipeline Priority 1:
  [FIX] trigger-due-alerts: assigned_user_id IS NOT NULL 필터 추가
        담당자 없는 일정(inspection_sets 4조건 미충족으로 생성된 스케줄 등)에
        알림을 발송하지 않음

v1.0.0 (2026-04-07):
  POST /legal-engine/generate-schedules/{factory_id}
      factory_diagnosis_results(is_latest) → work_schedules 자동 INSERT
  POST /notifications/trigger-due-alerts
      D-7/D-3/D-0 기준 마감 알림 생성
"""
from fastapi import APIRouter, HTTPException
from datetime import date, datetime, timedelta
from typing import Optional

from db.supabase_client import get_supabase
from services.time import business_today, now_kst

router = APIRouter(tags=["일정파이프"])


def _cycle_to_days(cycle_unit: str, cycle_int: int) -> int:
    u = (cycle_unit or "").lower()
    n = max(cycle_int or 1, 1)
    if u == "day":   return n
    if u == "week":  return n * 7
    if u == "month": return n * 30
    if u == "year":  return n * 365
    return 365


# ============================================================
# POST /legal-engine/generate-schedules/{factory_id}
# ============================================================

@router.post("/legal-engine/generate-schedules/{factory_id}")
def generate_schedules_from_diagnosis(factory_id: str):
    """
    최신 진단 결과(is_latest=True) → work_schedules 자동 생성.
    source_type='LEGAL'
    """
    supabase = get_supabase()

    diag_res = (
        supabase.table("factory_diagnosis_results")
        .select("id, factory_id, sector, result_data")
        .eq("factory_id", factory_id)
        .eq("is_latest", True)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not diag_res.data:
        raise HTTPException(status_code=404, detail="해당 시설의 진단 결과가 없습니다. 먼저 /legal-engine/diagnose/step1을 실행하세요.")

    result_data      = diag_res.data[0].get("result_data") or {}
    inspection_rules = result_data.get("inspection_required") or []
    total_rules      = len(inspection_rules)

    if not inspection_rules:
        return {"status": "success", "data": {"created": 0, "skipped": 0, "total_rules": 0,
                                               "message": "inspection_required 룰이 없습니다."}}

    fac_res    = supabase.table("factories").select("id, company_id").eq("id", factory_id).single().execute()
    company_id: Optional[str] = fac_res.data.get("company_id") if fac_res.data else None

    existing_res = (
        supabase.table("work_schedules")
        .select("rule_code")
        .eq("factory_id", factory_id)
        .eq("source_type", "LEGAL")
        .eq("status_code", "PENDING")
        .execute()
    )
    existing_rule_codes = {
        r["rule_code"] for r in (existing_res.data or []) if r.get("rule_code")
    }

    today   = business_today()
    created = 0
    skipped = 0
    rows    = []

    for rule in inspection_rules:
        rule_id = (rule.get("rule_id") or rule.get("rule_code") or "").strip()
        if not rule_id:
            skipped += 1; continue
        if rule_id in existing_rule_codes:
            skipped += 1; continue

        cycle_unit = rule.get("inspection_cycle_unit") or ""
        cycle_int  = int(rule.get("inspection_cycle_int") or 0)
        days       = _cycle_to_days(cycle_unit, cycle_int) if (cycle_unit and cycle_int) else 365
        planned    = today + timedelta(days=days)

        rows.append({
            "factory_id":      factory_id,
            "company_id":      company_id,
            "source_type":     "LEGAL",
            "rule_code":       rule_id,
            "description":     (rule.get("obligation_summary") or rule.get("description") or "").strip(),
            "obligation_type": rule.get("obligation_type") or "INSPECT",
            "law_name":        rule.get("law_name") or "",
            "law_article":     rule.get("law_article") or "",
            "form_code":       rule.get("form_code") or None,
            "planned_date":    planned.isoformat(),
            "status_code":     "PENDING",
            "active_yn":       True,
            "cycle_base_guide": f"{cycle_int}{cycle_unit} 주기" if (cycle_unit and cycle_int) else "",
        })
        existing_rule_codes.add(rule_id)

    for i in range(0, len(rows), 20):
        res = supabase.table("work_schedules").insert(rows[i:i+20]).execute()
        created += len(res.data or [])

    skipped += total_rules - len(rows)

    return {
        "status": "success",
        "data": {"created": created, "skipped": skipped, "total_rules": total_rules},
    }


# ============================================================
# POST /notifications/trigger-due-alerts
# ============================================================

@router.post("/notifications/trigger-due-alerts")
def trigger_due_alerts():
    """
    v1.1.0: D-7/D-3/D-0 마감 알림 생성.
    ★ assigned_user_id IS NOT NULL 필터 추가 — 담당자 없는 일정은 알림 미발송.
    """
    supabase = get_supabase()
    today = business_today()
    now   = now_kst()

    due_targets = [
        (7, "D-7",   "NORMAL"),
        (3, "D-3",   "HIGH"),
        (0, "당일",  "HIGH"),
    ]

    total_created = 0
    total_skipped = 0

    for days, label, priority in due_targets:
        target_date = today + timedelta(days=days)

        sched_res = (
            supabase.table("work_schedules")
            .select("id, factory_id, company_id, assigned_user_id, description, obligation_type, law_name")
            .eq("planned_date", target_date.isoformat())
            .eq("status_code", "PENDING")
            .eq("active_yn", True)
            .not_.is_("assigned_user_id", "null")  # ★ v1.1.0: 담당자 없는 일정 알림 제외
            .execute()
        )
        schedules = sched_res.data or []

        for sched in schedules:
            sched_id = sched["id"]
            link_url = f"/work-schedules/{sched_id}"

            dup_res = (
                supabase.table("notifications")
                .select("id", count="exact")
                .eq("trigger_code", "DUE_ALERT")
                .eq("link_url", link_url)
                .ilike("title", f"%{label}%")
                .execute()
            )
            if dup_res.count and dup_res.count > 0:
                total_skipped += 1
                continue

            desc  = (sched.get("description") or "점검 일정").strip()
            law   = sched.get("law_name") or ""
            title = f"점검 마감 알림 ({label})"
            body  = f"{desc}"
            if law:
                body += f"\n법령: {law}"
            body += f"\n마감: {target_date} ({label})"

            supabase.table("notifications").insert({
                "company_id":    sched.get("company_id"),
                "user_id":       sched.get("assigned_user_id"),
                "trigger_code":  "DUE_ALERT",
                "trigger_group": "SCHEDULE",
                "title":         title,
                "body":          body,
                "link_url":      link_url,
                "priority":      priority,
                "channel":       "SITE",
                "is_read":       False,
                "send_status":   "SUCCESS",
                "sent_at":       now.isoformat(),
                "created_at":    now.isoformat(),
            }).execute()
            total_created += 1

    return {
        "status": "success",
        "data": {
            "created": total_created,
            "skipped": total_skipped,
            "checked_dates": [
                (today + timedelta(days=d)).isoformat()
                for d in (0, 3, 7)
            ],
        },
    }
