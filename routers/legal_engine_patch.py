"""
legal_engine_patch.py
=====================
v1.3.0 (2026-04-07)
  [FIX] generate-schedules/all: CONSTRUCTION 한정 → is_active=True 전체 공장으로 확장
        (진단 결과 없는 공장은 자동 스킵)
  [ADD] POST /work-schedules/auto-assign
        PENDING + 미배정 work_schedules → 공장 안전관리자 자동 배정
        - factory_id 파라미터 (없으면 전체 공장)
        - users에서 role_code='003'(안전관리자) 또는 '012' 조회
        - work_assignments INSERT

v1.2.0 (2026-04-07)
  [ADD] POST /legal-engine/generate-schedules/all

v1.1.0 (2026-04-07)
  [FIX] planned_date = 오늘 날짜 고정 (cycle 계산 제거)

v1.0.0 (2026-04-07)
  - factory_diagnosis_results(is_latest) → work_schedules 자동 INSERT
"""
from fastapi import APIRouter, HTTPException, Query
from datetime import date, datetime, timezone
from typing import Optional, List
import uuid

from db.supabase_client import get_supabase

router = APIRouter(tags=["법령엔진"])

SAFETY_MANAGER_ROLES = {"003", "012"}  # 안전관리자 role_code


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ──────────────────────────────────────────────
# 주의: /all, /auto-assign 등 고정 경로는
#       /{factory_id} 보다 먼저 선언
# ──────────────────────────────────────────────

@router.post("/legal-engine/generate-schedules/all")
def generate_schedules_all():
    """
    v1.3.0: is_active=True 전체 공장에 대해 일괄 일정 생성.
    진단 결과 없는 공장은 에러로 표시하고 계속 진행.
    """
    supabase = get_supabase()
    factories = supabase.table("factories").select("id, name") \
        .eq("is_active", True).execute()
    results = []
    for f in (factories.data or []):
        try:
            r = generate_schedules_from_diagnosis(f["id"])
            results.append({"factory_id": f["id"], "name": f.get("name"), "result": r})
        except HTTPException as e:
            results.append({"factory_id": f["id"], "name": f.get("name"), "error": e.detail})
        except Exception as e:
            results.append({"factory_id": f["id"], "name": f.get("name"), "error": str(e)})

    total_created = sum(
        r.get("result", {}).get("data", {}).get("created", 0)
        for r in results if isinstance(r.get("result"), dict)
    )
    return {
        "status": "success",
        "data": {
            "processed":     len(results),
            "total_created": total_created,
            "results":       results,
        },
    }


@router.post("/work-schedules/auto-assign")
def auto_assign_schedules(
    factory_id: Optional[str] = Query(None, description="특정 공장만 처리 (없으면 전체)"),
):
    """
    v1.3.0: PENDING + assigned_user_id=NULL work_schedules 를
    공장 안전관리자(role_code 003/012)에게 자동 배정.

    로직:
    1. PENDING + active_yn=True + assigned_user_id 없는 스케줄 조회
    2. factory_id별로 그룹핑
    3. 해당 공장의 안전관리자(role_code IN 003,012) 1명 조회
    4. work_assignments INSERT + work_schedules.assigned_user_id 업데이트
    5. 배정 건수 반환
    """
    supabase = get_supabase()

    # 미배정 PENDING 스케줄 조회
    q = supabase.table("work_schedules").select(
        "id, factory_id, company_id, planned_date, rule_code, description, obligation_type"
    ).eq("status_code", "PENDING").eq("active_yn", True).is_("assigned_user_id", "null")

    if factory_id:
        q = q.eq("factory_id", factory_id)

    sched_res = q.execute()
    schedules = sched_res.data or []

    if not schedules:
        return {"status": "success", "data": {"assigned": 0, "skipped": 0, "message": "배정할 스케줄 없음"}}

    # factory_id별 그룹핑
    factory_map: dict = {}
    for s in schedules:
        fid = s["factory_id"]
        if fid not in factory_map:
            factory_map[fid] = []
        factory_map[fid].append(s)

    assigned_total = 0
    skipped_total  = 0
    today_str = date.today().isoformat()
    now       = _now_iso()

    for fid, scheds in factory_map.items():
        # 안전관리자 조회 (role_code 003 우선, 없으면 012)
        manager_id = None
        for role in ("003", "012"):
            u_res = supabase.table("users").select("id").eq("factory_id", fid) \
                .eq("role_code", role).eq("is_active", True).limit(1).execute()
            if u_res.data:
                manager_id = u_res.data[0]["id"]
                break

        if not manager_id:
            # company_id로 fallback 시도
            company_id = scheds[0].get("company_id")
            if company_id:
                for role in ("003", "012", "002"):
                    u_res = supabase.table("users").select("id") \
                        .eq("company_id", company_id).eq("role_code", role) \
                        .eq("is_active", True).limit(1).execute()
                    if u_res.data:
                        manager_id = u_res.data[0]["id"]
                        break

        if not manager_id:
            skipped_total += len(scheds)
            continue

        # work_assignments INSERT + work_schedules.assigned_user_id 업데이트
        assign_rows = []
        sched_ids   = []
        for s in scheds:
            assign_rows.append({
                "schedule_id":      s["id"],
                "assigned_user_id": manager_id,
                "scheduled_date":   s.get("planned_date") or today_str,
                "status_code":      "PENDING",
                "created_at":       now,
            })
            sched_ids.append(s["id"])

        # 배치 INSERT (20건씩)
        for i in range(0, len(assign_rows), 20):
            try:
                supabase.table("work_assignments").insert(assign_rows[i:i+20]).execute()
            except Exception as e:
                print(f"[AUTO_ASSIGN] work_assignments insert 실패: {e}")
                continue

        # work_schedules.assigned_user_id 업데이트
        for sid in sched_ids:
            try:
                supabase.table("work_schedules").update({
                    "assigned_user_id": manager_id,
                    "updated_at":       now,
                }).eq("id", sid).execute()
            except Exception as e:
                print(f"[AUTO_ASSIGN] work_schedules update 실패 sid={sid}: {e}")

        assigned_total += len(scheds)

    return {
        "status": "success",
        "data": {
            "assigned":   assigned_total,
            "skipped":    skipped_total,
            "factories":  len(factory_map),
            "message":    f"{assigned_total}건 배정 완료 ({skipped_total}건 안전관리자 미지정으로 스킵)",
        },
    }


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
            detail="진단 결과 없음 (step1 먼저 실행 필요)",
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
            "planned_date":    today.isoformat(),
            "status_code":     "PENDING",
            "active_yn":       True,
            "cycle_base_guide": (
                f"{cycle_int}{cycle_unit} 주기" if (cycle_unit and cycle_int) else "주기 미지정"
            ),
        })
        existing_codes.add(rule_id)

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
