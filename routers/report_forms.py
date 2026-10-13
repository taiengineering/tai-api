# routers/report_forms.py v2.2.0
# v2.2.0: WP-SEC0-A — 전 엔드포인트 인증·테넌트 소유권 게이트 추가
#   - get_current_user Depends 전 엔드포인트 적용
#   - factory 경로: _ensure_factory_own 으로 소유권 검증
#   - submission/event 경로: DB에서 factory_id 조회 후 소유권 검증
#   - upload_html_template: ALL 어드민 전용
#   - create_form_submission: created_by 토큰 강제 주입
# v2.1.0: Supabase 스토리지 분리 적용
#   - HTML 템플릿: GitHub filesystem → form-templates 버킷 (동적 로드)
#   - PDF 출력물: form-outputs 버킷 업로드 후 signed URL 반환
#   - TEMPLATE_MAP 하드코딩 → DB html_storage_path 우선, 로컬 fallback
# v2.0.2: WeasyPrint → xhtml2pdf 전환
#
# 버킷 구조:
#   form-originals/{form_code}/original.hwp  — HWP 원본
#   form-templates/{form_code}/template.html — HTML 변환본
#   form-outputs/{factory_id}/{submission_id}.pdf — 생성 PDF
#
# 엔드포인트:
#   GET  /report-forms/templates
#   GET  /report-forms/templates/{form_code}
#   GET  /report-forms/obligations
#   GET  /report-forms/obligations/by-factory/{factory_id}
#   GET  /report-forms/events/{factory_id}
#   POST /report-forms/events
#   PATCH /report-forms/events/{event_id}
#   GET  /report-forms/submissions/{factory_id}
#   GET  /report-forms/submissions/detail/{id}
#   POST /report-forms/submissions
#   PATCH /report-forms/submissions/{id}
#   POST /report-forms/submissions/preview-pdf
#   POST /report-forms/submissions/{id}/pdf
#   GET  /report-forms/storage/signed-url/{submission_id}
#   POST /report-forms/storage/upload-template
#   GET  /report-forms/dashboard/{factory_id}
#   GET  /report-forms/test

from fastapi import APIRouter, HTTPException, Query, Body, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from typing import Optional
from datetime import datetime, date, timedelta
from pathlib import Path
import os, io, re
from supabase import create_client
from routers.auth import get_current_user
from services.company_scope import _ensure_factory_own, _ensure_own_company, _require_admin
from services.time import business_today, now_kst, serialize_business_datetime

router = APIRouter(prefix="/report-forms", tags=["신고서식"])

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# 로컬 fallback — storage에 없을 때 GitHub 파일로 대체
# 신규 서식은 form-templates 버킷에만 올리면 자동 인식됨
LOCAL_TEMPLATE_FALLBACK = {
    "OSHACT-FORM-002": "templates/forms/OSHACT_FORM_002.html",
}

BUCKET_TEMPLATES = "form-templates"
BUCKET_OUTPUTS   = "form-outputs"
BUCKET_ORIGINALS = "form-originals"


def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ============================================================
# 템플릿 로드 (스토리지 우선 → 로컬 fallback)
# ============================================================

def _load_html_template(form_code: str) -> str:
    """
    우선순위:
    1) form_templates.html_storage_path → form-templates 버킷에서 다운로드
    2) LOCAL_TEMPLATE_FALLBACK → 로컬 파일 읽기
    """
    supabase = get_supabase()

    # 1) DB에서 storage path 확인
    try:
        res = supabase.table("form_templates").select(
            "html_storage_path"
        ).eq("form_code", form_code).eq("is_active", True).maybe_single().execute()

        if res.data and res.data.get("html_storage_path"):
            storage_path = res.data["html_storage_path"]
            file_bytes = supabase.storage.from_(BUCKET_TEMPLATES).download(storage_path)
            return file_bytes.decode("utf-8")
    except Exception:
        pass  # storage 실패 시 fallback으로

    # 2) 로컬 fallback
    local_path = LOCAL_TEMPLATE_FALLBACK.get(form_code)
    if local_path and Path(local_path).exists():
        return Path(local_path).read_text(encoding="utf-8")

    raise HTTPException(status_code=404, detail=f"HTML 템플릿 없음: {form_code}. form-templates 버킷에 {form_code}/template.html 을 업로드하세요.")


def _render_html(html: str, form_data: dict) -> str:
    """{{ key }} 치환으로 HTML 렌더링"""
    for k, v in form_data.items():
        html = html.replace("{{ " + k + " }}", str(v) if v is not None else "")
    html = re.sub(r"\{\{\s*\w+\s*\}\}", "", html)
    return html


def _generate_pdf_bytes(html_content: str) -> bytes:
    """xhtml2pdf (순수 Python) — 한글 UTF-8 지원"""
    try:
        from xhtml2pdf import pisa
        buf = io.BytesIO()
        pisa_status = pisa.CreatePDF(io.StringIO(html_content), dest=buf, encoding="UTF-8")
        if pisa_status.err:
            raise RuntimeError(f"xhtml2pdf 오류: {pisa_status.err}")
        return buf.getvalue()
    except ImportError:
        raise ImportError("xhtml2pdf 미설치 — pip install xhtml2pdf")


def _upload_pdf_to_storage(supabase, factory_id: str, submission_id: str, pdf_bytes: bytes) -> str:
    """
    form-outputs/{factory_id}/{submission_id}.pdf 업로드.
    반환: 버킷 내 경로 (storage_path)
    """
    storage_path = f"{factory_id}/{submission_id}.pdf"
    supabase.storage.from_(BUCKET_OUTPUTS).upload(
        path=storage_path,
        file=pdf_bytes,
        file_options={"content-type": "application/pdf", "upsert": "true"},
    )
    return storage_path


def _get_signed_url(supabase, storage_path: str, expires_in: int = 3600) -> str:
    """form-outputs 버킷 signed URL (1시간 유효)"""
    res = supabase.storage.from_(BUCKET_OUTPUTS).create_signed_url(storage_path, expires_in)
    return res.get("signedURL") or res.get("signedUrl", "")


def _fetch_submission_factory_id(supabase, submission_id: str) -> str:
    """form_submissions에서 factory_id 조회. 미존재 시 404."""
    res = supabase.table("form_submissions").select("factory_id").eq(
        "id", submission_id
    ).single().execute()
    if not res.data or not res.data.get("factory_id"):
        raise HTTPException(status_code=404, detail="서류를 찾을 수 없습니다")
    return res.data["factory_id"]


def _fetch_event_factory_id(supabase, event_id: str) -> str:
    """report_events에서 factory_id 조회. 미존재 시 404."""
    res = supabase.table("report_events").select("factory_id").eq(
        "id", event_id
    ).single().execute()
    if not res.data or not res.data.get("factory_id"):
        raise HTTPException(status_code=404, detail="이벤트를 찾을 수 없습니다")
    return res.data["factory_id"]


# ============================================================
# 스토리지 관리 엔드포인트
# ============================================================

@router.get("/storage/signed-url/{submission_id}")
def get_pdf_signed_url(
    submission_id: str,
    expires_in: int = Query(3600, ge=60, le=86400),
    current_user: dict = Depends(get_current_user),
):
    """저장된 서류 PDF의 임시 다운로드 URL 발급 (기본 1시간)"""
    supabase = get_supabase()
    res = supabase.table("form_submissions").select(
        "factory_id, pdf_url, form_code"
    ).eq("id", submission_id).single().execute()
    if not res.data or not res.data.get("pdf_url"):
        raise HTTPException(status_code=404, detail="PDF가 없습니다. 먼저 PDF를 생성하세요.")

    sub = res.data
    _ensure_factory_own(supabase, sub["factory_id"], current_user)

    pdf_url = sub["pdf_url"]
    # 외부 HTTP URL: 레거시 보존 — 더 이상 신규 설정 불가 (PATCH pdf_url 차단)
    if pdf_url.startswith("http"):
        return {"status": "success", "url": pdf_url, "type": "external"}

    # Storage 경로 prefix가 소유 사업장과 일치하는지 검증 (P0-03)
    path_prefix = pdf_url.split("/")[0] if "/" in pdf_url else None
    if path_prefix != sub["factory_id"]:
        raise HTTPException(status_code=403, detail="PDF 경로가 유효하지 않습니다")

    signed = _get_signed_url(supabase, pdf_url, expires_in)
    return {
        "status": "success",
        "url": signed,
        "type": "storage",
        "expires_in": expires_in,
        "storage_path": pdf_url,
    }


@router.post("/storage/upload-template")
def upload_html_template(
    body: dict = Body(...),
    current_user: dict = Depends(get_current_user),
):
    """
    HTML 템플릿을 form-templates 버킷에 업로드.
    body: { form_code, html_content }
    경로: {form_code}/template.html
    플랫폼 어드민(ALL scope) 전용.
    """
    supabase = get_supabase()
    _require_admin(current_user, supabase)

    form_code    = body.get("form_code")
    html_content = body.get("html_content")
    if not form_code or not html_content:
        raise HTTPException(status_code=400, detail="form_code, html_content 필수")

    storage_path = f"{form_code}/template.html"

    supabase.storage.from_(BUCKET_TEMPLATES).upload(
        path=storage_path,
        file=html_content.encode("utf-8"),
        file_options={"content-type": "text/html; charset=utf-8", "upsert": "true"},
    )

    # form_templates DB에 경로 업데이트
    supabase.table("form_templates").update({
        "html_storage_path": storage_path,
        "updated_at": serialize_business_datetime(now_kst()),
    }).eq("form_code", form_code).execute()

    return {
        "status": "success",
        "message": f"form-templates/{storage_path} 업로드 완료",
        "storage_path": storage_path,
    }


# ============================================================
# 1. 서식 목록 / 상세
# ============================================================

@router.get("/templates")
def get_form_templates(
    law_code:  Optional[str] = Query(None),
    is_active: bool          = Query(True),
    page:      int           = Query(1, ge=1),
    page_size: int           = Query(20, ge=1, le=100),
    current_user: dict       = Depends(get_current_user),
):
    """서식 템플릿 목록 조회"""
    supabase = get_supabase()
    offset = (page - 1) * page_size

    q = supabase.table("form_templates").select(
        "id, form_code, form_no, form_name, law_code, "
        "submit_to, submit_timing, trigger_event, bylseq, "
        "hwp_url, html_storage_path, original_storage_path, is_active",
        count="exact"
    ).eq("is_active", is_active)

    if law_code:
        q = q.eq("law_code", law_code)

    q = q.order("form_code").range(offset, offset + page_size - 1)
    res = q.execute()

    # 템플릿 준비 여부 플래그 추가
    items = res.data or []
    for item in items:
        item["has_html_template"] = bool(
            item.get("html_storage_path") or
            item.get("form_code") in LOCAL_TEMPLATE_FALLBACK
        )

    return {
        "status": "success",
        "data": {
            "items":     items,
            "total":     res.count or 0,
            "page":      page,
            "page_size": page_size,
        }
    }


@router.get("/templates/{form_code}")
def get_form_template(
    form_code: str,
    current_user: dict = Depends(get_current_user),
):
    """서식 템플릿 상세 조회"""
    supabase = get_supabase()
    res = supabase.table("form_templates").select("*").eq(
        "form_code", form_code
    ).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="서식을 찾을 수 없습니다")
    data = res.data
    data["has_html_template"] = bool(
        data.get("html_storage_path") or form_code in LOCAL_TEMPLATE_FALLBACK
    )
    return {"status": "success", "data": data}


# ============================================================
# 2. 법적 의무
# ============================================================

@router.get("/obligations")
def get_legal_obligations(
    domain:     Optional[str] = Query(None),
    oblig_type: Optional[str] = Query(None, alias="type"),
    page:       int           = Query(1, ge=1),
    page_size:  int           = Query(50, ge=1, le=100),
    current_user: dict        = Depends(get_current_user),
):
    supabase = get_supabase()
    offset = (page - 1) * page_size
    q = supabase.table("legal_obligations").select("*", count="exact")
    if domain:      q = q.eq("domain", domain)
    if oblig_type:  q = q.eq("obligation_type", oblig_type)
    q = q.order("category_code").range(offset, offset + page_size - 1)
    res = q.execute()
    return {
        "status": "success",
        "data": {"items": res.data or [], "total": res.count or 0,
                 "page": page, "page_size": page_size}
    }


@router.get("/obligations/by-factory/{factory_id}")
def get_obligations_by_factory(
    factory_id: str,
    current_user: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current_user)

    fac_res = supabase.table("factories").select(
        "id, name, ksic_code, worker_count, site_type"
    ).eq("id", factory_id).single().execute()
    if not fac_res.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다")
    fac = fac_res.data
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
# 3. 신고 이벤트
# ============================================================

@router.get("/events/{factory_id}")
def get_report_events(
    factory_id:      str,
    status:          Optional[str] = Query(None),
    include_overdue: bool          = Query(True),
    current_user:    dict          = Depends(get_current_user),
):
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current_user)

    q = supabase.table("report_events").select(
        "*, form_templates(form_code, form_name, submit_to, submit_timing)"
    ).eq("factory_id", factory_id)
    if status: q = q.eq("status", status)
    q = q.order("due_date")
    res = q.execute()
    items = res.data or []
    today = business_today()
    result = []
    for item in items:
        due = item.get("due_date")
        if due:
            d = date.fromisoformat(due)
            days_left = (d - today).days
            item["days_left"]   = days_left
            item["is_overdue"]  = days_left < 0
            item["is_urgent"]   = 0 <= days_left <= 7
            item["d_day_label"] = (
                f"D-{abs(days_left)}" if days_left < 0 else
                f"D-{days_left}"      if days_left > 0 else "D-Day"
            )
            if item.get("status") == "PENDING" and days_left < 0:
                supabase.table("report_events").update(
                    {"status": "OVERDUE", "updated_at": serialize_business_datetime(now_kst())}
                ).eq("id", item["id"]).execute()
                item["status"] = "OVERDUE"
        if not include_overdue and item.get("is_overdue"):
            continue
        result.append(item)
    result.sort(key=lambda x: (x.get("status") == "COMPLETED", x.get("days_left", 9999)))
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
def create_report_event(
    body: dict,
    current_user: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    factory_id   = body.get("factory_id")
    form_code    = body.get("form_code")
    trigger_date = body.get("trigger_date")
    if not factory_id or not form_code or not trigger_date:
        raise HTTPException(status_code=400, detail="factory_id, form_code, trigger_date 필수")

    _ensure_factory_own(supabase, factory_id, current_user)

    due_days = body.get("due_days")
    if not due_days:
        rule_res = supabase.table("master_building_legal_rules").select(
            "due_days"
        ).eq("form_code", form_code).limit(1).execute()
        due_days = (rule_res.data[0]["due_days"]
                    if rule_res.data and rule_res.data[0].get("due_days") else 14)
    trigger = date.fromisoformat(trigger_date)
    due     = trigger + timedelta(days=due_days)
    res = supabase.table("report_events").insert({
        "factory_id":   factory_id,
        "rule_code":    body.get("rule_code"),
        "form_code":    form_code,
        "trigger_date": trigger_date,
        "due_date":     due.isoformat(),
        "status":       "PENDING",
        "created_at":   serialize_business_datetime(now_kst()),
        "updated_at":   serialize_business_datetime(now_kst()),
    }).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="이벤트 생성 실패")
    event = res.data[0]
    days_left = (due - business_today()).days
    event["days_left"]   = days_left
    event["d_day_label"] = (f"D-{days_left}" if days_left > 0
                             else ("D-Day" if days_left == 0 else f"D+{abs(days_left)}"))
    return {"status": "success",
            "message": f"신고 이벤트 생성. 마감일: {due.isoformat()} ({event['d_day_label']})",
            "data": event}


@router.patch("/events/{event_id}")
def update_report_event_status(
    event_id: str,
    body: dict,
    current_user: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    event_factory_id = _fetch_event_factory_id(supabase, event_id)
    _ensure_factory_own(supabase, event_factory_id, current_user)

    allowed_status = {"PENDING", "IN_PROGRESS", "COMPLETED", "OVERDUE"}
    status = body.get("status")
    if status and status not in allowed_status:
        raise HTTPException(status_code=400, detail=f"status는 {allowed_status} 중 하나")
    update_data = {"updated_at": serialize_business_datetime(now_kst())}
    if status: update_data["status"] = status
    if status == "COMPLETED": update_data["completed_at"] = serialize_business_datetime(now_kst())
    res = supabase.table("report_events").update(update_data).eq("id", event_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="이벤트를 찾을 수 없습니다")
    return {"status": "success", "message": "이벤트 상태 변경됨", "data": res.data[0]}


# ============================================================
# 4. 서류 제출
# ============================================================

@router.get("/submissions/{factory_id}")
def get_form_submissions(
    factory_id: str,
    form_code:  Optional[str] = Query(None),
    page:       int           = Query(1, ge=1),
    page_size:  int           = Query(20, ge=1, le=100),
    current_user: dict        = Depends(get_current_user),
):
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current_user)

    offset = (page - 1) * page_size
    q = supabase.table("form_submissions").select(
        "id, factory_id, form_code, event_id, pdf_url, submitted_at, created_at, "
        "form_templates(form_name, form_no)",
        count="exact"
    ).eq("factory_id", factory_id)
    if form_code: q = q.eq("form_code", form_code)
    q = q.order("created_at", desc=True).range(offset, offset + page_size - 1)
    res = q.execute()
    return {"status": "success",
            "data": {"items": res.data or [], "total": res.count or 0,
                     "page": page, "page_size": page_size}}


@router.get("/submissions/detail/{submission_id}")
def get_form_submission(
    submission_id: str,
    current_user: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    res = supabase.table("form_submissions").select(
        "*, form_templates(form_name, form_no, form_json, submit_to)"
    ).eq("id", submission_id).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="서류를 찾을 수 없습니다")

    _ensure_factory_own(supabase, res.data["factory_id"], current_user)

    return {"status": "success", "data": res.data}


@router.post("/submissions")
def create_form_submission(
    body: dict,
    current_user: dict = Depends(get_current_user),
):
    supabase   = get_supabase()
    factory_id = body.get("factory_id")
    form_code  = body.get("form_code")
    form_data  = body.get("form_data", {})
    if not factory_id or not form_code:
        raise HTTPException(status_code=400, detail="factory_id, form_code 필수")

    _ensure_factory_own(supabase, factory_id, current_user)

    # 사업장 기본정보 자동채움
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
            if k not in form_data or not form_data[k]: form_data[k] = v

    event_id = body.get("event_id")
    if event_id:
        # event_id 소유권 검증: 같은 사업장 소유인지 확인
        ev_check = supabase.table("report_events").select("factory_id, form_code").eq(
            "id", event_id
        ).single().execute()
        if not ev_check.data:
            raise HTTPException(status_code=404, detail="이벤트를 찾을 수 없습니다")
        if ev_check.data.get("factory_id") != factory_id:
            raise HTTPException(status_code=404, detail="이벤트를 찾을 수 없습니다")

    res = supabase.table("form_submissions").insert({
        "factory_id": factory_id, "form_code": form_code,
        "event_id":   event_id, "form_data": form_data,
        "created_by": current_user.get("id"),
        "created_at": serialize_business_datetime(now_kst()),
        "updated_at": serialize_business_datetime(now_kst()),
    }).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="서류 저장 실패")
    if event_id:
        supabase.table("report_events").update(
            {"status": "IN_PROGRESS", "updated_at": serialize_business_datetime(now_kst())}
        ).eq("id", event_id).eq("factory_id", factory_id).eq("status", "PENDING").execute()
    return {"status": "success", "message": "서류 저장됨", "data": res.data[0]}


@router.patch("/submissions/{submission_id}")
def update_form_submission(
    submission_id: str,
    body: dict,
    current_user: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    sub_factory_id = _fetch_submission_factory_id(supabase, submission_id)
    _ensure_factory_own(supabase, sub_factory_id, current_user)

    # pdf_url 제거: 서버 전용 관리 필드 — 클라이언트 수정 금지 (P0-03)
    allowed  = {"form_data", "submitted_at"}
    filtered = {k: v for k, v in body.items() if k in allowed}
    if not filtered:
        raise HTTPException(status_code=400, detail="수정할 항목 없음")
    filtered["updated_at"] = serialize_business_datetime(now_kst())
    res = supabase.table("form_submissions").update(filtered).eq("id", submission_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="서류를 찾을 수 없습니다")
    if "submitted_at" in filtered:
        sub = res.data[0]
        if sub.get("event_id"):
            # event 소유권 재확인 후 COMPLETED 처리 (P0-02)
            ev_chk = supabase.table("report_events").select("factory_id").eq(
                "id", sub["event_id"]
            ).single().execute()
            if ev_chk.data and ev_chk.data.get("factory_id") == sub_factory_id:
                supabase.table("report_events").update(
                    {"status": "COMPLETED",
                     "completed_at": serialize_business_datetime(now_kst()),
                     "updated_at": serialize_business_datetime(now_kst())}
                ).eq("id", sub["event_id"]).eq("factory_id", sub_factory_id).execute()
    return {"status": "success", "message": "서류 수정됨", "data": res.data[0]}


# ============================================================
# 5. PDF 생성 (스토리지 업로드 포함)
# ============================================================

@router.post("/submissions/preview-pdf")
def preview_pdf(
    body: dict = Body(...),
    current_user: dict = Depends(get_current_user),
):
    """즉시 PDF 스트림 반환 (DB·스토리지 저장 없음)"""
    form_code = body.get("form_code", "OSHACT-FORM-002")
    form_data = body.get("form_data", {})

    html_raw     = _load_html_template(form_code)
    html_content = _render_html(html_raw, form_data)

    try:
        pdf_bytes = _generate_pdf_bytes(html_content)
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{form_code}_preview.pdf"'}
        )
    except ImportError as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=501)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF 생성 실패: {str(e)}")


@router.post("/submissions/{submission_id}/pdf")
def generate_and_save_pdf(
    submission_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    저장된 서류 → PDF 생성 → form-outputs 버킷 업로드
    → form_submissions.pdf_url 업데이트 (버킷 내 경로)
    → PDF 스트림 반환
    """
    supabase = get_supabase()
    res = supabase.table("form_submissions").select(
        "factory_id, form_code, form_data"
    ).eq("id", submission_id).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="서류를 찾을 수 없습니다")

    sub        = res.data
    _ensure_factory_own(supabase, sub["factory_id"], current_user)

    form_code  = sub.get("form_code", "OSHACT-FORM-002")
    form_data  = sub.get("form_data", {})
    factory_id = sub.get("factory_id", "unknown")

    html_raw     = _load_html_template(form_code)
    html_content = _render_html(html_raw, form_data)

    try:
        pdf_bytes    = _generate_pdf_bytes(html_content)
        storage_path = _upload_pdf_to_storage(supabase, factory_id, submission_id, pdf_bytes)

        # pdf_url을 버킷 내 경로로 저장 (외부 URL 아님)
        supabase.table("form_submissions").update({
            "pdf_url":    storage_path,
            "updated_at": serialize_business_datetime(now_kst()),
        }).eq("id", submission_id).execute()

        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{form_code}_{submission_id}.pdf"'}
        )
    except ImportError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF 생성/업로드 실패: {str(e)}")


# ============================================================
# 6. 대시보드
# ============================================================

@router.get("/dashboard/{factory_id}")
def get_report_dashboard(
    factory_id: str,
    current_user: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current_user)

    res = supabase.table("report_events").select(
        "id, form_code, due_date, status, form_templates(form_name, submit_to)"
    ).eq("factory_id", factory_id).neq("status", "COMPLETED").execute()
    items = res.data or []
    today = business_today()
    urgent, upcoming, overdue = [], [], []
    for item in items:
        due = item.get("due_date")
        if not due: continue
        d = date.fromisoformat(due)
        days_left = (d - today).days
        item["days_left"]   = days_left
        item["d_day_label"] = (
            f"D+{abs(days_left)}" if days_left < 0 else
            f"D-{days_left}"      if days_left > 0 else "D-Day"
        )
        if days_left < 0:        overdue.append(item)
        elif days_left <= 7:     urgent.append(item)
        elif days_left <= 30:    upcoming.append(item)
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


@router.get("/test")
def test(current_user: dict = Depends(get_current_user)):
    return {
        "status": "ok",
        "message": "report-forms API v2.2.0 (SEC0 auth hardened)",
        "buckets": {
            "originals":  BUCKET_ORIGINALS,
            "templates":  BUCKET_TEMPLATES,
            "outputs":    BUCKET_OUTPUTS,
        },
        "local_fallback": list(LOCAL_TEMPLATE_FALLBACK.keys()),
    }
