# routers/report_forms.py v2.0.0
# 안전관리 신고서식 자동화 API
#
# 엔드포인트:
#   GET  /report-forms/templates                            — 서식 목록
#   GET  /report-forms/templates/{form_code}                — 서식 상세
#   GET  /report-forms/obligations                          — 법적 의무 목록 [NEW]
#   GET  /report-forms/obligations/by-factory/{factory_id}  — 시설별 의무 [NEW]
#   GET  /report-forms/events/{factory_id}                  — 신고 이벤트 목록
#   POST /report-forms/events                               — 신고 이벤트 생성
#   PATCH /report-forms/events/{event_id}                   — 이벤트 상태 변경
#   GET  /report-forms/submissions/{factory_id}             — 제출 서류 목록
#   GET  /report-forms/submissions/detail/{id}              — 서류 상세
#   POST /report-forms/submissions                          — 서류 저장
#   PATCH /report-forms/submissions/{id}                    — 서류 수정
#   POST /report-forms/submissions/preview-pdf              — 즉시 PDF 스트림 [NEW]
#   POST /report-forms/submissions/{id}/pdf                 — 저장 후 PDF [NEW]
#   GET  /report-forms/dashboard/{factory_id}               — 대시보드 요약
#   GET  /report-forms/test                                 — 헬스체크

from fastapi import APIRouter, HTTPException, Query, Body
from fastapi.responses import StreamingResponse, JSONResponse
from typing import Optional
from datetime import datetime, date, timedelta
import os, io, re
from supabase import create_client

router = APIRouter(prefix="/report-forms", tags=["신고서식"])

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# HTML 템플릿 경로 맵 (form_code → 파일 경로)
TEMPLATE_MAP = {
    "OSHACT-FORM-002": "templates/forms/OSHACT_FORM_002.html",
}


def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def _render_html_template(template_path: str, form_data: dict) -> str:
    """{{ key }} 치환으로 HTML 렌더링 (Jinja2 의존 없이)"""
    from pathlib import Path
    html = Path(template_path).read_text(encoding="utf-8")
    for k, v in form_data.items():
        html = html.replace("{{ " + k + " }}", str(v) if v is not None else "")
    # 미치환 변수 → 빈 문자열
    html = re.sub(r"\{\{\s*\w+\s*\}\}", "", html)
    return html


def _generate_pdf_bytes(html_content: str) -> bytes:
    """
    WeasyPrint → xhtml2pdf 순으로 시도.
    둘 다 없으면 ImportError 발생.
    """
    try:
        from weasyprint import HTML as WeasyHTML
        return WeasyHTML(string=html_content, base_url=".").write_pdf()
    except ImportError:
        pass

    try:
        from xhtml2pdf import pisa
        buf = io.BytesIO()
        pisa.CreatePDF(html_content, dest=buf)
        return buf.getvalue()
    except ImportError:
        raise ImportError(
            "PDF 라이브러리 없음 — pip install weasyprint 또는 xhtml2pdf"
        )


# ============================================================
# 1. 서식 목록 / 상세
# ============================================================

@router.get("/templates")
def get_form_templates(
    law_code:  Optional[str] = Query(None, description="법령 코드 (OSHACT)"),
    is_active: bool          = Query(True),
    page:      int           = Query(1, ge=1),
    page_size: int           = Query(20, ge=1, le=100),
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
            "items":     res.data or [],
            "total":     res.count or 0,
            "page":      page,
            "page_size": page_size,
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
# 2. 법적 의무 (legal_obligations) [NEW v2.0]
# ============================================================

@router.get("/obligations")
def get_legal_obligations(
    domain:    Optional[str] = Query(None, description="도메인 (산업안전보건)"),
    oblig_type: Optional[str] = Query(None, alias="type", description="NOTIFICATION/REPORT/PERMIT/INSPECTION/RECORD"),
    page:      int            = Query(1, ge=1),
    page_size: int            = Query(50, ge=1, le=100),
):
    """법적 의무 목록 조회"""
    supabase = get_supabase()
    offset = (page - 1) * page_size

    q = supabase.table("legal_obligations").select("*", count="exact")
    if domain:
        q = q.eq("domain", domain)
    if oblig_type:
        q = q.eq("obligation_type", oblig_type)
    q = q.order("category_code").range(offset, offset + page_size - 1)
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


@router.get("/obligations/by-factory/{factory_id}")
def get_obligations_by_factory(factory_id: str):
    """
    시설별 해당 법적 의무 목록
    - 시설 정보 조회 후 전체 의무 반환 (추후 법령판정 결과와 연동 예정)
    - obligation_form_mapping 함께 반환
    """
    supabase = get_supabase()

    # 시설 정보 확인
    fac_res = supabase.table("factories").select(
        "id, name, ksic_code, worker_count, site_type"
    ).eq("id", factory_id).single().execute()

    if not fac_res.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다")

    fac = fac_res.data

    # 의무 목록 + 연관 서식 매핑
    oblig_res = supabase.table("legal_obligations").select(
        "*, obligation_form_mapping(form_code, form_name, auto_generate, notes)"
    ).eq("status", "ACTIVE_MASTER_DRAFT").order("category_code").execute()

    return {
        "status": "success",
        "data": {
            "factory_id":   factory_id,
            "factory_name": fac.get("name"),
            "ksic_code":    fac.get("ksic_code"),
            "worker_count": fac.get("worker_count"),
            "obligations":  oblig_res.data or [],
            "total":        len(oblig_res.data or [])
        }
    }


# ============================================================
# 3. 신고 이벤트 (D-day 추적)
# ============================================================

@router.get("/events/{factory_id}")
def get_report_events(
    factory_id: str,
    status:         Optional[str] = Query(None, description="PENDING/IN_PROGRESS/COMPLETED/OVERDUE"),
    include_overdue: bool         = Query(True, description="기한 초과 포함 여부"),
):
    """시설의 신고 이벤트 목록 조회"""
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
            item["days_left"]  = days_left
            item["is_overdue"] = days_left < 0
            item["is_urgent"]  = 0 <= days_left <= 7
            item["d_day_label"] = (
                f"D-{abs(days_left)}" if days_left < 0 else
                f"D-{days_left}" if days_left > 0 else "D-Day"
            )
            if item.get("status") == "PENDING" and days_left < 0:
                supabase.table("report_events").update(
                    {"status": "OVERDUE", "updated_at": datetime.now().isoformat()}
                ).eq("id", item["id"]).execute()
                item["status"] = "OVERDUE"

        if not include_overdue and item.get("is_overdue"):
            continue
        result.append(item)

    result.sort(key=lambda x: (
        x.get("status") == "COMPLETED",
        x.get("days_left", 9999)
    ))

    return {
        "status": "success",
        "data": {
            "factory_id":    factory_id,
            "items":         result,
            "total":         len(result),
            "urgent_count":  sum(1 for r in result if r.get("is_urgent") and r.get("status") != "COMPLETED"),
            "overdue_count": sum(1 for r in result if r.get("is_overdue")),
        }
    }


@router.post("/events")
def create_report_event(body: dict):
    """신고 이벤트 생성"""
    supabase = get_supabase()

    factory_id   = body.get("factory_id")
    form_code    = body.get("form_code")
    trigger_date = body.get("trigger_date")

    if not factory_id or not form_code or not trigger_date:
        raise HTTPException(status_code=400, detail="factory_id, form_code, trigger_date 필수")

    due_days = body.get("due_days")
    if not due_days:
        rule_res = supabase.table("master_building_legal_rules").select(
            "due_days"
        ).eq("form_code", form_code).limit(1).execute()
        due_days = (rule_res.data[0]["due_days"]
                    if rule_res.data and rule_res.data[0].get("due_days")
                    else 14)

    trigger = date.fromisoformat(trigger_date)
    due     = trigger + timedelta(days=due_days)

    res = supabase.table("report_events").insert({
        "factory_id":   factory_id,
        "rule_code":    body.get("rule_code"),
        "form_code":    form_code,
        "trigger_date": trigger_date,
        "due_date":     due.isoformat(),
        "status":       "PENDING",
        "created_at":   datetime.now().isoformat(),
        "updated_at":   datetime.now().isoformat(),
    }).execute()

    if not res.data:
        raise HTTPException(status_code=500, detail="이벤트 생성 실패")

    event = res.data[0]
    days_left = (due - date.today()).days
    event["days_left"]   = days_left
    event["d_day_label"] = (f"D-{days_left}" if days_left > 0
                             else ("D-Day" if days_left == 0 else f"D+{abs(days_left)}"))

    return {
        "status":  "success",
        "message": f"신고 이벤트가 생성됐습니다. 마감일: {due.isoformat()} ({event['d_day_label']})",
        "data":    event
    }


@router.patch("/events/{event_id}")
def update_report_event_status(event_id: str, body: dict):
    """이벤트 상태 변경"""
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
# 4. 서류 제출 (form_submissions)
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
    """서류 저장 (서식 작성 완료)"""
    supabase = get_supabase()

    factory_id = body.get("factory_id")
    form_code  = body.get("form_code")
    form_data  = body.get("form_data", {})

    if not factory_id or not form_code:
        raise HTTPException(status_code=400, detail="factory_id, form_code 필수")

    fac_res = supabase.table("factories").select(
        "name, address_road, address_jibun, ksic_code, ksic_name, worker_count, "
        "companies(name, business_number, representative_name)"
    ).eq("id", factory_id).single().execute()

    if fac_res.data:
        fac = fac_res.data
        co  = fac.get("companies") or {}
        auto_filled = {
            "factory_name":        fac.get("name", ""),
            "factory_address":     fac.get("address_road") or fac.get("address_jibun", ""),
            "worker_count":        fac.get("worker_count", ""),
            "company_name":        co.get("name", ""),
            "business_number":     co.get("business_number", ""),
            "representative_name": co.get("representative_name", ""),
        }
        for k, v in auto_filled.items():
            if k not in form_data or not form_data[k]:
                form_data[k] = v

    res = supabase.table("form_submissions").insert({
        "factory_id": factory_id,
        "form_code":  form_code,
        "event_id":   body.get("event_id"),
        "form_data":  form_data,
        "created_by": body.get("created_by"),
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }).execute()

    if not res.data:
        raise HTTPException(status_code=500, detail="서류 저장 실패")

    if body.get("event_id"):
        supabase.table("report_events").update(
            {"status": "IN_PROGRESS", "updated_at": datetime.now().isoformat()}
        ).eq("id", body["event_id"]).eq("status", "PENDING").execute()

    return {"status": "success", "message": "서류가 저장됐습니다.", "data": res.data[0]}


@router.patch("/submissions/{submission_id}")
def update_form_submission(submission_id: str, body: dict):
    """서류 수정"""
    supabase = get_supabase()

    allowed = {"form_data", "pdf_url", "submitted_at"}
    update_data = {k: v for k, v in body.items() if k in allowed}
    update_data["updated_at"] = datetime.now().isoformat()

    if not update_data:
        raise HTTPException(status_code=400, detail="수정할 항목이 없습니다")

    res = supabase.table("form_submissions").update(update_data).eq("id", submission_id).execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="서류를 찾을 수 없습니다")

    if "submitted_at" in update_data:
        sub = res.data[0]
        if sub.get("event_id"):
            supabase.table("report_events").update(
                {"status": "COMPLETED", "completed_at": datetime.now().isoformat(),
                 "updated_at": datetime.now().isoformat()}
            ).eq("id", sub["event_id"]).execute()

    return {"status": "success", "message": "서류가 수정됐습니다.", "data": res.data[0]}


# ============================================================
# 5. PDF 생성 [NEW v2.0]
# ============================================================

@router.post("/submissions/preview-pdf")
def preview_pdf(body: dict = Body(...)):
    """
    즉시 PDF 스트림 반환 (DB 저장 없음)
    body: { form_code, form_data: { ... } }
    """
    form_code = body.get("form_code", "OSHACT-FORM-002")
    form_data = body.get("form_data", {})

    template_path = TEMPLATE_MAP.get(form_code)
    if not template_path:
        raise HTTPException(status_code=404, detail=f"템플릿 없음: {form_code}")

    html_content = _render_html_template(template_path, form_data)

    try:
        pdf_bytes = _generate_pdf_bytes(html_content)
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{form_code}_preview.pdf"'}
        )
    except ImportError as e:
        # PDF 라이브러리 미설치 시 HTML 반환 (개발 환경 대비)
        return JSONResponse({
            "status":  "html_only",
            "message": str(e),
            "html":    html_content[:1000] + "..."
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF 생성 실패: {str(e)}")


@router.post("/submissions/{submission_id}/pdf")
def generate_and_save_pdf(submission_id: str):
    """
    저장된 서류 PDF 생성 → pdf_url DB 업데이트 → PDF 스트림 반환
    """
    supabase = get_supabase()

    res = supabase.table("form_submissions").select(
        "*, form_templates(form_code, form_json)"
    ).eq("id", submission_id).single().execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="서류를 찾을 수 없습니다")

    sub       = res.data
    form_code = sub.get("form_code", "OSHACT-FORM-002")
    form_data = sub.get("form_data", {})

    template_path = TEMPLATE_MAP.get(form_code)
    if not template_path:
        raise HTTPException(status_code=404, detail=f"템플릿 없음: {form_code}")

    html_content = _render_html_template(template_path, form_data)

    try:
        pdf_bytes = _generate_pdf_bytes(html_content)

        # pdf_url 업데이트 (Supabase Storage 연동 전 임시값)
        pdf_url = f"generated/{form_code}_{submission_id}.pdf"
        supabase.table("form_submissions").update(
            {"pdf_url": pdf_url, "updated_at": datetime.now().isoformat()}
        ).eq("id", submission_id).execute()

        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{form_code}_{submission_id}.pdf"'}
        )
    except ImportError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF 생성 실패: {str(e)}")


# ============================================================
# 6. 대시보드 요약
# ============================================================

@router.get("/dashboard/{factory_id}")
def get_report_dashboard(factory_id: str):
    """tadmin 대시보드용 신고 현황 요약"""
    supabase = get_supabase()

    res = supabase.table("report_events").select(
        "id, form_code, due_date, status, "
        "form_templates(form_name, submit_to)"
    ).eq("factory_id", factory_id).neq("status", "COMPLETED").execute()

    items = res.data or []
    today = date.today()

    urgent   = []
    upcoming = []
    overdue  = []

    for item in items:
        due = item.get("due_date")
        if not due:
            continue
        d = date.fromisoformat(due)
        days_left = (d - today).days
        item["days_left"]   = days_left
        item["d_day_label"] = (
            f"D+{abs(days_left)}" if days_left < 0 else
            f"D-{days_left}"      if days_left > 0 else "D-Day"
        )
        if days_left < 0:
            overdue.append(item)
        elif days_left <= 7:
            urgent.append(item)
        elif days_left <= 30:
            upcoming.append(item)

    completed_res = supabase.table("report_events").select(
        "id", count="exact"
    ).eq("factory_id", factory_id).eq("status", "COMPLETED").execute()

    return {
        "status": "success",
        "data": {
            "factory_id": factory_id,
            "urgent":     sorted(urgent,   key=lambda x: x["days_left"]),
            "upcoming":   sorted(upcoming, key=lambda x: x["days_left"]),
            "overdue":    sorted(overdue,  key=lambda x: x["days_left"]),
            "summary": {
                "urgent_count":    len(urgent),
                "upcoming_count":  len(upcoming),
                "overdue_count":   len(overdue),
                "completed_count": completed_res.count or 0,
            }
        }
    }


# ============================================================
# 7. 헬스체크
# ============================================================

@router.get("/test")
def test():
    return {"status": "ok", "message": "report-forms API v2.0.0"}
