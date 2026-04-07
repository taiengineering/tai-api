"""
진단→일정 자동생성 + D-7/D-3/당일 알림 파이프 — v1.0.0
============================================================
v1.0.0 (2026-04-07):
  POST /legal-engine/generate-schedules/{factory_id}
      소습: factory_diagnosis_results(is_latest) → work_schedules 자동 INSERT
      중복(rule_code + PENDING) 스킵, 생성 건수 반환

  POST /notifications/trigger-due-alerts
      소습: work_schedules.planned_date 기준 D-7/D-3/D-0 조회 → notifications INSERT
      중복(link_url + due_label) 스킵, 생성 건수 반환
"""
from fastapi import APIRouter, HTTPException
from datetime import date, datetime, timedelta
from typing import Optional

from db.supabase_client import get_supabase

# ============================================================
# 라우터 선언 (prefix 없음 — 엔드포인트 자체에 수동 prefix 포함)
# ============================================================

router = APIRouter(tags=["일정파이프"])


# ============================================================
# 헬퍼
# ============================================================

def _cycle_to_days(cycle_unit: str, cycle_int: int) -> int:
    """점검 주기 → 일(day) 변환."""
    u = (cycle_unit or "").lower()
    n = max(cycle_int or 1, 1)
    if u == "day":   return n
    if u == "week":  return n * 7
    if u == "month": return n * 30
    if u == "year":  return n * 365
    return 365  # 기본 1년


# ============================================================
# 작업1: POST /legal-engine/generate-schedules/{factory_id}
# ============================================================

@router.post("/legal-engine/generate-schedules/{factory_id}")
def generate_schedules_from_diagnosis(factory_id: str):
    """
    최신 진단 결과(is_latest=True) → work_schedules 자동 생성.

    로직:
    1. factory_diagnosis_results 에서 해당 factory_id의 is_latest 진단 조회
    2. result_data.inspection_required 순회
    3. 동일 rule_code + PENDING 존재 시 스킵 (중복 방지)
    4. work_schedules INSERT (source_type='LEGAL')
    5. 생성 건수 반환
    """
    supabase = get_supabase()

    # 1. 최신 진단 결과 조회
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

    result_data       = diag_res.data[0].get("result_data") or {}
    inspection_rules  = result_data.get("inspection_required") or []
    total_rules       = len(inspection_rules)

    if not inspection_rules:
        return {"status": "success", "data": {"created": 0, "skipped": 0, "total_rules": 0,
                                               "message": "inspection_required 룰이 없습니다."}}

    # 2. 시설 company_id 조회
    fac_res = supabase.table("factories").select("id, company_id").eq("id", factory_id).single().execute()
    company_id: Optional[str] = fac_res.data.get("company_id") if fac_res.data else None

    # 3. 기존 LEGAL+PENDING rule_code 목록 조회 (중복 방지)
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

    today    = date.today()
    created  = 0
    skipped  = 0
    rows     = []

    for rule in inspection_rules:
        rule_id = (rule.get("rule_id") or rule.get("rule_code") or "").strip()
        if not rule_id:
            skipped += 1
            continue
        if rule_id in existing_rule_codes:
            skipped += 1
            continue

        # 점검 주기 기반 planned_date 계산
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
        existing_rule_codes.add(rule_id)  # 동일 루프 내 중복 방지

    # 4. 배치 INSERT (20건씨)
    for i in range(0, len(rows), 20):
        res = supabase.table("work_schedules").insert(rows[i:i+20]).execute()
        created += len(res.data or [])

    skipped += total_rules - len(rows)

    return {
        "status": "success",
        "data": {
            "created":     created,
            "skipped":     skipped,
            "total_rules": total_rules,
        },
    }


# ============================================================
# 작업2: POST /notifications/trigger-due-alerts
# ============================================================

@router.post("/notifications/trigger-due-alerts")
def trigger_due_alerts():
    """
    D-7 / D-3 / D-0 기준 work_schedules 마감 알림 생성.
    매일 오전 8시 크론으로 호웉.

    로직:
    1. 오늘+7/+3/+0 마감인 PENDING 일정 조회
    2. 이미 알림이 존재하면 스킵 (link_url + due_label 중복 체크)
    3. notifications 테이블에 INSERT
    4. 생성 건수 반환
    """
    supabase = get_supabase()
    today = date.today()
    now   = datetime.now()

    due_targets = [
        (7, "D-7",   "NORMAL"),
        (3, "D-3",   "HIGH"),
        (0, "\ub2f9\uc77c", "HIGH"),
    ]

    total_created = 0
    total_skipped = 0

    for days, label, priority in due_targets:
        target_date = today + timedelta(days=days)

        # 해당 마감 PENDING 일정 조회
        sched_res = (
            supabase.table("work_schedules")
            .select("id, factory_id, company_id, assigned_user_id, description, obligation_type, law_name")
            .eq("planned_date", target_date.isoformat())
            .eq("status_code", "PENDING")
            .eq("active_yn", True)
            .execute()
        )
        schedules = sched_res.data or []

        for sched in schedules:
            sched_id  = sched["id"]
            link_url  = f"/work-schedules/{sched_id}"

            # 중복 체크: 동일 schedule link_url + label이 이미 있으면 스킵
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

            desc    = (sched.get("description") or "점검 일정").strip()
            law     = sched.get("law_name") or ""
            title   = f"점검 마감 알림 ({label})"
            body    = f"{desc}"
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
