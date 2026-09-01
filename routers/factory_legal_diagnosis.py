#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
routers/factory_legal_diagnosis.py — Safe INDUSTRIAL 법령진단 facility supplemental profile
WO-SAFE-LEGAL-IND-IMPLEMENT-001 / STEP 3.

기존 factories 라우팅 surface(prefix=/factories) 확장 — routers/factories.py(20KB) 무수정(0-drift).
auth(get_current_user) + ownership(_ensure_factory_own) + get_supabase 재사용. persistence 만 담당
(assembler / input-preview / run-leg / process·equipment wiring 미포함 — 후속 STEP).
"""
from fastapi import APIRouter, Depends
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


@router.get("/{factory_id}/legal-diagnosis/profile")
def get_legal_diagnosis_profile(factory_id: str, current: dict = Depends(get_current_user)):
    """현재 factory 의 facility supplemental profile 조회. 없으면 empty representation(DB mutation 0)."""
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)   # foreign/missing → 404 (기존 convention)
    return {"status": "success", "data": _fldp_get(supabase, factory_id)}


@router.put("/{factory_id}/legal-diagnosis/profile")
def put_legal_diagnosis_profile(
    factory_id: str,
    body: LegalDiagnosisProfileBody,
    current: dict = Depends(get_current_user),
):
    """facility supplemental profile idempotent upsert. ownership 선검증 후 DB 접근.
    body(extra=forbid)가 server-managed/미허용 key 를 422 거부. contract_version 은 server 고정."""
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)
    vocab = _fldp_vocab(supabase)
    cleaned = _fldp_validate(body.dict(), vocab)
    return {
        "status": "success",
        "message": "법령진단 추가정보가 저장됐습니다",
        "data": _fldp_upsert(supabase, factory_id, cleaned),
    }
