"""Internal MSDS Reference Candidate Query API.

Endpoint:
  POST /internal/reference/msds/candidates

Auth: X-Internal-Secret header (INTERNAL_API_SECRET env) → 403 on failure.
Read-only: INSERT/UPDATE/DELETE = 0.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel

log = logging.getLogger("internal_reference_query")

router = APIRouter(prefix="/internal/reference/msds", tags=["internal-reference-query"])


def _auth(x_internal_secret: Optional[str]) -> None:
    expected = os.environ.get("INTERNAL_API_SECRET")
    if not expected or x_internal_secret != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid internal secret")


class CandidateQueryRequest(BaseModel):
    snapshot_id: str
    cas_list: List[str] = []
    product_name_normalized: Optional[str] = None


@router.post("/candidates")
def query_msds_candidates(
    body: CandidateQueryRequest,
    x_internal_secret: Optional[str] = Header(None, alias="X-Internal-Secret"),
) -> Dict[str, Any]:
    _auth(x_internal_secret)

    from services.msds_reference_query_svc import (
        SnapshotNotReadyError,
        ReferenceQueryError,
        find_candidates,
        validate_snapshot,
    )

    try:
        validate_snapshot(body.snapshot_id)
    except SnapshotNotReadyError as exc:
        log.warning("snapshot not ready: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except ReferenceQueryError as exc:
        log.error("reference query config error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    except Exception as exc:
        log.exception("snapshot validation failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"REFERENCE_QUERY_FAILED: {exc}",
        )

    try:
        items = find_candidates(
            snapshot_id=body.snapshot_id,
            cas_list=body.cas_list,
            product_name_normalized=body.product_name_normalized,
        )
    except Exception as exc:
        log.exception("find_candidates failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"REFERENCE_QUERY_FAILED: {exc}",
        )

    return {
        "status": "success",
        "data": {
            "snapshot_id": body.snapshot_id,
            "items": items,
        },
    }
