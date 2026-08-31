"""
엔진설정 > 문서 메뉴 라우터 — v1.1.0
=======================================
v1.1.0 (2026-08-18):
  - 서식 목록/상세 응답에 penalty 별칭 부여 (LEDGER §49 매핑분)
    화면(engine-document)은 item.penalty 를 읽으나 두 원본 테이블은 penalty_summary 만 보유.
    서빙 계층에서 penalty = penalty_summary 를 채워 넣는다(원본 penalty_summary 는 그대로 유지).
    ※ 데이터 자체가 비어있는 경우(form_templates.penalty_summary 등)는 여기서 채울 수 없음 — 데이터/엔진 영역.
v1.0.0 (2026-04-02):
  - GET  /engine/forms          서식 목록 조회 (form_type 파라미터로 테이블 분기)
  - GET  /engine/forms/summary  보관현황 요약 카드
  - GET  /engine/forms/{code}   서식 상세 조회
  - PATCH /engine/forms/{code}  서식 수정 (관리자)

대상 테이블:
  - form_templates        법정서식 (LEGAL)
  - document_form_master  TAI표준서식(STANDARD) / 자유서식가이드(FREE)
"""
from fastapi import APIRouter, Query, HTTPException
from typing import Optional
from datetime import datetime, timezone

from db.supabase_client import get_supabase
from services.time import now_kst, serialize_external_utc

router = APIRouter(prefix="/engine", tags=["engine-document"])


def _alias_penalty(row: dict) -> dict:
    """화면 계약(item.penalty) 호환: penalty 가 없고 penalty_summary 가 있으면 채운다.
    원본 penalty_summary 는 제거하지 않는다(다른 소비자 호환)."""
    if not isinstance(row, dict):
        return row
    if row.get("penalty") in (None, "") and row.get("penalty_summary") not in (None, ""):
        row["penalty"] = row.get("penalty_summary")
    return row


@router.get("/forms")
async def get_forms(
    form_type: Optional[str] = Query(None, description="LEGAL | STANDARD | FREE"),
    form_category: Optional[str] = Query(None, description="REPORT | DOCUMENT | NOTIFY | APPOINT | INSPECT"),
    obligation_type: Optional[str] = Query(None),
    sector: str = Query("BUILDING"),
    is_active: bool = Query(True),
):
    """
    서식 목록 조회
    - form_type=LEGAL    → form_templates 테이블
    - form_type=STANDARD / FREE / None → document_form_master 테이블
    """
    supabase = get_supabase()

    if form_type == "LEGAL":
        # 법정서식: form_templates 조회
        query = (
            supabase.table("form_templates")
            .select("*")
            .eq("is_active", is_active)
        )
        if sector:
            query = query.eq("sector", sector)
        result = query.order("sort_order").execute()
    else:
        # TAI표준서식 / 자유서식가이드: document_form_master 조회
        query = (
            supabase.table("document_form_master")
            .select("*")
            .eq("is_active", is_active)
        )
        if form_type:
            query = query.eq("form_type", form_type)
        if form_category:
            query = query.eq("form_category", form_category)
        if obligation_type:
            query = query.eq("obligation_type", obligation_type)
        if sector:
            query = query.eq("sector", sector)
        result = query.order("sort_order").execute()

    rows = [_alias_penalty(r) for r in (result.data or [])]

    return {
        "success": True,
        "data": rows,
        "total": len(rows),
    }


@router.get("/forms/summary")
async def get_forms_summary(sector: str = Query("BUILDING")):
    """
    보관현황 요약 카드
    - 법정서식 수 (form_templates)
    - TAI표준서식 수 (document_form_master, form_type=STANDARD)
    - 자유서식가이드 수 (document_form_master, form_type=FREE)
    """
    supabase = get_supabase()

    # document_form_master 전체 (sector 필터)
    std_res = (
        supabase.table("document_form_master")
        .select("id, form_type")
        .eq("is_active", True)
        .eq("sector", sector)
        .execute()
    )

    # form_templates 전체 (sector 필터)
    legal_res = (
        supabase.table("form_templates")
        .select("id, form_type")
        .eq("is_active", True)
        .execute()
    )

    std_data = std_res.data or []
    legal_data = legal_res.data or []

    total_legal    = len(legal_data)
    total_standard = len([x for x in std_data if x.get("form_type") == "STANDARD"])
    total_free     = len([x for x in std_data if x.get("form_type") == "FREE"])

    return {
        "success": True,
        "data": {
            "total_legal":               total_legal,
            "total_standard":            total_standard,
            "total_free":                total_free,
            "total_document_obligations": 52,   # Phase 3: 보관의무 건수
            "forms_stored":              0,      # Phase 3: document_storage 연동
            "expiring_soon":             0,      # Phase 3
            "expired":                   0,      # Phase 3
        },
    }


@router.get("/forms/{form_code}")
async def get_form_detail(form_code: str):
    """
    서식 상세 조회
    - form_templates 우선 조회 → 없으면 document_form_master 조회
    """
    supabase = get_supabase()

    # form_templates 우선
    res = (
        supabase.table("form_templates")
        .select("*")
        .eq("form_code", form_code)
        .limit(1)
        .execute()
    )
    if res.data:
        return {"success": True, "data": _alias_penalty(res.data[0]), "source": "form_templates"}

    # document_form_master
    res = (
        supabase.table("document_form_master")
        .select("*")
        .eq("form_code", form_code)
        .limit(1)
        .execute()
    )
    if res.data:
        return {"success": True, "data": _alias_penalty(res.data[0]), "source": "document_form_master"}

    raise HTTPException(status_code=404, detail=f"Form not found: {form_code}")


@router.patch("/forms/{form_code}")
async def update_form(form_code: str, body: dict):
    """
    서식 수정 (관리자용)
    - form_templates / document_form_master 자동 분기
    """
    supabase = get_supabase()

    # 수정 불가 필드 제거
    for key in ("id", "form_code", "created_at"):
        body.pop(key, None)

    body["updated_at"] = serialize_external_utc(now_kst())

    # form_templates 존재 여부 확인
    check = (
        supabase.table("form_templates")
        .select("id")
        .eq("form_code", form_code)
        .limit(1)
        .execute()
    )

    if check.data:
        result = (
            supabase.table("form_templates")
            .update(body)
            .eq("form_code", form_code)
            .execute()
        )
    else:
        result = (
            supabase.table("document_form_master")
            .update(body)
            .eq("form_code", form_code)
            .execute()
        )

    if not result.data:
        raise HTTPException(status_code=404, detail=f"Form not found: {form_code}")

    return {"success": True, "data": result.data[0]}
