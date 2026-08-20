"""TAI Safe 문서 관리 API v1.1.0

v1.1.0: 인증·회사 스코프 (P13).
  업로드는 토큰 회사 강제, 목록·통계·만료는 무회사 빈 결과,
  단건은 소유 확인, by-entity 는 자사 후필터.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services import document_svc
from services.company_scope import _ensure_own_company, require_company_id, scoped_list_company

router = APIRouter(prefix="/documents", tags=["Documents"])

_NOT_FOUND = "Document not found"


def _owned_company_id(current: dict, form_or_query_company_id: Optional[str]):
    """업로드용: 비-ALL 은 토큰 회사 강제(Form/Query 무시). ALL 은 토큰이 없으면 클라 값 유지."""
    supabase = get_supabase()
    forced = require_company_id(current, supabase)
    company_id = forced or form_or_query_company_id
    if not company_id:
        raise HTTPException(status_code=403, detail="회사 등록이 필요합니다.")
    return company_id


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    company_id: str = Form(...),
    category: str = Form("general"),
    factory_id: Optional[str] = Form(None),
    linked_table: Optional[str] = Form(None),
    linked_id: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    uploaded_by: Optional[str] = Form(None),
    current: dict = Depends(get_current_user),
):
    company_id = _owned_company_id(current, company_id)
    file_bytes = await file.read()
    tag_list = [t.strip() for t in tags.split(",")] if tags else []
    result = await document_svc.upload_document(
        file_bytes=file_bytes,
        file_name=file.filename,
        mime_type=file.content_type or "application/octet-stream",
        company_id=company_id,
        category=category,
        factory_id=factory_id,
        linked_table=linked_table,
        linked_id=linked_id,
        title=title,
        description=description,
        tags=tag_list,
        uploaded_by=uploaded_by,
    )
    return {"status": "success", "data": result}


@router.post("/upload-multiple")
async def upload_multiple(
    files: List[UploadFile] = File(...),
    company_id: str = Form(...),
    category: str = Form("general"),
    factory_id: Optional[str] = Form(None),
    linked_table: Optional[str] = Form(None),
    linked_id: Optional[str] = Form(None),
    uploaded_by: Optional[str] = Form(None),
    current: dict = Depends(get_current_user),
):
    company_id = _owned_company_id(current, company_id)
    results = []
    for f in files:
        fb = await f.read()
        r = await document_svc.upload_document(
            file_bytes=fb,
            file_name=f.filename,
            mime_type=f.content_type or "application/octet-stream",
            company_id=company_id,
            category=category,
            factory_id=factory_id,
            linked_table=linked_table,
            linked_id=linked_id,
            uploaded_by=uploaded_by,
        )
        results.append(r)
    return {"status": "success", "data": results, "count": len(results)}


@router.get("")
async def list_documents(
    company_id: str = Query(...),
    category: Optional[str] = Query(None),
    factory_id: Optional[str] = Query(None),
    linked_table: Optional[str] = Query(None),
    linked_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    tags: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    scoped_cid, deny_all = scoped_list_company(current, supabase, company_id)
    if deny_all or not scoped_cid:
        return {
            "status": "success",
            "items": [],
            "total": 0,
            "page": page,
            "per_page": per_page,
            "total_pages": 0,
        }
    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    result = await document_svc.list_documents(
        company_id=scoped_cid,
        category=category,
        factory_id=factory_id,
        linked_table=linked_table,
        linked_id=linked_id,
        search=search,
        tags=tag_list,
        page=page,
        per_page=per_page,
    )
    return {"status": "success", **result}


@router.get("/stats")
async def document_stats(
    company_id: str = Query(...),
    current: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    scoped_cid, deny_all = scoped_list_company(current, supabase, company_id)
    if deny_all or not scoped_cid:
        return {"status": "success", "data": []}
    data = await document_svc.get_stats(scoped_cid)
    return {"status": "success", "data": data}


@router.get("/expiring")
async def expiring_documents(
    company_id: str = Query(...),
    days: int = Query(90),
    current: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    scoped_cid, deny_all = scoped_list_company(current, supabase, company_id)
    if deny_all or not scoped_cid:
        return {"status": "success", "data": []}
    data = await document_svc.get_expiring(scoped_cid, days)
    return {"status": "success", "data": data}


@router.get("/by-entity/{table}/{record_id}")
async def by_entity(table: str, record_id: str, current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    data = await document_svc.get_attachments(table, record_id)
    scoped_cid, deny_all = scoped_list_company(current, supabase, None)
    if deny_all:
        data = []
    elif scoped_cid:
        data = [d for d in data if str(d.get("company_id") or "") == str(scoped_cid)]
    return {"status": "success", "data": data}


@router.get("/{doc_id}")
async def get_document(doc_id: str, current: dict = Depends(get_current_user)):
    doc = await document_svc.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    _ensure_own_company(doc.get("company_id"), current, get_supabase(), _NOT_FOUND)
    return {"status": "success", "data": doc}


@router.get("/{doc_id}/download")
async def download_document(doc_id: str, current: dict = Depends(get_current_user)):
    doc = await document_svc.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    _ensure_own_company(doc.get("company_id"), current, get_supabase(), _NOT_FOUND)
    url = await document_svc.get_signed_url(doc_id)
    if not url:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return {"status": "success", "url": url}


@router.patch("/{doc_id}")
async def update_document(doc_id: str, body: dict, current: dict = Depends(get_current_user)):
    doc = await document_svc.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    _ensure_own_company(doc.get("company_id"), current, get_supabase(), _NOT_FOUND)
    updated = await document_svc.update_document(doc_id, body)
    if updated is None and not any(k in {"title", "description", "tags", "category"} for k in body.keys()):
        raise HTTPException(status_code=400, detail="No valid fields to update")
    if updated is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return {"status": "success", "data": updated}


@router.delete("/{doc_id}")
async def delete_document(doc_id: str, current: dict = Depends(get_current_user)):
    doc = await document_svc.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    _ensure_own_company(doc.get("company_id"), current, get_supabase(), _NOT_FOUND)
    ok = await document_svc.soft_delete(doc_id)
    if not ok:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return {"status": "success"}
