"""WO-008: Deliverable B — factory legal-classification service.

Service-role-only: reads/writes public.factory_legal_classifications.
No client-supplied confirmed_by / confirmed_at / law_version accepted.
CAS enforced at DB write predicate (factory_id + revision).
Factory sector drift check before each confirm.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import HTTPException

from services.canonical.explicit_appendix3_classification import (
    APPENDIX3_LAW_VERSION_ID,
    APPENDIX3_ITEM_MIN,
    APPENDIX3_ITEM_MAX,
    is_strict_int,
    is_strict_bool,
)
from services.legal_rules import normalize_sector_db

_TABLE = "factory_legal_classifications"
_GATED_SECTORS = frozenset({"BUILDING", "INDUSTRIAL", "CONSTRUCTION"})


def get_factory_legal_classification(
    supabase, factory_id: str
) -> Optional[Dict[str, Any]]:
    """Read current classification. Returns None if no record exists."""
    res = (
        supabase.table(_TABLE)
        .select("*")
        .eq("factory_id", factory_id)
        .limit(1)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    return rows[0] if rows else None


def _read_factory_sector(supabase, factory_id: str) -> str:
    """Read factory sector. 404 if not found."""
    frow = (
        supabase.table("factories")
        .select("sector")
        .eq("id", factory_id)
        .limit(1)
        .execute()
    )
    fdata = getattr(frow, "data", None) or []
    if not fdata:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다")
    return normalize_sector_db(str(fdata[0].get("sector") or ""))


def _validate_confirm_inputs(
    appendix3_item_no: Any,
    is_real_estate_management: Any,
    confirmed_sector: str,
) -> str:
    """Validate and normalize inputs. Returns normalized sector. Raises 422 on failure."""
    if not is_strict_int(appendix3_item_no):
        raise HTTPException(
            status_code=422,
            detail={"code": "APPENDIX3_ITEM_NO_TYPE", "detail": "integer 1..49 required"},
        )
    if not APPENDIX3_ITEM_MIN <= appendix3_item_no <= APPENDIX3_ITEM_MAX:
        raise HTTPException(
            status_code=422,
            detail={"code": "APPENDIX3_ITEM_NO_RANGE", "detail": "integer 1..49 required"},
        )
    if appendix3_item_no == 37:
        if is_real_estate_management is not None and not is_strict_bool(is_real_estate_management):
            raise HTTPException(
                status_code=422,
                detail={"code": "APPENDIX3_SUBTYPE_TYPE", "detail": "boolean required for item 37"},
            )
        # R4: item37 subtype must be explicitly true or false at confirm time.
        if is_real_estate_management is None:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "APPENDIX3_EXPLICIT_CLASSIFICATION_REQUIRED",
                    "missing_fields": ["is_real_estate_management"],
                    "detail": "항목 37은 is_real_estate_management를 명시해야 합니다 (true 또는 false).",
                },
            )
    else:
        if is_real_estate_management is not None:
            raise HTTPException(
                status_code=422,
                detail={"code": "APPENDIX3_SUBTYPE_NON37", "detail": "is_real_estate_management must be null for item != 37"},
            )
    normalized_sector = normalize_sector_db(str(confirmed_sector or ""))
    if normalized_sector not in _GATED_SECTORS:
        raise HTTPException(
            status_code=422,
            detail={"code": "CONFIRMED_SECTOR_INVALID", "detail": "sector must be BUILDING, INDUSTRIAL, or CONSTRUCTION"},
        )
    return normalized_sector


def confirm_factory_legal_classification(
    supabase,
    *,
    factory_id: str,
    appendix3_item_no: int,
    is_real_estate_management: Optional[bool],
    confirmed_sector: str,
    expected_revision: Optional[int],
    confirmed_by: str,
) -> Dict[str, Any]:
    """Confirm / update factory legal classification with CAS.

    First insert: expected_revision must be None.
    Update: expected_revision must equal current stored revision.
    Returns the upserted record row.

    HTTP errors:
      404 — factory not found or foreign factory
      409 — stale revision, concurrent race, or sector drift
      422 — invalid item/subtype/sector inputs
      503 — DB write failure
    """
    normalized_sector = _validate_confirm_inputs(
        appendix3_item_no, is_real_estate_management, confirmed_sector
    )

    # Sector consistency: confirmed_sector must match factory's actual sector.
    factory_sector = _read_factory_sector(supabase, factory_id)
    if factory_sector != normalized_sector:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "SECTOR_DRIFT",
                "detail": (
                    f"시설 섹터({factory_sector})와 확인 요청 섹터({normalized_sector})가 다릅니다. "
                    "현재 섹터로 재확인이 필요합니다."
                ),
            },
        )

    current = get_factory_legal_classification(supabase, factory_id)

    if current is None:
        # First insert — expected_revision must be absent.
        if expected_revision is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "STALE_REVISION",
                    "detail": "기존 분류 기록이 없습니다. 최초 확인 시 expected_revision을 생략하세요.",
                },
            )
        payload: Dict[str, Any] = {
            "factory_id": factory_id,
            "appendix3_item_no": appendix3_item_no,
            "is_real_estate_management": is_real_estate_management,
            "appendix3_law_version_id": APPENDIX3_LAW_VERSION_ID,
            "confirmed_sector": normalized_sector,
            "confirmed_by": confirmed_by,
            "revision": 1,
        }
        try:
            res = supabase.table(_TABLE).insert(payload).execute()
        except Exception as exc:
            _es = str(exc).lower()
            if "unique" in _es or "duplicate" in _es or "23505" in _es:
                raise HTTPException(
                    status_code=409,
                    detail={"code": "CONCURRENT_INSERT_CONFLICT", "detail": "동시 최초 확인 경쟁 발생. 다시 조회 후 재시도하세요."},
                ) from exc
            raise HTTPException(
                status_code=503,
                detail={"code": "DB_WRITE_ERROR", "detail": str(exc)},
            ) from exc
        rows = getattr(res, "data", None) or []
        if not rows:
            raise HTTPException(
                status_code=503,
                detail={"code": "DB_WRITE_EMPTY", "detail": "insert returned no data"},
            )
        return rows[0]

    else:
        # CAS update — expected_revision must match current.
        current_revision = current["revision"]
        if expected_revision is None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "STALE_REVISION",
                    "detail": f"기존 분류 기록이 있습니다 (revision={current_revision}). expected_revision을 제공하세요.",
                },
            )
        if expected_revision != current_revision:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "STALE_REVISION",
                    "detail": f"expected_revision {expected_revision} != 현재 revision {current_revision}",
                },
            )
        new_revision = current_revision + 1
        # CAS at DB predicate: WHERE factory_id=X AND revision=current_revision.
        # If 0 rows updated → concurrent race won.
        try:
            res = (
                supabase.table(_TABLE)
                .update({
                    "appendix3_item_no": appendix3_item_no,
                    "is_real_estate_management": is_real_estate_management,
                    "appendix3_law_version_id": APPENDIX3_LAW_VERSION_ID,
                    "confirmed_sector": normalized_sector,
                    "confirmed_by": confirmed_by,
                    "confirmed_at": datetime.now(timezone.utc).isoformat(),
                    "revision": new_revision,
                })
                .eq("factory_id", factory_id)
                .eq("revision", current_revision)
                .execute()
            )
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail={"code": "DB_WRITE_ERROR", "detail": str(exc)},
            ) from exc
        rows = getattr(res, "data", None) or []
        if not rows:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "STALE_REVISION",
                    "detail": "동시 업데이트 경쟁 패배. 최신 revision 조회 후 재시도하세요.",
                },
            )
        return rows[0]
