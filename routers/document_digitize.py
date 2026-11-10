"""routers/document_digitize.py — 명시적 문서 디지털화 API.

POST /digitize — TAI 관리자가 파일을 DOC에 보내 변환 결과 ID를 받는 단방향 진입점.

권한 계약 (초기 제한, G6-I2 TAI Consumer Connection):
  - role_code == "001" 전용 (일반 직원 개방 시 별도 Owner 승인 필요)
  - 서버에서 확인한 company_id만 사용 (클라이언트 제공 금지)
  - companies 테이블 실존 확인 필수

기존 upload_file_field() 미변경 — 파일 첨부와 문서 디지털화는 별개 기능.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services.doc_digitize_client import (
    DocConfigError,
    DocConnectionError,
    DocDigitizeError,
    digitize,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/digitize", tags=["문서 디지털화"])

_MAX_BYTES = 50 * 1024 * 1024  # 50 MiB (DOC 현재 기본 제한)


def _require_admin(current_user: dict) -> None:
    if current_user.get("role_code") != "001":
        raise HTTPException(403, "문서 디지털화는 관리자(role_code=001) 전용입니다")


def _require_company_id(current_user: dict) -> str:
    cid = (current_user.get("company_id") or "").strip()
    if not cid:
        raise HTTPException(403, "company_id가 없는 계정은 디지털화를 실행할 수 없습니다")
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
    current_user: dict = Depends(get_current_user),
):
    """파일을 DOC에 전송해 디지털화 처리 결과 ID를 반환합니다.

    - 중복 파일: duplicate=true, doc_log_id만 반환
    - 신규 파일: primitive_id·v2_status 등 포함
    - DOC 오류 메시지는 TAI 로그에만 기록 (사용자 미노출)
    """
    _require_admin(current_user)
    company_id = _require_company_id(current_user)
    _verify_company_exists(company_id)

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
        # extraction_storage_ref: DOC doc-extractions 버킷 경로.
        # None = 저장 실패 또는 중복 응답.
        # 참조 존재가 MAP-02용 JSON 확보를 보장하지 않음 — 현재 운영 추출은 Markdown.
        "extraction_storage_ref": result.extraction_storage_ref,
    }
    if result.storage_warning:
        # DOC 내부 저장 오류 원문 미노출 — 일반 안내로 치환
        response["storage_warning"] = "원본 파일 저장이 완료되지 않았습니다. 관리자 확인이 필요합니다."
    if result.extraction_storage_warning:
        response["extraction_storage_warning"] = "추출 결과 저장이 완료되지 않았습니다. 관리자 확인이 필요합니다."
    return response
