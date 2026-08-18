from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from services.document_forms_service import (
    get_document_form,
    get_document_forms_stats,
    list_document_forms,
)

router = APIRouter(prefix="/document-forms", tags=["document-forms"])


@router.get("")
def list_forms(
    sector: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    tai_grade: Optional[str] = Query(None),
    tab_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=200),
):
    # [17] 화면 unwrapFormList 는 {status, data:{items,...}} 봉투를 기대한다.
    #   다른 라우터(factories·org·tbm)와 달리 이 목록만 봉투 없이 반환해
    #   resp.data 가 undefined → 항상 빈 목록("등록된 서식이 없습니다")이었다.
    return {
        "status": "success",
        "data": list_document_forms(
            sector=sector,
            category=category,
            tai_grade=tai_grade,
            tab_type=tab_type,
            search=search,
            page=page,
            per_page=per_page,
        ),
    }


@router.get("/stats")
def forms_stats():
    return get_document_forms_stats()


@router.get("/{doc_id}")
def form_detail(doc_id: str):
    return get_document_form(doc_id)
