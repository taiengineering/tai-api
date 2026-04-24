"""
routers/uploads.py — v1.0.0
사진 업로드 엔드포인트

v1.0.0 (2026-04-24)
  POST /uploads/inspection-photo — 점검/신고/긴급 사진 업로드
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile

from routers.auth import get_current_user
from services.upload_service import upload_inspection_photo

router = APIRouter(prefix="/uploads", tags=["uploads"])

VALID_CONTEXTS = {"inspection", "report", "emergency", "tbm"}


@router.post("/inspection-photo")
async def post_inspection_photo(
    file: UploadFile = File(...),
    context: str = Form("inspection"),
    inspection_id: Optional[str] = Form(None),
    factory_id: Optional[str] = Form(None),
    site_id: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user),
):
    """
    점검/신고/긴급/TBM 사진 업로드.

    - Authorization: Bearer {access_token} 필수
    - multipart/form-data
    - 파일당 최대 5MB, image/jpeg|png|webp만 허용
    """
    if context not in VALID_CONTEXTS:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"context는 {VALID_CONTEXTS} 중 하나여야 합니다")

    contents = await file.read()

    result = upload_inspection_photo(
        file=file,
        contents=contents,
        context=context,
        user_id=current_user.get("id", ""),
        inspection_id=inspection_id,
        factory_id=factory_id,
        site_id=site_id,
    )
    return result
