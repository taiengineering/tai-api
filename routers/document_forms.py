from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response as _FileResponse

from storage3.exceptions import StorageApiError

from db.supabase_client import get_supabase
from routers.auth import get_current_user, get_current_user_optional
from services.company_scope import _require_admin
from services.document_engine.r2_route_policy import get_provision_policy
from services.document_engine.source_file_allowlist import get_verified_path, source_file_bucket
from services.document_forms_service import (
    get_document_form,
    get_document_form_articles,
    get_document_forms_stats,
    list_document_forms,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/document-forms", tags=["document-forms"])


@router.get("")
def list_forms(
    sector: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    tai_grade: Optional[str] = Query(None),
    tab_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=200),
):
    # [17] 화면 unwrapFormList 는 {status, data:{items,...}} 봉투를 기대한다.
    #   다른 라우터(factories·org·tbm)와 달리 이 목록만 봉투 없이 반환해
    #   resp.data 가 undefined → 항상 빈 목록("등록된 서식이 없습니다")이었다.
    return {
        "status": "success",
        "data": list_document_forms(
            sector=sector,
            category=category,
            tai_grade=tai_grade,
            tab_type=tab_type,
            search=search,
            page=page,
            per_page=per_page,
        ),
    }


@router.get("/stats")
def forms_stats():
    return get_document_forms_stats()


@router.get("/{doc_id}/articles")
def form_articles(
    doc_id: str,
    include_pending: bool = Query(False, description="PENDING 상태 매핑 포함 여부"),
    current_user: Optional[dict] = Depends(get_current_user_optional),
):
    """서식에 연결된 공용 조문 목록 조회.

    field_rule_mapping → law_article 경로로 조회한다.
    PENDING 매핑은 is_confirmed=False 표시. 고시 제6조 자동 추론 금지.
    include_pending=true는 플랫폼 관리자(role_code=ALL scope)만 요청 가능.
    """
    if include_pending:
        if current_user is None:
            raise HTTPException(status_code=401, detail="인증이 필요합니다")
        _require_admin(current_user, get_supabase())
    return get_document_form_articles(doc_id, include_pending=include_pending)


@router.get("/{doc_id}/source-file")
def get_source_file(
    doc_id: str,
    current_user: dict = Depends(get_current_user),
):
    """수집된 서식 원본 파일 다운로드 (회원 전용).

    doc_id 형식 검증 → route_group 정책 확인 → 활성 문서 확인 → storage 조회 순서.
    F_SCOPE_OUT(범위 외)·A_INTERNAL(웹생성 경로) 문서는 서버에서 차단.
    스토리지 접근 실패는 503 (파일 없음 404와 구분).
    서명 URL·경로는 응답에 포함되지 않음.
    """
    # Gate 1: doc_id 형식 검증 → 표준 경로 계산
    storage_path = get_verified_path(doc_id)
    if storage_path is None:
        raise HTTPException(status_code=404, detail="유효하지 않은 서식 ID입니다.")

    # Gate 2: route_group 정책 — 파일 다운로드 비대상 차단
    provision_policy = get_provision_policy(doc_id)
    if provision_policy is not None:
        rg = provision_policy.get("route_group")
        if rg in ("F_SCOPE_OUT", "A_INTERNAL"):
            raise HTTPException(status_code=404, detail="서식 파일 다운로드를 지원하지 않는 문서입니다.")

    # Gate 3: 경로 무결성 방어적 재확인
    if not storage_path.startswith("doc_forms/") or ".." in storage_path:
        log.error("storage path integrity violation: doc_id=%s path=%s", doc_id, storage_path)
        raise HTTPException(status_code=404, detail="유효하지 않은 서식 ID입니다.")

    # Gate 4: 활성 문서 확인
    supabase = get_supabase()
    form_res = (
        supabase.table("document_forms")
        .select("id, doc_id")
        .eq("doc_id", doc_id)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    if not form_res.data:
        raise HTTPException(status_code=404, detail="서식 문서를 찾을 수 없습니다.")

    # Gate 5: doc_forms/ 직접 경로 — 파일 없음(404) vs. 접근 실패(503) 구분
    # Supabase storage SDK는 파일 없음도 StorageApiError(status=400)로 반환한다.
    # status 400 = "Object not found" → 404. 그 외 SDK 오류 = 503.
    try:
        file_bytes: bytes = supabase.storage.from_(source_file_bucket()).download(storage_path)
    except StorageApiError as exc:
        status = int(exc.status) if exc.status else 0
        if status in (400, 404):
            raise HTTPException(status_code=404, detail="서식 파일을 아직 제공하지 않습니다.")
        raise HTTPException(status_code=503, detail="서식 파일을 불러올 수 없습니다. 잠시 후 다시 시도해 주세요.")
    except Exception:
        raise HTTPException(status_code=503, detail="서식 파일을 불러올 수 없습니다. 잠시 후 다시 시도해 주세요.")

    if not file_bytes:
        # doc_forms/ 에 파일 없음.
        # FORM647 원장(form647_review)과의 doc_id → ek 크로스워크가 현재 미확립.
        # document_forms.file_url의 flSeq ≠ FORM647 ek (별도 식별자).
        # 연결 가능 경로가 확인되면 이 위치에 fallback을 추가한다.
        raise HTTPException(status_code=404, detail="서식 파일을 아직 제공하지 않습니다.")

    filename = f"{doc_id}.hwp"
    return _FileResponse(
        content=file_bytes,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        },
    )


@router.get("/{doc_id}")
def form_detail(doc_id: str):
    return get_document_form(doc_id)
