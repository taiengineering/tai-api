"""
legal_engine_patch.py
=====================
POST /legal-engine/generate-schedules/{factory_id}

v1.0.0 (2026-04-07)
  - factory_diagnosis_results(is_latest) → work_schedules 자동 INSERT
  - 실제 work_schedules 콘럼 기준 (information_schema 확인 완료)
    rule_code, description, source_type, factory_id, company_id,
    planned_date, status_code, active_yn, obligation_type,
    law_name, law_article, form_code, cycle_base_guide
  - 동일 rule_code + source_type='LEGAL' 존재 시 스킵

ROUTE PREFIX: /legal-engine (이미 legal_engine_router에 등록된 prefix와 일치)
주의: main.py에서 legal_engine_router 등록 순서 뒤라기 전에 이 router를 도 등록든다.
       prefix '/legal-engine' 없이 엔드포인트에 직접 prefix 포함.
"""
from fastapi import APIRouter, HTTPException
from datetime import date, timedelta
from typing import Optional

from db.supabase_client import get_supabase

router = APIRouter(tags=["법령엔진"])

# 점검 주기 단위 → 일(day) 변환 테이블
_UNIT_DAYS = {"day": 1, "week": 7, "month": 30, "year": 365}


@router.post("/legal-engine/generate-schedules/{factory_id}")
def generate_schedules_from_diagnosis(factory_id: str):
    """
    최신 진단 결과(is_latest=True) → work_schedules 자동 생성.

    로직:
    1. factory_diagnosis_results에서 factory_id의 is_latest 진단 조회
    2. result_data.inspection_required 배열 순회
    3. 동일 rule_code + source_type='LEGAL' 이미 존재 시 스킵 (중복 방지)
    4. work_schedules INSERT (source_type='LEGAL')
    5. 생성 건수 반환
    """
    supabase = get_supabase()

    # 1. 최신 진단 결과 조회
    diag = (
        supabase.table("factory_diagnosis_results")
        .select("id, factory_id, sector, result_data")
        .eq("factory_id", factory_id)
        .eq("is_latest", True)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not diag.data:
        raise HTTPException(
            status_code=404,
            detail=(
                "해당 시설의 진단 결과가 없습니다. "
                "/legal-engine/diagnose/step1을 먼저 실행하세요."
            ),
        )

    result_data      = diag.data[0].get("result_data") or {}
    inspection_rules = result_data.get("inspection_required") or []
    total_rules      = len(inspection_rules)

    if not inspection_rules:
        return {"status": "success", "data": {"created": 0, "skipped": 0, "total_rules": 0}}

    # 2. 시설 company_id 조회
    fac = (
        supabase.table("factories")
        .select("id, company_id")
        .eq("id", factory_id)
        .single()
        .execute()
    )
    company_id: Optional[str] = fac.data.get("company_id") if fac.data else None

    # 3. 기존 LEGAL 일정 rule_code 목록 조회 (중복 방지)
    existing = (
        supabase.table("work_schedules")
        .select("rule_code")
        .eq("factory_id", factory_id)
        .eq("source_type", "LEGAL")
        .execute()
    )
    existing_codes = {
        r["rule_code"] for r in (existing.data or []) if r.get("rule_code")
    }

    today   = date.today()
    rows    = []
    skipped = 0

    for rule in inspection_rules:
        rule_id = (rule.get("rule_id") or rule.get("rule_code") or "").strip()
        if not rule_id:
            skipped += 1
            continue
        if rule_id in existing_codes:
            skipped += 1
            continue

        # 점검 주기 → planned_date 계산
        cycle_unit = (rule.get("inspection_cycle_unit") or "").lower()
        cycle_int  = int(rule.get("inspection_cycle_int") or 0)
        days_add   = (cycle_int or 1) * _UNIT_DAYS.get(cycle_unit, 365)
        planned    = today + timedelta(days=days_add)

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
            "cycle_base_guide": (
                f"{cycle_int}{cycle_unit} 주기" if (cycle_unit and cycle_int) else "주기 미지정"
            ),
        })
        existing_codes.add(rule_id)  # 루프 내 중복 방지

    # 4. 배치 INSERT (20건씨)
    created = 0
    for i in range(0, len(rows), 20):
        res = supabase.table("work_schedules").insert(rows[i:i + 20]).execute()
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
