"""routers/document_generate.py — 범용 문서 생성 (WO-3)

document_type_registry(2겹 매핑) 기반으로 유형별 문서를 HTML 미리보기/PDF 생성.
발행 코드: {TYPE}-{사업장}-{YYYYMMDD}[-{세부}] (DOCUMENT_CODE_CONVENTION_v1).

  POST /documents/{doc_type}/preview   → text/html
  POST /documents/{doc_type}/generate  → application/pdf
  GET  /documents/{doc_type}/registry  → 유형 등록 정보

doc_type 예: INSP, CHK, EQUIP, TBM, PPE. 단건형은 inspection_id/meeting_id 로 지정.
"""
from __future__ import annotations

import io
from datetime import date
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from services.document_engine.generator import render_html, render_pdf, get_registry

router = APIRouter(prefix="/documents", tags=["document-generate"])


class GenerateBody(BaseModel):
    factory_id: Optional[str] = None
    inspection_id: Optional[str] = None
    meeting_id: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    site_label: Optional[str] = None   # 발행 코드용 사업장 라벨
    detail: Optional[str] = None       # 발행 코드 세부(설비 대상 등)
    extra: Optional[Dict[str, Any]] = None


def _params(body: GenerateBody) -> Dict[str, Any]:
    p = body.model_dump(exclude_none=True)
    extra = p.pop("extra", None)
    if isinstance(extra, dict):
        p.update(extra)
    p.pop("site_label", None)
    return p


def _issue_code(doc_type: str, site_label: Optional[str], detail: Optional[str]) -> str:
    d = date.today().strftime("%Y%m%d")
    site = (site_label or "SITE").replace(" ", "")
    base = f"{doc_type}-{site}-{d}"
    return f"{base}-{detail}" if detail else base


@router.get("/{doc_type}/registry")
async def registry_info(doc_type: str):
    reg = await get_registry(doc_type.upper())
    if not reg:
        raise HTTPException(status_code=404, detail=f"미등록 서식 유형: {doc_type}")
    return reg


@router.post("/{doc_type}/preview", response_class=HTMLResponse)
async def preview(doc_type: str, body: GenerateBody):
    try:
        html = await render_html(doc_type.upper(), _params(body))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="템플릿이 아직 제작되지 않았습니다.")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"미리보기 실패: {e}")
    return HTMLResponse(content=html)


@router.post("/{doc_type}/generate")
async def generate(doc_type: str, body: GenerateBody):
    dt = doc_type.upper()
    try:
        pdf = await render_pdf(dt, _params(body))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="템플릿이 아직 제작되지 않았습니다.")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"PDF 생성 실패: {e}")

    code = _issue_code(dt, body.site_label, body.detail)
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{code}.pdf"'},
    )
