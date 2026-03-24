# routers/report_forms.py v1.0.0
# 안전관리 신고서식 자동화 API
#
# 엔드포인트:
#   GET  /report-forms/templates                   — 서식 목록
#   GET  /report-forms/templates/{form_code}       — 서식 상세
#   GET  /report-forms/events/{factory_id}         — 시설 신고 이벤트 목록 (D-day)
#   POST /report-forms/events                      — 신고 이벤트 생성
#   PATCH /report-forms/events/{event_id}          — 이벤트 상태 변경
#   GET  /report-forms/submissions/{factory_id}    — 제출 서류 목록
#   POST /report-forms/submissions                 — 서류 저장
#   PATCH /report-forms/submissions/{id}           — 서류 수정
#   GET  /report-forms/submissions/{id}/pdf        — PDF 생성 (추후)

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import datetime, date, timedelta
import os
from supabase import create_client

router = APIRouter(prefix="/report-forms", tags=["신고서식"])

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ============================================================
# 1. 서식 목록 / 상세
# ============================================================

@router.get("/templates")
def get_form_templates(
    law_code:  Optional[str]  = Query(None, description="법령 코드 (OSHACT)"),
    is_active: bool           = Query(True),
    page:      int            = Query(1, ge=1),
    page_size: int            = Query(20, ge=1, le=100),
):
    """서식 템플릿 목록 조회"""
    supabase = get_supabase()
    offset = (page - 1) * page_size

    q = supabase.table("form_templates").select(
        "id, form_code, form_no, form_name, law_code, "
        "submit_to, submit_timing, trigger_event, bylSeq, hwp_url, is_active",
        count="exact"
    ).eq("is_active", is_active)

    if law_code:
        q = q.eq("law_code", law_code)

    q = q.order("form_code").range(offset, offset + page_size - 1)
    res = q.execute()

    return {
        "status": "success",
        "data": {
            "items":      res.data or [],
            "total":      res.count or 0,
            "page":       page,
            "page_size":  page_size,
        }
    }


@router.get("/templates/{form_code}")
def get_form_template(form_code: str):
    """서식 템플릿 상세 조회 (form_json 포함)"""
    supabase = get_supabase()

    res = supabase.table("form_templates").select("*").eq(
        "form_code", form_code
    ).single().execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="서식을 찾을 수 없습니다")

    return {"status": "success", "data": res.data}


# ============================================================
# 2. 신고 이벤트 (D-day 추적)
# ============================================================

@router.get("/events/{factory_id}")
def get_report_events(
    factory_id: str,
    status:    Optional[str] = Query(None, description="PENDING/IN_PROGRESS/COMPLETED/OVERDUE"),
    include_overdue: bool    = Query(True, description="기한 초과 포함 여부"),
):
    """
    시설의 신고 이벤트 목록 조회
    - due_date 기준 D-day 자동 계산
    - status=PENDING/IN_PROGRESS 인 것 우선 반환
    """
    supabase = get_supabase()

    q = supabase.table("report_events").select(
        "*, form_templates(form_code, form_name, submit_to, submit_timing)"
    ).eq("factory_id", factory_id)

    if status:
        q = q.eq("status", status)

    q = q.order("due_date")
    res = q.execute()
    items = res.data or []

    today = date.today()
    result = []
    for item in items:
        due = item.get("due_date")
        if due:
            d = date.fromisoformat(due)
            days_left = (d - today).days
            item["days_left"]   = days_left
            item["is_overdue"]  = days_left < 0
            item["is_urgent"]   = 0 <= days_left <= 7  # 7일 이내 긴급
            item["d_day_label"] = (
                f"D-{abs(days_left)}" if days_left < 0 else
                f"D-{days_left}" if days_left > 0 else
                "D-Day"
            )

            # PENDING 중 기한 초과된 것 자동 OVERDUE 처리
            if item.get("status") == "PENDING" and days_left < 0:
                supabase.table("report_events").update(
                    {"status": "OVERDUE", "updated_at": datetime.now().isoformat()}
                ).eq("id", item["id"]).execute()
                item["status"] = "OVERDUE"

        if not include_overdue and item.get("is_overdue"):
            continue

        result.append(item)

    # 긴급/미완료 우선 정렬
    result.sort(key=lambda x: (
        x.get("status") == "COMPLETED",
        x.get("days_left", 9999)
    ))

    return {
        "status": "success",
        "data": {
            "factory_id": factory_id,
            "items":      result,
            "total":      len(result),
            "urgent_count": sum(1 for r in result if r.get("is_urgent") and r.get("status") != "COMPLETED"),
            "overdue_count": sum(1 for r in result if r.get("is_overdue")),
        }
    }


@router.post("/events")
def create_report_event(body: dict):
    """
    신고 이벤트 생성
    body: {
      factory_id, rule_code, form_code,
      trigger_date (YYYY-MM-DD),
      due_days (미입력 시 form의 submit_timing에서 자동 계산)
    }
    """
    supabase = get_supabase()

    factory_id   = body.get("factory_id")
    form_code    = body.get("form_code")
    trigger_date = body.get("trigger_date")

    if not factory_id or not form_code or not trigger_date:
        raise HTTPException(status_code=400, detail="factory_id, form_code, trigger_date 필수")

    # due_days 계산
    due_days = body.get("due_days")
    if not due_days:
        # master_building_legal_rules에서 due_days 조회
        rule_res = supabase.table("master_building_legal_rules").select(
            "due_days"
        ).eq("form_code", form_code).limit(1).execute()
        if rule_res.data and rule_res.data[0].get("due_days"):
            due_days = rule_res.data[0]["due_days"]
        else:
            due_days = 14  # 기본값 14일

    trigger = date.fromisoformat(trigger_date)
    due     = trigger + timedelta(days=due_days)

    insert_data = {
        "factory_id":   factory_id,
        "rule_code":    body.get("rule_code"),
        "form_code":    form_code,
        "trigger_date": trigger_date,
        "due_date":     due.isoformat(),
        "status":       "PENDING",
        "created_at":   datetime.now().isoformat(),
        "updated_at":   datetime.now().isoformat(),
    }

    res = supabase.table("report_events").insert(insert_data).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="이벤트 생성 실패")

    event = res.data[0]
    days_left = (due - date.today()).days
    event["days_left"]   = days_left
    event["d_day_label"] = f"D-{days_left}" if days_left > 0 else ("D-Day" if days_left == 0 else f"D+{abs(days_left)}")

    return {
        "status":  "success",
        "message": f"신고 이벤트가 생성됐습니다. 마감일: {due.isoformat()} ({event['d_day_label']})",
        "data":    event
    }


@router.patch("/events/{event_id}")
def update_report_event_status(event_id: str, body: dict):
    """이벤트 상태 변경 (PENDING → IN_PROGRESS → COMPLETED)"""
    supabase = get_supabase()

    allowed_status = {"PENDING", "IN_PROGRESS", "COMPLETED", "OVERDUE"}
    status = body.get("status")

    if status and status not in allowed_status:
        raise HTTPException(status_code=400, detail=f"status는 {allowed_status} 중 하나여야 합니다")

    update_data = {"updated_at": datetime.now().isoformat()}
    if status:
        update_data["status"] = status
    if status == "COMPLETED":
        update_data["completed_at"] = datetime.now().isoformat()

    res = supabase.table("report_events").update(update_data).eq("id", event_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="이벤트를 찾을 수 없습니다")

    return {"status": "success", "message": "이벤트 상태가 변경됐습니다.", "data": res.data[0]}


# ============================================================
# 3. 서류 제출 (form_submissions)
# ============================================================

@router.get("/submissions/{factory_id}")
def get_form_submissions(
    factory_id: str,
    form_code:  Optional[str] = Query(None),
    page:       int           = Query(1, ge=1),
    page_size:  int           = Query(20, ge=1, le=100),
):
    """시설의 작성된 서류 목록 조회"""
    supabase = get_supabase()
    offset = (page - 1) * page_size

    q = supabase.table("form_submissions").select(
        "id, factory_id, form_code, event_id, pdf_url, submitted_at, created_at, "
        "form_templates(form_name, form_no)",
        count="exact"
    ).eq("factory_id", factory_id)

    if form_code:
        q = q.eq("form_code", form_code)

    q = q.order("created_at", desc=True).range(offset, offset + page_size - 1)
    res = q.execute()

    return {
        "status": "success",
        "data": {
            "items":     res.data or [],
            "total":     res.count or 0,
            "page":      page,
            "page_size": page_size,
        }
    }


@router.get("/submissions/detail/{submission_id}")
def get_form_submission(submission_id: str):
    """서류 상세 조회 (form_data 포함)"""
    supabase = get_supabase()

    res = supabase.table("form_submissions").select(
        "*, form_templates(form_name, form_no, form_json, submit_to)"
    ).eq("id", submission_id).single().execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="서류를 찾을 수 없습니다")

    return {"status": "success", "data": res.data}


@router.post("/submissions")
def create_form_submission(body: dict):
    """
    서류 저장 (서식 작성 완료)
    body: {
      factory_id, form_code, event_id (선택),
      form_data: { ... 입력된 서식 데이터 ... }
    }
    """
    supabase = get_supabase()

    factory_id = body.get("factory_id")
    form_code  = body.get("form_code")
    form_data  = body.get("form_data", {})

    if not factory_id or not form_code:
        raise HTTPException(status_code=400, detail="factory_id, form_code 필수")

    # 시설 기본정보 자동채움 (factories 조회)
    fac_res = supabase.table("factories").select(
        "name, address_road, address_jibun, ksic_code, ksic_name, worker_count, "
        "companies(name, business_number, representative_name)"
    ).eq("id", factory_id).single().execute()

    if fac_res.data:
        fac = fac_res.data
        co  = fac.get("companies") or {}
        # auto_fill 데이터 병합 (이미 입력된 값 우선)
        auto_filled = {
            "factory_name":         fac.get("name", ""),
            "factory_address":      fac.get("address_road") or fac.get("address_jibun", ""),
            "worker_count":         fac.get("worker_count", ""),
            "company_name":         co.get("name", ""),
            "business_number":      co.get("business_number", ""),
            "representative_name":  co.get("representative_name", ""),
        }
        for k, v in auto_filled.items():
            if k not in form_data or not form_data[k]:
                form_data[k] = v

    insert_data = {
        "factory_id": factory_id,
        "form_code":  form_code,
        "event_id":   body.get("event_id"),
        "form_data":  form_data,
        "created_by": body.get("created_by"),
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }

    res = supabase.table("form_submissions").insert(insert_data).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="서류 저장 실패")

    # 이벤트 상태 IN_PROGRESS로 변경
    if body.get("event_id"):
        supabase.table("report_events").update(
            {"status": "IN_PROGRESS", "updated_at": datetime.now().isoformat()}
        ).eq("id", body["event_id"]).eq("status", "PENDING").execute()

    return {
        "status":  "success",
        "message": "서류가 저장됐습니다.",
        "data":    res.data[0]
    }


@router.patch("/submissions/{submission_id}")
def update_form_submission(submission_id: str, body: dict):
    """서류 수정 (form_data, submitted_at)"""
    supabase = get_supabase()

    allowed = {"form_data", "pdf_url", "submitted_at"}
    update_data = {k: v for k, v in body.items() if k in allowed}
    update_data["updated_at"] = datetime.now().isoformat()

    if not update_data:
        raise HTTPException(status_code=400, detail="수정할 항목이 없습니다")

    res = supabase.table("form_submissions").update(update_data).eq(
        "id", submission_id
    ).execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="서류를 찾을 수 없습니다")

    # submitted_at 입력 시 이벤트 COMPLETED 처리
    if "submitted_at" in update_data:
        sub = res.data[0]
        if sub.get("event_id"):
            supabase.table("report_events").update(
                {"status": "COMPLETED", "completed_at": datetime.now().isoformat(), "updated_at": datetime.now().isoformat()}
            ).eq("id", sub["event_id"]).execute()

    return {"status": "success", "message": "서류가 수정됐습니다.", "data": res.data[0]}


# ============================================================
# 4. 대시보드용 — 전체 신고 현황 요약
# ============================================================

@router.get("/dashboard/{factory_id}")
def get_report_dashboard(factory_id: str):
    """
    tadmin 대시보드용 신고 현황 요약
    - 긴급(7일 이내), 임박(30일 이내), 완료, 기한초과 건수
    """
    supabase = get_supabase()

    res = supabase.table("report_events").select(
        "id, form_code, due_date, status, "
        "form_templates(form_name, submit_to)"
    ).eq("factory_id", factory_id).neq("status", "COMPLETED").execute()

    items = res.data or []
    today = date.today()

    urgent   = []  # 7일 이내
    upcoming = []  # 8~30일
    overdue  = []  # 기한 초과

    for item in items:
        due = item.get("due_date")
        if not due:
            continue
        d = date.fromisoformat(due)
        days_left = (d - today).days
        item["days_left"]   = days_left
        item["d_day_label"] = (
            f"D+{abs(days_left)}" if days_left < 0 else
            f"D-{days_left}" if days_left > 0 else "D-Day"
        )

        if days_left < 0:
            overdue.append(item)
        elif days_left <= 7:
            urgent.append(item)
        elif days_left <= 30:
            upcoming.append(item)

    # 완료 건수
    completed_res = supabase.table("report_events").select(
        "id", count="exact"
    ).eq("factory_id", factory_id).eq("status", "COMPLETED").execute()

    return {
        "status": "success",
        "data": {
            "factory_id":     factory_id,
            "urgent":         sorted(urgent,   key=lambda x: x["days_left"]),
            "upcoming":       sorted(upcoming, key=lambda x: x["days_left"]),
            "overdue":        sorted(overdue,  key=lambda x: x["days_left"]),
            "summary": {
                "urgent_count":    len(urgent),
                "upcoming_count":  len(upcoming),
                "overdue_count":   len(overdue),
                "completed_count": completed_res.count or 0,
            }
        }
    }


# ============================================================
# 5. 테스트
# ============================================================

@router.get("/test")
def test():
    return {"status": "ok", "message": "report-forms API v1.0.0"}
