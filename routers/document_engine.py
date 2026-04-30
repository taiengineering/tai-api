"""Document Engine Router

문서 자동생성 엔진 API.
- /document-forms/{doc_id}/preview  — HTML 미리보기
- /document-forms/{doc_id}/generate — PDF 생성 + 티켓 차감
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from services.document_engine.fetchers.tbm_fetcher import TbmFetcher
from services.document_engine.renderer import (
    generate_document_pdf,
    render_document_html,
)

router = APIRouter(prefix="/document-forms", tags=["document-engine"])

# 패처 레지스트리 (doc_id → Fetcher)
_FETCHERS = {
    "DOC-OSH-056": TbmFetcher(),
    # TODO: 추가 패처 등록
}


class GenerateRequest(BaseModel):
    factory_id: str
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    meeting_id: Optional[str] = None
    additional_data: Optional[dict] = None


@router.get("/{doc_id}/preview", response_class=HTMLResponse)
async def preview_document(
    doc_id: str,
    factory_id: str = Query(...),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    meeting_id: Optional[str] = Query(None),
):
    """HTML 미리보기 — 데이터를 주입한 문서 HTML을 반환합니다."""
    fetcher = _FETCHERS.get(doc_id)
    if not fetcher:
        raise HTTPException(404, f"No fetcher registered for {doc_id}")

    try:
        data = await fetcher.fetch(
            factory_id=factory_id,
            date_from=date_from,
            date_to=date_to,
            meeting_id=meeting_id,
        )
        html = await render_document_html(doc_id, data)
        return HTMLResponse(content=html)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Preview failed: {e}")


@router.post("/{doc_id}/generate")
async def generate_document(doc_id: str, req: GenerateRequest):
    """PDF 생성 — 데이터 주입 → Gotenberg PDF 변환 → 바이트 반환."""
    fetcher = _FETCHERS.get(doc_id)
    if not fetcher:
        raise HTTPException(404, f"No fetcher registered for {doc_id}")

    # TODO: 티켓 잔여 확인 + 차감 (B~D등급)
    # from services.document_forms_service import get_document_form
    # form = get_document_form(doc_id)
    # if form['tai_grade'] != 'A':
    #     check_and_deduct_ticket(factory_id, form['ticket_cost'])

    try:
        data = await fetcher.fetch(
            factory_id=req.factory_id,
            date_from=req.date_from,
            date_to=req.date_to,
            meeting_id=req.meeting_id,
            additional_data=req.additional_data,
        )
        pdf_bytes = await generate_document_pdf(doc_id, data)

        filename = f"{doc_id}_{req.factory_id[:8]}_{data.get('work_date', 'doc')}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Generate failed: {e}")
