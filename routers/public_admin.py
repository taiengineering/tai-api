"""
비회원 법령진단 신청 관리 API
URL prefix: /admin/public-diagnosis-requests
인증: 필요 (tadmin 토큰)
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime, timezone

from db.supabase_client import get_supabase

router = APIRouter(prefix="/admin/public-diagnosis-requests", tags=["관리 - 비회원진단"])

STATUS_LABELS = {
    "NEW": "신규",
    "IN_PROGRESS": "분석 중",
    "DONE": "완료",
    "CANCELLED": "취소",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ──────────────────────────────────────────────────────────────
# GET /admin/public-diagnosis-requests — 목록
# ──────────────────────────────────────────────────────────────

@router.get("")
def list_requests(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    request_type: Optional[str] = None,
    status_code:  Optional[str] = None,
    search:       Optional[str] = None,
):
    supabase = get_supabase()
    offset = (page - 1) * size

    q = supabase.table("public_diagnosis_requests") \
        .select(
            "id, request_no, request_type, company_name, biz_no, address, "
            "contact_name, contact_phone, contact_email, sector, "
            "facility_data, process_data, equipment_data, memo, source, "
            "status_code, admin_memo, result_html, result_pdf_url, "
            "result_sent_at, created_at, updated_at",
            count="exact"
        ) \
        .eq("is_active", True)

    if request_type:
        q = q.eq("request_type", request_type)
    if status_code:
        q = q.eq("status_code", status_code)
    if search:
        q = q.or_(f"company_name.ilike.%{search}%,request_no.ilike.%{search}%,contact_name.ilike.%{search}%")

    q = q.order("created_at", desc=True).range(offset, offset + size - 1)
    res = q.execute()

    return {
        "status": "success",
        "data": {
            "items": res.data or [],
            "total": res.count or 0,
            "page": page,
            "size": size,
        },
    }


# ──────────────────────────────────────────────────────────────
# GET /admin/public-diagnosis-requests/stats — 요약 통계
# ──────────────────────────────────────────────────────────────

@router.get("/stats")
def get_stats():
    supabase = get_supabase()
    res = supabase.table("public_diagnosis_requests") \
        .select("status_code, request_type") \
        .eq("is_active", True) \
        .execute()
    rows = res.data or []
    return {
        "status": "success",
        "data": {
            "total":       len(rows),
            "new":         sum(1 for r in rows if r["status_code"] == "NEW"),
            "in_progress": sum(1 for r in rows if r["status_code"] == "IN_PROGRESS"),
            "done":        sum(1 for r in rows if r["status_code"] == "DONE"),
            "cancelled":   sum(1 for r in rows if r["status_code"] == "CANCELLED"),
            "v1":          sum(1 for r in rows if r["request_type"] == "v1"),
            "v2":          sum(1 for r in rows if r["request_type"] == "v2"),
            "v3":          sum(1 for r in rows if r["request_type"] == "v3"),
        },
    }


# ──────────────────────────────────────────────────────────────
# GET /admin/public-diagnosis-requests/{id} — 상세
# ──────────────────────────────────────────────────────────────

@router.get("/{req_id}")
def get_request(req_id: str):
    supabase = get_supabase()
    res = supabase.table("public_diagnosis_requests") \
        .select("*") \
        .eq("id", req_id) \
        .eq("is_active", True) \
        .limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="신청을 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}


# ──────────────────────────────────────────────────────────────
# PATCH /admin/public-diagnosis-requests/{id}/status — 상태 변경
# ──────────────────────────────────────────────────────────────

class StatusUpdateBody(BaseModel):
    status_code: str
    admin_memo:  Optional[str] = None


@router.patch("/{req_id}/status")
def update_status(req_id: str, body: StatusUpdateBody):
    if body.status_code not in STATUS_LABELS:
        raise HTTPException(status_code=422, detail=f"status_code는 {list(STATUS_LABELS.keys())} 중 하나여야 합니다.")
    supabase = get_supabase()
    update = {"status_code": body.status_code, "updated_at": _now()}
    if body.admin_memo is not None:
        update["admin_memo"] = body.admin_memo
    res = supabase.table("public_diagnosis_requests") \
        .update(update).eq("id", req_id).execute()
    return {"status": "success", "data": res.data[0] if res.data else {}}


# ──────────────────────────────────────────────────────────────
# POST /admin/public-diagnosis-requests/{id}/run-diagnosis
# 법령진단 엔진 실행 → diagnosis_result 저장
# ──────────────────────────────────────────────────────────────

@router.post("/{req_id}/run-diagnosis")
def run_diagnosis(req_id: str):
    supabase = get_supabase()

    # 신청 조회
    res = supabase.table("public_diagnosis_requests") \
        .select("*").eq("id", req_id).eq("is_active", True).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="신청을 찾을 수 없습니다.")
    req = res.data[0]

    sector          = req.get("sector") or "BUILDING"
    facility_data   = req.get("facility_data") or {}
    request_type    = req.get("request_type", "v1")

    # 법령진단 step1 실행 (내부 호출)
    try:
        from routers.legal_engine import (
            _input_to_facility_context,
            _evaluate_facility_conditions_db,
            _classify_rules_db,
            _resolve_obligation_type,
            _get_construction_summary,
            ENGINE_VERSION,
        )
        from datetime import datetime

        # 1단계 진단
        all_rules_res = supabase.table("master_building_legal_rules") \
            .select("*").eq("is_active", True).eq("sector", sector).eq("diagnosis_stage", 1).execute()
        all_rules = all_rules_res.data or []

        inp = dict(facility_data)
        facility_ctx = _input_to_facility_context(sector, inp)
        applicable, not_applicable = _evaluate_facility_conditions_db(facility_ctx, all_rules, sector)

        triggered: Dict[str, list] = {
            "appointment": [], "inspection": [], "notify": [], "report": [], "action": [],
        }
        _classify_rules_db(applicable, triggered)

        total = sum(len(triggered[k]) for k in triggered)

        diagnosis_result = {
            "engine_version":  ENGINE_VERSION,
            "sector":          sector,
            "request_type":    request_type,
            "evaluated_at":    datetime.now().isoformat(),
            "applicable_count": total,
            "summary": {
                "total":       total,
                "appointment": len(triggered["appointment"]),
                "inspection":  len(triggered["inspection"]),
                "action":      len(triggered["action"]),
                "report":      len(triggered["report"]),
                "notify":      len(triggered["notify"]),
            },
            "appointment_required": triggered["appointment"],
            "inspection_required":  triggered["inspection"],
            "action_required":      triggered["action"],
            "report_required":      triggered["report"],
            "notify_required":      triggered["notify"],
        }

        if sector == "CONSTRUCTION":
            diagnosis_result["construction_summary"] = _get_construction_summary(facility_ctx)

        # 결과 HTML 자동 생성
        result_html = _build_result_html(req, diagnosis_result)

        supabase.table("public_diagnosis_requests").update({
            "diagnosis_result": diagnosis_result,
            "result_html":      result_html,
            "status_code":      "IN_PROGRESS",
            "updated_at":       _now(),
        }).eq("id", req_id).execute()

        return {
            "status":  "success",
            "message": f"법령진단 완료 — {total}건 적용",
            "data":    diagnosis_result,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"진단 실행 오류: {str(e)}")


def _build_result_html(req: dict, result: dict) -> str:
    """진단 결과를 편집 가능한 HTML로 변환"""
    company = req.get("company_name", "")
    sector  = req.get("sector", "")
    summary = result.get("summary", {})
    cs      = result.get("construction_summary", {})
    today   = datetime.now().strftime("%Y년 %m월 %d일")

    def rows_html(rules: list, category: str) -> str:
        if not rules:
            return ""
        html = f'<h3 style="color:#0d6efd;border-bottom:2px solid #0d6efd;padding-bottom:4px">{category}</h3><table style="width:100%;border-collapse:collapse;margin-bottom:16px"><thead><tr style="background:#f0f6ff"><th style="padding:6px;border:1px solid #dee2e6;text-align:left">법령명</th><th style="padding:6px;border:1px solid #dee2e6">조문</th><th style="padding:6px;border:1px solid #dee2e6">의무 내용</th><th style="padding:6px;border:1px solid #dee2e6">벌칙</th></tr></thead><tbody>'
        for r in rules:
            html += f'<tr><td style="padding:6px;border:1px solid #dee2e6">{r.get("law_name","")}</td><td style="padding:6px;border:1px solid #dee2e6;white-space:nowrap">{r.get("law_article","")}</td><td style="padding:6px;border:1px solid #dee2e6">{r.get("obligation_summary") or r.get("description","")}</td><td style="padding:6px;border:1px solid #dee2e6;font-size:0.85em">{r.get("penalty_summary","")}</td></tr>'
        html += '</tbody></table>'
        return html

    html = f"""<div style="font-family:'Noto Sans KR',sans-serif;max-width:900px;margin:0 auto;padding:24px">
<div style="text-align:center;margin-bottom:32px">
  <h1 style="color:#1a1f36;font-size:1.8rem">산업안전 법령진단 결과보고서</h1>
  <p style="color:#6c757d">{today} &nbsp;|&nbsp; TAI Engineering</p>
</div>

<table style="width:100%;border-collapse:collapse;margin-bottom:24px">
  <tr style="background:#f8f9fa"><td style="padding:8px 12px;font-weight:600;width:25%;border:1px solid #dee2e6">회사명</td><td style="padding:8px 12px;border:1px solid #dee2e6">{company}</td><td style="padding:8px 12px;font-weight:600;width:25%;border:1px solid #dee2e6">사업자번호</td><td style="padding:8px 12px;border:1px solid #dee2e6">{req.get("biz_no","")}</td></tr>
  <tr><td style="padding:8px 12px;font-weight:600;border:1px solid #dee2e6">주소</td><td style="padding:8px 12px;border:1px solid #dee2e6" colspan="3">{req.get("address","")}{" " + req.get("address_detail","") if req.get("address_detail") else ""}</td></tr>
  <tr style="background:#f8f9fa"><td style="padding:8px 12px;font-weight:600;border:1px solid #dee2e6">담당자</td><td style="padding:8px 12px;border:1px solid #dee2e6">{req.get("contact_name","")}</td><td style="padding:8px 12px;font-weight:600;border:1px solid #dee2e6">연락처</td><td style="padding:8px 12px;border:1px solid #dee2e6">{req.get("contact_phone","")}</td></tr>
  <tr><td style="padding:8px 12px;font-weight:600;border:1px solid #dee2e6">섹터</td><td style="padding:8px 12px;border:1px solid #dee2e6">{sector}</td><td style="padding:8px 12px;font-weight:600;border:1px solid #dee2e6">진단 유형</td><td style="padding:8px 12px;border:1px solid #dee2e6">{{"v1":"법령진단","v2":"공정진단","v3":"설비진단"}.get(req.get("request_type","v1"),"")}</td></tr>
</table>

<div style="background:#e8f0fe;border-left:4px solid #0d6efd;padding:16px;margin-bottom:24px;border-radius:4px">
  <strong>진단 요약</strong><br>
  총 <strong>{summary.get("total",0)}건</strong>의 법령이 적용됩니다.
  선임 {summary.get("appointment",0)}건 · 점검 {summary.get("inspection",0)}건 · 조치 {summary.get("action",0)}건 · 신고 {summary.get("report",0)}건 · 보고 {summary.get("notify",0)}건
  {f'<br><br>⚠️ <strong>안전관리자 선임 의무: {"발생" if cs.get("safety_manager_required") else "해당없음"}</strong> ({cs.get("safety_manager_basis","")})' if cs else ""}
</div>

{rows_html(result.get("appointment_required",[]), "선임 의무")}
{rows_html(result.get("inspection_required",[]), "점검 의무")}
{rows_html(result.get("action_required",[]), "안전조치 의무")}
{rows_html(result.get("report_required",[]), "신고·보고 의무")}

<div style="margin-top:40px;padding-top:16px;border-top:1px solid #dee2e6;color:#6c757d;font-size:0.85rem;text-align:center">
  본 보고서는 TAI Engineering이 제공하는 AI 기반 법령진단 결과입니다.<br>
  실제 적용 여부는 현장 전문가의 최종 확인이 필요합니다.<br>
  문의: TAI Engineering | taieng.co.kr
</div>
</div>"""
    return html


# ──────────────────────────────────────────────────────────────
# PATCH /admin/public-diagnosis-requests/{id}/result-html
# 결과 HTML 직접 수정 저장
# ──────────────────────────────────────────────────────────────

class ResultHtmlBody(BaseModel):
    result_html: str


@router.patch("/{req_id}/result-html")
def update_result_html(req_id: str, body: ResultHtmlBody):
    supabase = get_supabase()
    res = supabase.table("public_diagnosis_requests").update({
        "result_html": body.result_html,
        "updated_at":  _now(),
    }).eq("id", req_id).execute()
    return {"status": "success", "data": res.data[0] if res.data else {}}


# ──────────────────────────────────────────────────────────────
# POST /admin/public-diagnosis-requests/{id}/mark-sent
# 결과 발송 완료 처리
# ──────────────────────────────────────────────────────────────

@router.post("/{req_id}/mark-sent")
def mark_sent(req_id: str):
    supabase = get_supabase()
    now = _now()
    res = supabase.table("public_diagnosis_requests").update({
        "status_code":    "DONE",
        "result_sent_at": now,
        "updated_at":     now,
    }).eq("id", req_id).execute()
    return {"status": "success", "message": "발송 완료 처리됐습니다.", "data": res.data[0] if res.data else {}}
