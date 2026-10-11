"""WO-008: Deliverable C — SaaS Appendix3 safe-route contract gate.

Called from route handlers AFTER auth/entitlement and BEFORE assembler/LEG/C10.

Flag OFF (SAAS_APP3_ENABLED=false, default):
  - New classification fields absent → None (no-op; old callers unchanged).
  - New classification fields present → 422 (unsupported gate).

Flag ON (SAAS_APP3_ENABLED=true):
  - Validates item/subtype types and ranges.
  - Calls existing validate_explicit_construction_predicates for CONSTRUCTION.
  - Reads authorized stored record from factory_legal_classifications.
  - Compares request facts vs stored item/subtype/sector/law_version.
  - Checks expected_app3_revision if provided (409 if stale).
  - Returns server-generated AP01-05 projection dict for LEG injection.

Control fields (expected_app3_revision): never injected into LEG source.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from fastapi import HTTPException

from services.canonical.explicit_appendix3_classification import (
    APPENDIX3_LAW_VERSION_ID,
    Appendix3SourceError,
    project_explicit_appendix3_classification,
    validate_explicit_appendix3_classification,
)
from services.canonical.explicit_construction_predicates import (
    validate_explicit_construction_predicates,
)
from services.legal_rules import normalize_sector_db

SAAS_APP3_ENABLED: bool = os.getenv("SAAS_APP3_ENABLED", "false").lower() == "true"

_APP3_NEW_FIELDS = (
    "appendix3_item_no",
    "is_real_estate_management",
    "expected_app3_revision",
    "is_relationship_contractor",
    "is_civil_construction",
)


def _has_app3_fields(consumer_input: Any) -> bool:
    for field in _APP3_NEW_FIELDS:
        if getattr(consumer_input, field, None) is not None:
            return True
    return False


def check_saas_appendix3_contract(
    supabase,
    factory_id: str,
    sector: str,
    consumer_input: Any,
) -> Optional[Dict[str, Any]]:
    """Validate App3 contract and return AP01-05 server projection or None.

    Returns None when flag OFF and no new fields (no-op path).
    Raises HTTPException on any validation or mismatch failure.
    """
    has_fields = _has_app3_fields(consumer_input)

    if not SAAS_APP3_ENABLED:
        if has_fields:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "SAAS_APP3_NOT_ENABLED",
                    "detail": "별표3 분류 필드는 SAAS_APP3_ENABLED 플래그 활성화 후 사용 가능합니다",
                },
            )
        return None

    # ── Flag ON path ──
    normalized_sector = normalize_sector_db(str(sector or ""))

    # R5: Use canonical validator for item type/range/item37-subtype completeness.
    validate_explicit_appendix3_classification(consumer_input, sector)

    # Extract after canonical validation passes (types are now guaranteed safe).
    item_no = getattr(consumer_input, "appendix3_item_no", None)
    subtype = getattr(consumer_input, "is_real_estate_management", None)
    expected_revision = getattr(consumer_input, "expected_app3_revision", None)

    # SaaS-specific: non-37 subtype must be absent (canonical does not check this).
    if item_no != 37 and subtype is not None:
        raise HTTPException(
            status_code=422,
            detail={"code": "APPENDIX3_SUBTYPE_NON37", "detail": "is_real_estate_management은 항목 37에만 유효합니다"},
        )

    # CONSTRUCTION: child predicate gate (is_relationship_contractor, is_civil_construction for item 49)
    if normalized_sector == "CONSTRUCTION":
        validate_explicit_construction_predicates(consumer_input, sector)

    # ── Stored record comparison ──
    from services.factory_legal_classification_svc import get_factory_legal_classification
    stored = get_factory_legal_classification(supabase, factory_id)
    if stored is None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CLASSIFICATION_NOT_CONFIRMED",
                "detail": "시설의 별표3 분류가 확인되지 않았습니다. 진단 전에 먼저 분류를 확인하세요.",
            },
        )

    # R7: Re-read authoritative factory sector — stored confirmed_sector may be stale.
    frow = supabase.table("factories").select("sector").eq("id", factory_id).limit(1).execute()
    fdata = getattr(frow, "data", None) or []
    if not fdata:
        raise HTTPException(
            status_code=404,
            detail={"code": "FACTORY_NOT_FOUND", "detail": "시설을 찾을 수 없습니다"},
        )
    current_factory_sector = normalize_sector_db(str(fdata[0].get("sector") or ""))
    if current_factory_sector != normalized_sector:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "SECTOR_DRIFT",
                "detail": (
                    f"현재 시설 섹터({current_factory_sector})와 요청 섹터({normalized_sector})가 다릅니다. "
                    "현재 섹터로 재확인이 필요합니다."
                ),
            },
        )

    stored_item: Optional[int] = stored.get("appendix3_item_no")
    stored_subtype: Optional[bool] = stored.get("is_real_estate_management")
    stored_sector: Optional[str] = stored.get("confirmed_sector")
    stored_law_version: str = str(stored.get("appendix3_law_version_id") or "")
    stored_revision: Optional[int] = stored.get("revision")

    if item_no != stored_item:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CLASSIFICATION_MISMATCH",
                "detail": f"요청 항목({item_no})이 확인된 분류({stored_item})와 다릅니다",
            },
        )
    if subtype != stored_subtype:
        raise HTTPException(
            status_code=409,
            detail={"code": "CLASSIFICATION_MISMATCH", "detail": "is_real_estate_management 불일치"},
        )
    if stored_sector != normalized_sector:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "SECTOR_DRIFT",
                "detail": f"확인된 분류 섹터({stored_sector})와 요청 섹터({normalized_sector})가 다릅니다. 현재 섹터로 재확인이 필요합니다.",
            },
        )
    if stored_law_version != APPENDIX3_LAW_VERSION_ID:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "LAW_VERSION_MISMATCH",
                "detail": "확인된 분류의 법령 버전이 현행과 다릅니다. 재확인이 필요합니다.",
            },
        )

    # R6: expected_app3_revision is required on flag-ON path (snapshot version protection).
    if expected_revision is None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "APPENDIX3_REVISION_REQUIRED",
                "detail": "SAAS_APP3_ENABLED=true 환경에서는 expected_app3_revision을 제공해야 합니다.",
            },
        )
    if expected_revision != stored_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "STALE_REVISION",
                "detail": f"expected_app3_revision {expected_revision} != 저장된 revision {stored_revision}",
            },
        )

    # ── Server AP01-05 projection (server-owned; client-supplied leaves rejected by caller) ──
    try:
        projection = project_explicit_appendix3_classification(item_no, subtype)
    except Appendix3SourceError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": exc.code, "detail": exc.message},
        ) from exc

    return projection
