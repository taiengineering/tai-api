# -*- coding: utf-8 -*-
"""safe 헬프센터 검색/조회 라우터. 설계 v3 §9·§10.

GET  /help/search      — kiwi 형태소 검색(type/page_slug/게이팅 필터). 공개.
GET  /help/doc/{slug}  — 문서 단건. 공개.
POST /help/content     — 콘텐츠 upsert + 색인. Bearer.
"""
from typing import Optional

from fastapi import APIRouter, Body, Header, HTTPException, Query

from services import safe_help_svc

router = APIRouter(prefix="/help", tags=["safe 헬프센터"])


def _csv(v: Optional[str]):
    if not v:
        return None
    out = [x.strip() for x in v.split(",") if x.strip()]
    return out or None


def _require_bearer(authorization: Optional[str]) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")


@router.get("/search")
def help_search(
    q: str = Query(..., min_length=1, description="검색어(한글 형태소)"),
    type: Optional[str] = Query(None, description="PAGE_GUIDE,TASK_GUIDE,FAQ (콤마 다중)"),
    page_slug: Optional[str] = Query(None, description="겹2 맥락 화면 slug"),
    sector: Optional[str] = Query(None, description="FACILITY/INDUSTRIAL/CONSTRUCTION"),
    level: Optional[int] = Query(None, description="사용자 계약 level"),
    addons: Optional[str] = Query(None, description="보유 addon (콤마 다중)"),
    role: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    offset = (page - 1) * size
    try:
        res = safe_help_svc.search(
            q=q, types=_csv(type), page_slug=page_slug, sector=sector,
            level=level, addons=_csv(addons), role=role, limit=size, offset=offset,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"검색 실패: {e!s}") from e
    total = res["total"]
    return {
        "status": "success",
        "data": {
            "items": res["items"],
            "total": total,
            "page": page,
            "size": size,
            "total_pages": (total + size - 1) // size if total else 0,
        },
    }


@router.get("/doc/{slug}")
def help_doc(slug: str):
    try:
        row = safe_help_svc.get_by_slug(slug.strip())
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"조회 실패: {e!s}") from e
    if not row:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
    return {"status": "success", "data": row}


@router.post("/content")
def help_upsert(
    authorization: Optional[str] = Header(None),
    doc: dict = Body(..., description="safe_help_content 행(doc_id/type/title/slug 필수)"),
):
    _require_bearer(authorization)
    try:
        saved = safe_help_svc.upsert_help(doc)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"저장 실패: {e!s}") from e
    return {"status": "success", "data": saved}
