# -*- coding: utf-8 -*-
"""safe 헬프센터 검색/조회 + 관리(admin) 라우터. 설계 v3 §9·§10.

공개:
  GET  /help/search      — kiwi 형태소 검색(type/page_slug/게이팅 필터).
  GET  /help/doc/{slug}  — 문서 단건.
등록·수정(Bearer):
  POST /help/content     — 콘텐츠 upsert + kiwi 색인.
관리(Bearer) — admin-vue3 '서비스 운영 > 매뉴얼':
  GET    /help/admin/list            — 전체 목록(q/type/menu_group/status 필터·페이징).
  GET    /help/admin/menu-groups     — menu_group 목록(셀렉트용).
  GET    /help/admin/doc/{doc_id}    — 단건(전체 필드).
  PATCH  /help/admin/{doc_id}/status — 상태 온오프.
  DELETE /help/admin/{doc_id}        — 삭제.
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


# ─────────────────────────────────────────────────────────────────────────
# 관리(admin) — admin-vue3 '서비스 운영 > 매뉴얼' 관리 화면. 전부 Bearer.
# ─────────────────────────────────────────────────────────────────────────

@router.get("/admin/list")
def help_admin_list(
    authorization: Optional[str] = Header(None),
    q: Optional[str] = Query(None, description="제목/doc_id/질문 부분일치"),
    type: Optional[str] = Query(None, description="PAGE_GUIDE/FAQ 등 단일"),
    menu_group: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="PUBLISHED/DRAFT 등"),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
):
    _require_bearer(authorization)
    offset = (page - 1) * size
    try:
        res = safe_help_svc.list_admin(
            q=q, type=type, menu_group=menu_group, status=status, limit=size, offset=offset,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"목록 조회 실패: {e!s}") from e
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


@router.get("/admin/menu-groups")
def help_admin_menu_groups(authorization: Optional[str] = Header(None)):
    _require_bearer(authorization)
    try:
        groups = safe_help_svc.list_menu_groups()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"그룹 조회 실패: {e!s}") from e
    return {"status": "success", "data": {"items": groups, "total": len(groups)}}


@router.get("/admin/doc/{doc_id}")
def help_admin_doc(doc_id: str, authorization: Optional[str] = Header(None)):
    _require_bearer(authorization)
    try:
        row = safe_help_svc.get_admin(doc_id.strip())
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"조회 실패: {e!s}") from e
    if not row:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
    return {"status": "success", "data": row}


@router.patch("/admin/{doc_id}/status")
def help_admin_set_status(
    doc_id: str,
    authorization: Optional[str] = Header(None),
    body: dict = Body(..., description='{"status": "PUBLISHED" | "DRAFT"}'),
):
    _require_bearer(authorization)
    status = (body or {}).get("status")
    if not status:
        raise HTTPException(status_code=400, detail="status 는 필수입니다.")
    try:
        saved = safe_help_svc.set_status(doc_id.strip(), status)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"상태 변경 실패: {e!s}") from e
    if not saved:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
    return {"status": "success", "data": saved}


@router.delete("/admin/{doc_id}")
def help_admin_delete(doc_id: str, authorization: Optional[str] = Header(None)):
    _require_bearer(authorization)
    try:
        ok = safe_help_svc.delete_help(doc_id.strip())
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"삭제 실패: {e!s}") from e
    if not ok:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
    return {"status": "success", "data": {"doc_id": doc_id, "deleted": True}}
