"""WP-PERSISTENCE-03 STEP-2 — 점검 결과 Web View read endpoint.

canonical runtime:
    authenticated caller
    → ownership/scope guard (_ensure_inspection_own)
    → READ-ONLY Composer (compose_inspection_view)
    → GENERAL View Model
    → HTTP response

invariant:
    - AUTH BEFORE COMPOSE: get_current_user → ownership guard → composer (순서 고정).
    - GET side effect = 0 (write/문서생성/PDF/storage 없음).
    - Composer domain 예외만 명시적 HTTP 변환; ownership guard 의 HTTPException 은 그대로 전파.
    - 내부 detail(UUID/schema 상태/table 이름 등) 을 public response 로 노출하지 않는다.
    - Composer(services/inspection_view_composer.py) 는 SEALED — compose 결과는 판단 규칙 없이 반환.
    - post-compose 프레젠테이션만 additive: allowlisted storage://company-docs/<path> 만
      short-lived signed URL 로 변환. 미등록/타사/다른 inspection ref 는 서명하지 않는다.
      legacy http(s) 는 그대로 통과. 서명 실패는 해당 필드만 원본 유지(화면 전체 실패 금지).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from routers.inspection_checklist import _ensure_inspection_own, resolve_inspection_owner_scope
from services.document_svc import BUCKET as COMPANY_DOCS_BUCKET
from services.inspection_view_composer import (
    InspectionViewComposeError,
    compose_inspection_view,
)

router = APIRouter(
    prefix="/inspection",
    tags=["점검 결과 Web View"],
)

# Composer domain error → HTTP status.
# INSPECTION_NOT_FOUND 만 404; 그 외 domain-state 오류는 409(요청 형식이 아니라
# 현재 source/config/state 로 Web View 를 안전하게 구성할 수 없는 상태).
_NOT_FOUND_CODE = "INSPECTION_NOT_FOUND"

STORAGE_REF_PREFIX = "storage://company-docs/"
PHOTO_SIGNED_TTL_SECONDS = 600


def _storage_path_from_ref(value):
    if not isinstance(value, str):
        return None
    if not value.startswith(STORAGE_REF_PREFIX):
        return None
    path = value[len(STORAGE_REF_PREFIX):]
    return path or None


def _collect_storage_photo_paths(rows):
    paths = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        for value in (row.get("photo_url"),):
            path = _storage_path_from_ref(value)
            if path and path not in seen:
                seen.add(path)
                paths.append(path)
        urls = row.get("photo_urls")
        if isinstance(urls, list):
            for value in urls:
                path = _storage_path_from_ref(value)
                if path and path not in seen:
                    seen.add(path)
                    paths.append(path)
    return paths


def _load_allowed_photo_paths(sb, inspection_id, company_id, paths):
    """documents 1회 batch. 소유 inspection 에 등록된 active path 만 allow."""
    if not company_id or not paths:
        return set()
    try:
        res = (
            sb.table("documents")
            .select("storage_path")
            .eq("bucket_id", COMPANY_DOCS_BUCKET)
            .eq("linked_table", "safety_inspections")
            .eq("linked_id", inspection_id)
            .eq("company_id", company_id)
            .eq("is_active", True)
            .is_("deleted_at", "null")
            .in_("storage_path", paths)
            .execute()
        )
    except Exception:
        return set()
    allowed = set()
    for row in (res.data or []):
        sp = row.get("storage_path")
        if isinstance(sp, str) and sp:
            allowed.add(sp)
    return allowed


def _sign_allowed_storage_ref(sb, value, allowed_paths):
    """allowlisted storage://company-docs/<path> → signed URL. 그 외는 원본 유지."""
    if not isinstance(value, str):
        return value
    if value.startswith("http://") or value.startswith("https://"):
        return value
    path = _storage_path_from_ref(value)
    if not path or path not in allowed_paths:
        return value
    try:
        result = sb.storage.from_(COMPANY_DOCS_BUCKET).create_signed_url(
            path, PHOTO_SIGNED_TTL_SECONDS
        )
    except Exception:
        return value
    if isinstance(result, dict):
        signed = result.get("signedURL") or result.get("signed_url")
        if signed:
            return signed
    return value


def apply_inspection_view_photo_signing(vm, sb, inspection_id):
    """Composer 결과의 photo_url/photo_urls 만 in-place 변환(allowlist). 판단 규칙 변경 없음."""
    if not isinstance(vm, dict):
        return vm
    fields = vm.get("fields")
    if not isinstance(fields, dict):
        return vm
    rows = fields.get("inspection_results")
    if not isinstance(rows, list):
        return vm

    paths = _collect_storage_photo_paths(rows)
    company_id = None
    if paths:
        try:
            company_id = resolve_inspection_owner_scope(sb, inspection_id).get("company_id")
        except HTTPException:
            company_id = None
    allowed = _load_allowed_photo_paths(sb, inspection_id, company_id, paths)

    for row in rows:
        if not isinstance(row, dict):
            continue
        if "photo_url" in row:
            row["photo_url"] = _sign_allowed_storage_ref(sb, row.get("photo_url"), allowed)
        urls = row.get("photo_urls")
        if isinstance(urls, list):
            row["photo_urls"] = [_sign_allowed_storage_ref(sb, u, allowed) for u in urls]
    return vm


@router.get("/{inspection_id}/view")
async def get_inspection_view(
    inspection_id: str,
    current: dict = Depends(get_current_user),
):
    """점검 1건의 GENERAL presentation View Model 을 반환 (READ-ONLY).

    AUTH BEFORE COMPOSE. ownership guard 통과 후에만 Composer 를 호출한다.
    """
    sb = get_supabase()

    # 1) AUTH BEFORE COMPOSE — 미소유/미해소 row 는 여기서 404 로 은닉된다.
    _ensure_inspection_own(sb, inspection_id, current)

    # 2) READ-ONLY compose (동일 sb instance 재사용)
    try:
        vm = compose_inspection_view(inspection_id, supabase=sb)
    except InspectionViewComposeError as exc:
        if exc.code == _NOT_FOUND_CODE:
            raise HTTPException(
                status_code=404,
                detail={"code": _NOT_FOUND_CODE, "message": "점검 레코드를 찾을 수 없습니다."},
            )
        # 내부 exc.detail 은 노출하지 않는다 (code 만 전달).
        raise HTTPException(
            status_code=409,
            detail={"code": exc.code, "message": "점검 결과 화면을 구성할 수 없습니다."},
        )

    # 3) post-compose presentation (composer SEALED — allowlisted 서명만 additive)
    return apply_inspection_view_photo_signing(vm, sb, inspection_id)
