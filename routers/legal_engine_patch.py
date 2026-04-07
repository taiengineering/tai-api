"""
legal_engine_patch.py
=====================
POST /legal-engine/generate-schedules/{factory_id}

v1.1.0 (2026-04-07)
  [FIX] planned_date = 오늘 날짜 고정 (cycle 계산 제거 — 작업지시서 v2 기준)
        이전 v1.0.0은 today + cycle_days 계산으로 2027년 등 미래 날짜가 생성됐음

v1.0.0 (2026-04-07)
  - factory_diagnosis_results(is_latest) → work_schedules 자동 INSERT
  - 실제 work_schedules 컬럼 기준 (information_schema 확인 완료)
  - 동일 rule_code + source_type='LEGAL' 존재 시 스킵
"""
from fastapi import APIRouter, HTTPException
from datetime import date
from typing import Optional

from db.supabase_client import get_supabase

router = APIRouter(tags=["법령엔진"])


@router.post("/legal-engine/generate-schedules/{factory_id}")
def generate_schedules_from_diagnosis(factory_id: str):
    """
    최신 진단 결과(is_latest=True) → work_schedules 자동 생성.

    로직:
    1. factories 테이블에서 factory_id 조회 → company_id 확보
    2. factory_diagnosis_results에서 is_latest 진단 조회
    3. result_data.inspection_required 배열 순회
    4. 동일 factory_id + rule_code + source_type='LEGAL' + status_code='PENDING' 존재 시 스킵
    5. work_schedules INSERT (planned_date=오늘, source_type='LEGAL')
    6. 생성 건수 반환
    """
    supabase = get_supabase()

    # 1. 시설 company_id 조회
    fac = (
        supabase.table("factories")
        .select("id, company_id")
        .eq("id", factory_id)
        .single()
        .execute()
    )
    if not fac.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다.")
    company_id: Optional[str] = fac.data.get("company_id")

    # 2. 최신 진단 결과 조회
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

    # 3. 기존 LEGAL+PENDING rule_code 목록 조회 (중복 방지)
    existing = (
        supabase.table("work_schedules")
        .select("rule_code")
        .eq("factory_id", factory_id)
        .eq("source_type", "LEGAL")
        .eq("status_code", "PENDING")
        .execute()
    )
    existing_codes = {
        r["rule_code"] for r in (existing.data or []) if r.get("rule_code")
    }

    today   = date.today()   # planned_date = 오늘 고정 (v1.1.0)
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

        cycle_unit = (rule.get("inspection_cycle_unit") or "").lower()
        cycle_int  = int(rule.get("inspection_cycle_int") or 0)

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
            "planned_date":    today.isoformat(),   # 오늘 날짜 고정
            "status_code":     "PENDING",
            "active_yn":       True,
            "cycle_base_guide": (
                f"{cycle_int}{cycle_unit} 주기" if (cycle_unit and cycle_int) else "주기 미지정"
            ),
        })
        existing_codes.add(rule_id)  # 루프 내 중복 방지

    # 4. 배치 INSERT (20건씩)
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
