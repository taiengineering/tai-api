"""services/doc_site_context.py — 사업장별 문서 처리 권한 검증.

WO-TAI-DOC-SITE-CONTEXT-GUARD-001

기존 TAI 회사·사업장 권한 체계(company_scope.py)를 재사용하여
문서 처리 대상 사업장이 현재 사용자에게 허용된 범위인지 확인한다.

현재 총어드민 업로드 API(document_digitize.py)에 연결하지 않는다.
운영 DB 쓰기 없음. DB 컬럼·RPC·Storage 변경 없음.
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException

from services.company_scope import (
    _ensure_factory_company_match,
    _scope,
)


@dataclass(frozen=True)
class SiteContextResult:
    company_id: str
    factory_id: str
    scope_type: str


def resolve_document_site_context(
    current_user: dict,
    company_id: str | None,
    factory_id: str | None,
    supabase,
) -> SiteContextResult:
    """문서 처리 대상 사업장이 현재 사용자에게 허용된 범위인지 확인한다.

    반환: 검증된 (company_id, factory_id, scope_type)
    차단: HTTPException(403) — 허용되지 않은 범위·누락값·알 수 없는 권한
    """
    if not company_id or not company_id.strip():
        raise HTTPException(status_code=403, detail="company_id가 필요합니다")
    if not factory_id or not factory_id.strip():
        raise HTTPException(status_code=403, detail="factory_id가 필요합니다")

    company_id = company_id.strip()
    factory_id = factory_id.strip()

    try:
        scope = _scope(supabase, current_user.get("role_code"))
    except Exception:
        raise HTTPException(status_code=403, detail="권한 확인 중 오류가 발생했습니다")

    if scope == "ALL":
        # 총어드민: 지정 회사·사업장 소속 관계 확인 후 허용
        _ensure_factory_company_match(supabase, factory_id, company_id)
        return SiteContextResult(company_id=company_id, factory_id=factory_id, scope_type=scope)

    if scope == "COMPANY":
        token_cid = current_user.get("company_id") or ""
        if company_id != token_cid:
            raise HTTPException(status_code=403, detail="타사 사업장에 접근할 수 없습니다")
        _ensure_factory_company_match(supabase, factory_id, company_id)
        return SiteContextResult(company_id=company_id, factory_id=factory_id, scope_type=scope)

    if scope in ("FACTORY", "TEAM"):
        # TEAM은 E-2 이전까지 FACTORY와 동일하게 처리
        token_cid = current_user.get("company_id") or ""
        if company_id != token_cid:
            raise HTTPException(status_code=403, detail="타사 사업장에 접근할 수 없습니다")
        token_fid = current_user.get("factory_id") or ""
        if not token_fid:
            raise HTTPException(status_code=403, detail="사업장 배정이 필요합니다")
        if factory_id != token_fid:
            raise HTTPException(status_code=403, detail="배정된 사업장이 아닙니다")
        return SiteContextResult(company_id=company_id, factory_id=factory_id, scope_type=scope)

    if scope == "ASSIGNED":
        # 문서 권한 계약 확정 전 차단
        raise HTTPException(status_code=403, detail="문서 접근 권한 계약이 확정되지 않았습니다")

    # 알 수 없는 권한
    raise HTTPException(status_code=403, detail="알 수 없는 권한입니다")
