"""Document Generator — 범용 생성 디스패처 (WO-3)

document_type_registry(2겹 매핑)로 doc_type → template·fetcher 를 조회하고,
fetcher 로 데이터를 조립해 renderer 로 HTML/PDF 를 생성한다.
compliance_report 패턴의 일반화. 신규 엔진 없음.

흐름: doc_type → registry 조회 → fetcher.fetch(params) → render(template, data)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Tuple

from db.supabase_client import get_supabase
from services.document_engine.renderer import render_document_html, generate_document_pdf
from services.document_engine.fetchers.inspection_fetcher import InspectionFetcher
from services.document_engine.fetchers.tbm_fetcher import TbmFetcher

log = logging.getLogger(__name__)

# fetcher_key → fetcher 클래스
FETCHER_MAP = {
    "inspection": InspectionFetcher,
    "tbm": TbmFetcher,
}


async def get_registry(doc_type: str) -> Dict[str, Any] | None:
    """document_type_registry 에서 유형 1건 조회."""
    sb = get_supabase()
    try:
        r = (
            sb.table("document_type_registry").select("*")
            .eq("doc_type", doc_type).limit(1).execute()
        )
        return r.data[0] if r.data else None
    except Exception as e:
        log.warning("registry 조회 실패: %s", e)
        return None


async def _build(doc_type: str, params: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    reg = await get_registry(doc_type)
    if not reg:
        raise ValueError(f"미등록 서식 유형: {doc_type}")
    fkey = reg.get("fetcher_key")
    status = reg.get("fetcher_status")
    if not fkey or fkey not in FETCHER_MAP:
        raise ValueError(
            f"'{doc_type}' 는 현재 자동 생성 대상이 아닙니다 (fetcher_status={status})."
        )
    fetcher = FETCHER_MAP[fkey]()
    data = await fetcher.fetch(params)
    template_id = (reg.get("template_file") or "").replace(".html", "")
    if not template_id:
        raise ValueError(f"'{doc_type}' 템플릿이 등록되지 않았습니다.")
    return template_id, data


async def render_html(doc_type: str, params: Dict[str, Any]) -> str:
    template_id, data = await _build(doc_type, params)
    return await render_document_html(template_id, data)


async def render_pdf(doc_type: str, params: Dict[str, Any]) -> bytes:
    template_id, data = await _build(doc_type, params)
    return await generate_document_pdf(template_id, data)
