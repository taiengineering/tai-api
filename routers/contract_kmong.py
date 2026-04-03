"""
크몽 법령진단 라우터 — v1.0.0
============================
대상 테이블: public_diagnosis_requests

v1.0.0 (2026-04-03):
  POST /contract/kmong/{id}/engine  법령엔진 구동 → diagnosis_result 저장
  PATCH /contract/kmong/{id}        status_code / result_html / admin_memo 수정
  POST /contract/kmong/{id}/pdf     result_html → PDF → Supabase Storage → result_pdf_url 저장
  GET  /contract/kmong              목록 조회 (page/size/search/status/source)
  GET  /contract/kmong/{id}         단건 조회
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import io
import os

from db.supabase_client import get_supabase

# legal_engine 내부 함수 임포트
from routers.legal_engine import (
    _input_to_facility_context,
    _evaluate_facility_conditions_db,
    _classify_rules_db,
    format_rule_result_db,
    _risk_level,
    ENGINE_VERSION,
)

router = APIRouter(prefix="/contract/kmong", tags=["contract-kmong"])


# ──────────────────────────────────────────────
# 스키마
# ──────────────────────────────────────────────

class KmongPatchBody(BaseModel):
    status_code: Optional[str] = None
    result_html: Optional[str] = None
    admin_memo:  Optional[str] = None


# ──────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_request_or_404(supabase, request_id: str) -> dict:
    res = (
        supabase.table("public_diagnosis_requests")
        .select("*")
        .eq("id", request_id)
        .single()
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="진단 요청을 찾을 수 없습니다.")
    return res.data


def _run_engine(row: dict) -> dict:
    """
    public_diagnosis_requests 행에서 입력값을 추출하여 법령엔진 판정 실행.
    facility_data JSON 안의 값을 flat input으로 변환.
    """
    supabase = get_supabase()

    sector = (row.get("sector") or "BUILDING").upper()
    facility_data = row.get("facility_data") or {}

    # facility_data 내 키를 flat input으로 사용
    inp = dict(facility_data)
    # 기본값 보완
    if "sector" not in inp:
        inp["sector"] = sector

    # facility context 생성
    facility_ctx = _input_to_facility_context(sector, inp)

    # 해당 섹터 + stage=1 룰 조회
    rules_res = (
        supabase.table("master_building_legal_rules")
        .select("*")
        .eq("is_active", True)
        .eq("sector", sector)
        .eq("diagnosis_stage", 1)
        .execute()
    )
    all_rules = rules_res.data or []

    applicable, not_applicable = _evaluate_facility_conditions_db(
        facility_ctx, all_rules, sector
    )

    triggered = {
        "appointment": [],
        "inspection": [],
        "notify": [],
        "report": [],
        "action": [],
    }
    _classify_rules_db(applicable, triggered)

    total = sum(len(v) for v in triggered.values())
    appointment_n = len(triggered["appointment"])
    risk = _risk_level(total, appointment_n)

    law_names = sorted({r.get("law_name") for r in applicable if r.get("law_name")})

    return {
        "engine_version":    ENGINE_VERSION,
        "sector":            sector,
        "evaluated_at":      _now(),
        "facility_context":  facility_ctx,
        "risk_level":        risk,
        "applicable_count":  total,
        "law_badges":        law_names,
        "summary": {
            "total":       total,
            "appointment": appointment_n,
            "inspection":  len(triggered["inspection"]),
            "action":      len(triggered["action"]),
            "report":      len(triggered["report"]),
            "notify":      len(triggered["notify"]),
        },
        "appointment_required": triggered["appointment"],
        "inspection_required":  triggered["inspection"],
        "action_required":      triggered["action"],
        "report_required":      triggered["report"] + triggered["notify"],
        "total_rules_checked":  len(all_rules),
        "not_applicable_count": len(not_applicable),
    }


# ──────────────────────────────────────────────
# API
# ──────────────────────────────────────────────

@router.post("/{request_id}/engine")
def run_engine(request_id: str):
    """
    법령엔진 구동 → diagnosis_result 저장
    status_code: PENDING → IN_REVIEW
    """
    supabase = get_supabase()
    row = _get_request_or_404(supabase, request_id)

    result = _run_engine(row)

    supabase.table("public_diagnosis_requests").update({
        "diagnosis_result": result,
        "status_code":      "IN_REVIEW",
        "updated_at":       _now(),
    }).eq("id", request_id).execute()

    return {
        "status":  "success",
        "message": "법령엔진 판정 완료. 상태: IN_REVIEW",
        "data":    result,
    }


@router.patch("/{request_id}")
def patch_request(request_id: str, body: KmongPatchBody):
    """
    status_code / result_html / admin_memo 수정
    """
    supabase = get_supabase()
    _get_request_or_404(supabase, request_id)

    update: dict = {"updated_at": _now()}
    if body.status_code is not None:
        update["status_code"] = body.status_code
    if body.result_html is not None:
        update["result_html"] = body.result_html
    if body.admin_memo is not None:
        update["admin_memo"] = body.admin_memo

    if len(update) == 1:
        raise HTTPException(status_code=400, detail="변경할 필드가 없습니다.")

    res = (
        supabase.table("public_diagnosis_requests")
        .update(update)
        .eq("id", request_id)
        .execute()
    )
    return {"status": "success", "data": res.data[0] if res.data else {}}


@router.post("/{request_id}/pdf")
def generate_pdf(request_id: str):
    """
    result_html → xhtml2pdf → PDF bytes → Supabase Storage 업로드 → result_pdf_url 저장
    Storage 버킷: diagnosis-pdfs (public)
    """
    supabase = get_supabase()
    row = _get_request_or_404(supabase, request_id)

    html_content = row.get("result_html") or ""
    if not html_content:
        raise HTTPException(status_code=400, detail="result_html이 없습니다. 먼저 PATCH로 result_html을 저장하세요.")

    # ── PDF 생성 (xhtml2pdf) ──
    try:
        from xhtml2pdf import pisa
    except ImportError:
        raise HTTPException(status_code=500, detail="xhtml2pdf 라이브러리가 설치되어 있지 않습니다.")

    pdf_buffer = io.BytesIO()
    result = pisa.pisaDocument(
        io.BytesIO(html_content.encode("utf-8")),
        pdf_buffer,
        encoding="utf-8",
    )
    if result.err:
        raise HTTPException(status_code=500, detail=f"PDF 생성 실패: {result.err}")

    pdf_bytes = pdf_buffer.getvalue()

    # ── Supabase Storage 업로드 ──
    file_name   = f"kmong/{request_id}.pdf"
    bucket_name = "diagnosis-pdfs"

    try:
        supabase.storage.from_(bucket_name).upload(
            path=file_name,
            file=pdf_bytes,
            file_options={"content-type": "application/pdf", "upsert": "true"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Storage 업로드 실패: {e}")

    # ── Public URL 획득 ──
    try:
        url_res = supabase.storage.from_(bucket_name).get_public_url(file_name)
        pdf_url = url_res if isinstance(url_res, str) else url_res.get("publicUrl", "")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"URL 획득 실패: {e}")

    # ── DB 저장 ──
    supabase.table("public_diagnosis_requests").update({
        "result_pdf_url": pdf_url,
        "status_code":    "DONE",
        "updated_at":     _now(),
    }).eq("id", request_id).execute()

    return {
        "status":      "success",
        "message":     "PDF 생성 완료. 상태: DONE",
        "pdf_url":     pdf_url,
        "size_bytes":  len(pdf_bytes),
    }


@router.get("")
def list_requests(
    page:    int           = Query(1, ge=1),
    size:    int           = Query(20, ge=1, le=100),
    search:  Optional[str] = Query(None, description="회사명·담당자명·요청번호 검색"),
    status:  Optional[str] = Query(None, description="status_code 필터"),
    source:  Optional[str] = Query(None, description="source 필터 (KMONG 등)"),
):
    """
    public_diagnosis_requests 목록 (page / size / search / status / source)
    """
    supabase = get_supabase()
    query = (
        supabase.table("public_diagnosis_requests")
        .select(
            "id, request_no, company_name, contact_name, contact_phone, contact_email, "
            "sector, source, status_code, admin_memo, result_pdf_url, created_at, updated_at",
            count="exact",
        )
    )

    if status:
        query = query.eq("status_code", status)
    if source:
        query = query.eq("source", source)
    if search:
        pat = f"%{search}%"
        query = query.or_(
            f"company_name.ilike.{pat},contact_name.ilike.{pat},request_no.ilike.{pat}"
        )

    offset = (page - 1) * size
    res = (
        query
        .order("created_at", desc=True)
        .range(offset, offset + size - 1)
        .execute()
    )

    total = res.count or 0
    return {
        "status": "success",
        "data": {
            "items":       res.data or [],
            "total":       total,
            "page":        page,
            "size":        size,
            "total_pages": -(-total // size) if total else 0,
        },
    }


@router.get("/{request_id}")
def get_request(request_id: str):
    """단건 조회"""
    supabase = get_supabase()
    row = _get_request_or_404(supabase, request_id)
    return {"status": "success", "data": row}
