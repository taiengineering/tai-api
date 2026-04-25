"""TAI Safe 문서 관리 API v1.0.0"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from services import document_svc

router = APIRouter(prefix="/documents", tags=["Documents"])


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
):
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
):
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
):
    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    result = await document_svc.list_documents(
        company_id=company_id,
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
async def document_stats(company_id: str = Query(...)):
    data = await document_svc.get_stats(company_id)
    return {"status": "success", "data": data}


@router.get("/expiring")
async def expiring_documents(company_id: str = Query(...), days: int = Query(90)):
    data = await document_svc.get_expiring(company_id, days)
    return {"status": "success", "data": data}


@router.get("/by-entity/{table}/{record_id}")
async def by_entity(table: str, record_id: str):
    data = await document_svc.get_attachments(table, record_id)
    return {"status": "success", "data": data}


@router.get("/{doc_id}")
async def get_document(doc_id: str):
    doc = await document_svc.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"status": "success", "data": doc}


@router.get("/{doc_id}/download")
async def download_document(doc_id: str):
    url = await document_svc.get_signed_url(doc_id)
    if not url:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"status": "success", "url": url}


@router.patch("/{doc_id}")
async def update_document(doc_id: str, body: dict):
    updated = await document_svc.update_document(doc_id, body)
    if updated is None and not any(k in {"title", "description", "tags", "category"} for k in body.keys()):
        raise HTTPException(status_code=400, detail="No valid fields to update")
    if updated is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"status": "success", "data": updated}


@router.delete("/{doc_id}")
async def delete_document(doc_id: str):
    ok = await document_svc.soft_delete(doc_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"status": "success"}
