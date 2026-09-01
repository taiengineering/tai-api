#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
routers/factory_legal_diagnosis.py — Safe INDUSTRIAL 법령진단 facility supplemental profile
WO-SAFE-LEGAL-IND-IMPLEMENT-001 / STEP 3 (STEP3-PATCH-1).

기존 factories 라우팅 surface(prefix=/factories) 확장 — routers/factories.py(20KB) 무수정(0-drift).
auth(get_current_user) + factory existence + ownership(_ensure_factory_own) + get_supabase 재사용.
persistence 만 담당(assembler / input-preview / run-leg / process·equipment wiring 미포함 — 후속 STEP).

STEP3-PATCH-1: factory existence gate 추가. 기존 _ensure_factory_own 은 ALL 관리자면 즉시 return 하므로
존재하지 않는 factory 를 관리자에게 404 로 막지 못한다. 아래 좁은 helper 가 존재확인(없으면 404)을
선행한 뒤 기존 ownership helper 를 호출한다. services/company_scope 는 미수정(공통 foundation 보호).

R2 STEP3: PUT 은 body.dict(exclude_unset=True) 로 sparse partial-merge(omitted 보존/explicit NULL clear). 나머지 무변.
"""
from fastapi import APIRouter, Depends, HTTPException
from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services.company_scope import _ensure_factory_own
from services.safe_industrial_legal_profile_svc import (
    LegalDiagnosisProfileBody,
    get_profile as _fldp_get,
    upsert_profile as _fldp_upsert,
    validate_profile as _fldp_validate,
    load_marketing_vocab as _fldp_vocab,
)

router = APIRouter(prefix="/factories", tags=["factories"])


def _ensure_profile_factory_access(supabase, factory_id: str, current: dict) -> None:
    """factory 존재확인 후 기존 ownership 검증. 순서: existence → ownership.

    ALL 관리자라도 존재하지 않는 factory 는 여기서 404(기존 _ensure_factory_own 의 admin 조기 return
    우회 방지). company_scope 는 변경하지 않는다. 비관리자 회사경계 의미는 _ensure_factory_own 그대로.
    """
    r = (
        supabase.table("factories")
        .select("id")
        .eq("id", factory_id)
        .limit(1)
        .execute()
    )
    if not getattr(r, "data", None):
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다")
    _ensure_factory_own(supabase, factory_id, current)


@router.get("/{factory_id}/legal-diagnosis/profile")
def get_legal_diagnosis_profile(factory_id: str, current: dict = Depends(get_current_user)):
    """현재 factory 의 facility supplemental profile 조회. 없으면 empty representation(DB mutation 0)."""
    supabase = get_supabase()
    _ensure_profile_factory_access(supabase, factory_id, current)   # existence → ownership (missing/foreign 404)
    return {"status": "success", "data": _fldp_get(supabase, factory_id)}


@router.put("/{factory_id}/legal-diagnosis/profile")
def put_legal_diagnosis_profile(
    factory_id: str,
    body: LegalDiagnosisProfileBody,
    current: dict = Depends(get_current_user),
):
    """facility supplemental profile sparse partial-merge upsert.
    순서: auth → existence → ownership → vocabulary → validate → upsert.
    타사/없는 factory 는 vocabulary/profile 을 읽기 전에 차단. contract_version 은 server 고정."""
    supabase = get_supabase()
    _ensure_profile_factory_access(supabase, factory_id, current)
    vocab = _fldp_vocab(supabase)
    cleaned = _fldp_validate(body.dict(exclude_unset=True), vocab)  # R2: sparse partial-merge (omitted 보존/explicit NULL clear)
    return {
        "status": "success",
        "message": "법령진단 추가정보가 저장됐습니다",
        "data": _fldp_upsert(supabase, factory_id, cleaned),
    }
