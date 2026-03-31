"""
이벤트 기반 신고·보고 일정 자동 생성 모듈 — v1.0.0

이벤트(선임, 사고, 변경, 설치, 폐업) 발생 시 호출됩니다.
work_schedules에 source_type='EVENT'로 REPORT/NOTIFY 일정을 생성합니다.

API:
  GET  /event-schedules/factory/{factory_id}  이벤트 기반 신고·보고 일정 목록
  POST /event-schedules/trigger               수동 트리거 (테스트/가동용)
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import date, timedelta, datetime
from db.supabase_client import get_supabase

router = APIRouter(tags=["event_trigger"])

VERSION = "1.0.0"

# cycle_base_type → 기본 due_days 매핑
DEFAULT_DUE_DAYS = {
    "APPOINTMENT":    14,   # 안전관리자 선임 후 14일 이내 신고
    "INCIDENT":        1,   # 사고 즉시 신고 (1일 = 당일)
    "CHANGE":         14,   # 변경 후 14일 이내 신고
    "INSTALL":        30,   # 설치 후 30일 이내 검사
    "CLOSURE":        14,   # 폐업 후 14일 이내 폐업신고
    "ACCIDENT_REPORT": 30,  # 산재조사표 제출 30일
}


async def trigger_event_schedules(
    factory_id: str,
    event_type: str,
    event_date: Optional[date] = None,
    context: dict = {},
) -> dict:
    """
    이벤트 발생 시 해당 factory의 REPORT/NOTIFY 룰을 조회하여
    work_schedules에 마감 일정을 생성합니다.

    Returns:
        {"created": int, "skipped": int, "event_type": str,
         "event_date": str, "schedules": [...]}
    """
    supabase   = get_supabase()
    event_date = event_date or date.today()
    created, skipped, schedules = 0, 0, []

    # 1. factory의 진단 결과에서 REPORT/NOTIFY 룰 조회
    try:
        rules_res = supabase.table("diagnosis_rule_results").select(
            "id, factory_id, obligation_type, obligation_summary, "
            "rule_code, law_name, law_article, form_code"
        ).eq("factory_id", factory_id).in_(
            "obligation_type", ["REPORT", "NOTIFY"]
        ).execute()
        rules = rules_res.data or []
    except Exception as e:
        print(f"[EVENT_TRIGGER] diagnosis_rule_results 조회 실패: {e}")
        return {"created": 0, "skipped": 0, "event_type": event_type,
                "event_date": str(event_date), "schedules": [], "error": str(e)}

    # 2. master 룰에서 cycle_base_type 매칭
    # diagnosis_rule_results에 rule_code 있으면 master 조회
    rule_codes = [r.get("rule_code") for r in rules if r.get("rule_code")]
    master_map = {}
    if rule_codes:
        try:
            master_res = supabase.table("master_building_legal_rules").select(
                "rule_code, cycle_base_type, due_days, cycle_base_guide"
            ).in_("rule_code", rule_codes).execute()
            for m in (master_res.data or []):
                master_map[m["rule_code"]] = m
        except Exception as e:
            print(f"[EVENT_TRIGGER] master_building_legal_rules 조회 실패: {e}")

    # 3. event_type 매칭 후 일정 생성
    for rule in rules:
        rc     = rule.get("rule_code", "")
        master = master_map.get(rc, {})
        base_type = master.get("cycle_base_type", "")

        # cycle_base_type 가 event_type과 일치하는 룰만 처리
        if base_type != event_type:
            continue

        # 마감일 계산
        due_days = master.get("due_days") or DEFAULT_DUE_DAYS.get(event_type, 14)
        deadline = event_date + timedelta(days=due_days)

        # 30일 이내 중복 체크
        try:
            existing = supabase.table("work_schedules").select("id").eq(
                "factory_id", factory_id
            ).eq("source_type", "EVENT").eq(
                "event_type", event_type
            ).eq("rule_code", rc).gte(
                "planned_date", str(event_date - timedelta(days=30))
            ).execute()
            if existing.data:
                skipped += 1
                continue
        except Exception:
            pass  # 중복 체크 실패 시 그냥 진행

        # work_schedules INSERT
        try:
            row = {
                "factory_id":       factory_id,
                "rule_code":        rc,
                "law_name":         rule.get("law_name", ""),
                "law_article":      rule.get("law_article", ""),
                "obligation_type":  rule.get("obligation_type", ""),
                "summary":          rule.get("obligation_summary") or rc,
                "source_type":      "EVENT",
                "status_code":      "SCHEDULED",
                "planned_date":     str(deadline),
                "event_type":       event_type,
                "event_date":       str(event_date),
                "form_code":        rule.get("form_code"),
                "cycle_base_guide": master.get("cycle_base_guide", ""),
                "assigned_user_id": context.get("assigned_user_id"),
                "active_yn":        True,
            }
            # company_id 추가 (시설에서 조회)
            if context.get("company_id"):
                row["company_id"] = context["company_id"]

            ins = supabase.table("work_schedules").insert(row).execute()
            if ins.data:
                created += 1
                schedules.append(ins.data[0])
        except Exception as e:
            print(f"[EVENT_TRIGGER] work_schedules INSERT 실패 (rule={rc}): {e}")
            skipped += 1

    return {
        "created":    created,
        "skipped":    skipped,
        "event_type": event_type,
        "event_date": str(event_date),
        "schedules":  schedules,
    }


# ============================================================
# Pydantic 모델
# ============================================================

class ManualTriggerBody(BaseModel):
    factory_id:    str
    event_type:    str            # APPOINTMENT | INCIDENT | CHANGE | INSTALL | CLOSURE | ACCIDENT_REPORT
    event_date:    Optional[str] = None  # YYYY-MM-DD, 없으면 오늘
    assigned_user_id: Optional[str] = None


# ============================================================
# POST /event-schedules/trigger  수동 트리거 (테스트/관리자용)
# ============================================================

@router.post("/event-schedules/trigger")
async def manual_trigger(body: ManualTriggerBody):
    """
    수동으로 이벤트 트리거 실행.
    테스트 또는 관리자가 직접 트리거할 때 사용.
    """
    valid_types = {"APPOINTMENT", "INCIDENT", "CHANGE", "INSTALL", "CLOSURE", "ACCIDENT_REPORT"}
    if body.event_type not in valid_types:
        raise HTTPException(
            status_code=422,
            detail=f"event_type은 {sorted(valid_types)} 중 하나여야 합니다."
        )

    ev_date = date.fromisoformat(body.event_date) if body.event_date else date.today()
    result  = await trigger_event_schedules(
        factory_id = body.factory_id,
        event_type = body.event_type,
        event_date = ev_date,
        context    = {"assigned_user_id": body.assigned_user_id},
    )
    return {"status": "success", "data": result}


# ============================================================
# GET /event-schedules/factory/{factory_id}  이벤트 일정 목록
# ============================================================

@router.get("/event-schedules/factory/{factory_id}")
def get_event_schedules(
    factory_id:        str,
    obligation_type:   Optional[str] = Query(None, description="REPORT | NOTIFY"),
    status_code:       Optional[str] = Query(None, description="SCHEDULED | COMPLETED"),
    event_type:        Optional[str] = Query(None, description="APPOINTMENT | INCIDENT | CHANGE ..."),
    planned_date_from: Optional[str] = Query(None),
    planned_date_to:   Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    """
    factory의 이벤트 기반 신고·보고 일정 목록.
    work_schedules에서 source_type='EVENT'인 항목만 반환.
    """
    supabase = get_supabase()
    query    = supabase.table("work_schedules").select("*", count="exact").eq(
        "factory_id", factory_id
    ).eq("source_type", "EVENT")

    if obligation_type:   query = query.eq("obligation_type",  obligation_type)
    if status_code:       query = query.eq("status_code",       status_code)
    if event_type:        query = query.eq("event_type",        event_type)
    if planned_date_from: query = query.gte("planned_date",     planned_date_from)
    if planned_date_to:   query = query.lte("planned_date",     planned_date_to)

    offset = (page - 1) * size
    res    = query.order("planned_date").range(offset, offset + size - 1).execute()
    total  = res.count or 0

    return {
        "status": "success",
        "data": {
            "items":       res.data or [],
            "total":       total,
            "page":        page,
            "size":        size,
            "total_pages": (total + size - 1) // size if total else 0,
        }
    }
