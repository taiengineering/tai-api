"""routers/document_digitize.py — 명시적 문서 디지털화 API.

POST /digitize — TAI 관리자가 파일을 DOC에 보내 변환 결과 ID를 받는 단방향 진입점.

권한 계약 (초기 제한, G6-I2 TAI Consumer Connection):
  - role_code == "001" 전용 (일반 직원 개방 시 별도 Owner 승인 필요)
  - 서버에서 확인한 company_id만 사용 (클라이언트 제공 금지)
  - companies 테이블 실존 확인 필수
  - factory_id 제공 시 resolve_document_site_context()로 사업장 소속·권한 검증 (Gate C)

기존 upload_file_field() 미변경 — 파일 첨부와 문서 디지털화는 별개 기능.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services.doc_digitize_client import (
    DocConfigError,
    DocConnectionError,
    DocDigitizeError,
    digitize,
)
from services.doc_lookup_client import DocLookupError, lookup_extraction_content
from services.doc_site_context import resolve_document_site_context

log = logging.getLogger(__name__)
router = APIRouter(prefix="/digitize", tags=["문서 디지털화"])

_MAX_BYTES = 50 * 1024 * 1024  # 50 MiB (DOC 현재 기본 제한)
_ALLOWED_MODES: frozenset[str] = frozenset({"digital", "scan", "unsure"})


def _require_admin(current_user: dict) -> None:
    if current_user.get("role_code") != "001":
        raise HTTPException(403, "문서 디지털화는 관리자(role_code=001) 전용입니다")


def _resolve_company_id(current_user: dict, form_company_id: Optional[str]) -> str:
    """company_id 결정: role_code=001이면 form 값 허용, 그 외 토큰 값만 사용."""
    if form_company_id and form_company_id.strip():
        return form_company_id.strip()
    cid = (current_user.get("company_id") or "").strip()
    if not cid:
        raise HTTPException(403, "대상 회사를 선택해 주세요")
    return cid


def _verify_company_exists(company_id: str) -> None:
    try:
        sb = get_supabase()
        res = sb.table("companies").select("id").eq("id", company_id).limit(1).execute()
    except Exception as exc:
        log.error("[digitize] company 조회 오류: %s", exc)
        raise HTTPException(503, "회사 확인 중 오류가 발생했습니다") from exc
    if not res.data:
        raise HTTPException(403, "유효하지 않은 company_id입니다")


@router.post("")
async def digitize_document(
    file: UploadFile = File(...),
    document_input_mode: Optional[str] = Form(None),
    company_id: Optional[str] = Form(None),
    factory_id: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user),
):
    """파일을 DOC에 전송해 디지털화 처리 결과 ID를 반환합니다.

    - 중복 파일: duplicate=true, doc_log_id만 반환
    - 신규 파일: primitive_id·v2_status 등 포함
    - DOC 오류 메시지는 TAI 로그에만 기록 (사용자 미노출)
    - document_input_mode: 파일 입력 방식 힌트 (digital|scan|unsure, 선택)
    - company_id: role_code=001 전용 — 대상 회사 지정 (미입력 시 토큰 company_id 사용)
    - factory_id: 대상 사업장 ID — 제공 시 사업장 소속·권한 검증 후 DOC에 전달 (Gate C)
    """
    _require_admin(current_user)
    company_id = _resolve_company_id(current_user, company_id)
    _verify_company_exists(company_id)

    if document_input_mode is not None and document_input_mode not in _ALLOWED_MODES:
        raise HTTPException(422, "document_input_mode 허용 값: digital, scan, unsure")

    # Gate C: factory_id 제공 시 사업장 소속·권한 검증
    verified_factory_id: Optional[str] = None
    if factory_id and factory_id.strip():
        sb = get_supabase()
        ctx = resolve_document_site_context(
            current_user=current_user,
            company_id=company_id,
            factory_id=factory_id.strip(),
            supabase=sb,
        )
        verified_factory_id = ctx.factory_id

    # 50 MiB + 1 센티넬로 초과 감지
    file_bytes = await file.read(_MAX_BYTES + 1)
    if len(file_bytes) > _MAX_BYTES:
        raise HTTPException(413, "파일 크기가 50 MiB를 초과합니다")

    original_filename = file.filename or "upload"

    try:
        result = await digitize(
            file_bytes=file_bytes,
            original_filename=original_filename,
            company_id=company_id,
            document_input_mode=document_input_mode,
            factory_id=verified_factory_id,
        )
    except DocConfigError as exc:
        log.error("[digitize] 설정 오류: %s", exc.reason)
        raise HTTPException(503, "문서 디지털화 서비스가 준비되지 않았습니다") from exc
    except DocConnectionError as exc:
        log.error("[digitize] 연결 오류: %s", exc.reason)
        raise HTTPException(502, "문서 디지털화 서비스에 연결할 수 없습니다") from exc
    except DocDigitizeError as exc:
        log.error("[digitize] DOC 처리 실패 stage=%s http=%s", exc.stage, exc.http_status)
        if exc.http_status == 422:
            raise HTTPException(422, f"문서 검증 실패 (stage: {exc.stage})")
        if exc.http_status == 503:
            raise HTTPException(503, "문서 디지털화 서비스를 사용할 수 없습니다") from exc
        raise HTTPException(502, "문서 디지털화 처리 중 오류가 발생했습니다") from exc

    response: dict = {
        "ok": True,
        "doc_log_id": result.doc_log_id,
        "duplicate": result.duplicate,
        "primitive_id": result.primitive_id,
        "v1_status": result.v1_status,
        "v2_status": result.v2_status,
        "file_hash": result.file_hash,
        "file_size_bytes": result.file_size_bytes,
        "storage_ref": result.storage_ref,
    }
    if result.storage_warning:
        # DOC 내부 저장 오류 원문 미노출 — 일반 안내로 치환
        response["storage_warning"] = "원본 파일 저장이 완료되지 않았습니다. 관리자 확인이 필요합니다."
    return response


@router.get("/{doc_log_id}/result")
async def get_digitize_result(
    doc_log_id: str,
    company_id: Optional[str] = Query(None),
    factory_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """디지털화된 문서의 추출 결과(Markdown)를 반환합니다.

    - role_code=001 전용
    - company_id: 조회 대상 회사 (미전달 시 로그인 계정 company_id 사용)
      * 업로드 시 선택한 회사와 동일한 company_id를 전달해야 조회 가능
    - factory_id: 업로드 시 지정한 사업장 ID — 제공 시 사업장 귀속 검증 후 DOC에 전달 (Gate C)
    - extraction_format=md 인 경우에만 콘텐츠 반환
    """
    _require_admin(current_user)
    company_id = _resolve_company_id(current_user, company_id)
    _verify_company_exists(company_id)

    # Gate C: factory_id 제공 시 사업장 소속·권한 검증
    verified_factory_id: Optional[str] = None
    if factory_id and factory_id.strip():
        sb = get_supabase()
        ctx = resolve_document_site_context(
            current_user=current_user,
            company_id=company_id,
            factory_id=factory_id.strip(),
            supabase=sb,
        )
        verified_factory_id = ctx.factory_id

    try:
        result = await lookup_extraction_content(
            doc_log_id=doc_log_id,
            company_id=company_id,
            factory_id=verified_factory_id,
        )
    except DocLookupError as exc:
        log.error("[digitize/result] DOC 조회 오류 code=%s", exc.code)
        if exc.code == "endpoint_not_active":
            raise HTTPException(503, "결과 조회 서비스가 아직 준비되지 않았습니다") from exc
        if exc.code in ("auth_failed", "config_missing"):
            raise HTTPException(503, "결과 조회 서비스 설정 오류입니다") from exc
        if exc.code in ("connection_timeout", "connection_error"):
            raise HTTPException(502, "결과 조회 서비스에 연결할 수 없습니다") from exc
        raise HTTPException(502, "결과 조회 중 오류가 발생했습니다") from exc

    if result.status == "NOT_FOUND":
        raise HTTPException(404, "문서를 찾을 수 없습니다")
    if result.status in ("EXTRACTION_REF_MISSING", "EXTRACTION_NOT_AVAILABLE"):
        raise HTTPException(404, "추출 결과가 아직 준비되지 않았습니다")
    if result.status == "LOOKUP_BACKEND_UNAVAILABLE":
        raise HTTPException(503, "결과 조회 서비스를 사용할 수 없습니다")
    if result.status != "FOUND" or result.content is None:
        raise HTTPException(404, "추출 결과를 찾을 수 없습니다")

    return {
        "ok": True,
        "doc_log_id": doc_log_id,
        "content": result.content,
        "extraction_format": "md",
    }
