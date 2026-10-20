"""
routers/document_catalog.py
WO-TAI-DOC-UNIFIED-CATALOG-IMPLEMENT-001 — Phase 1

GET /api/document-catalog        — unified document list (SAAS + REFERENCE_CMS)
GET /api/document-catalog/{key}  — single document detail by provisional key

Status: PROPOSED — not deployed
Source/DB mutations: 0
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from services.catalog_aggregator import (
    CatalogItem,
    SupabaseRestClient,
    get_document_detail,
    get_unified_catalog,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/document-catalog", tags=["Document catalog"])


# ---------------------------------------------------------------------------
# Serialisation helpers (dataclasses → plain dicts; no raw storage paths)
# ---------------------------------------------------------------------------

def _channel_to_dict(ch: Any) -> dict[str, Any]:
    d: dict[str, Any] = {"state": ch.state, "reason": ch.reason}
    if ch.action_url is not None:
        d["action_url"] = ch.action_url
    return d


def _item_to_dict(item: CatalogItem) -> dict[str, Any]:
    return {
        "provisional_key": item.provisional_key,
        "source_system": item.source_system,
        "source_code": item.source_code,
        "title": item.title,
        "normalized_title": item.normalized_title,
        "sector": item.sector,
        "category": item.category,
        "official_flag": item.official_flag,
        "format_flag": item.format_flag,
        "channels": {
            "REFERENCE_DOWNLOAD": _channel_to_dict(item.channels.REFERENCE_DOWNLOAD),
            "OFFICIAL_ORIGINAL": _channel_to_dict(item.channels.OFFICIAL_ORIGINAL),
            "WEB_EDIT": _channel_to_dict(item.channels.WEB_EDIT),
            "SAAS_EXPORT": _channel_to_dict(item.channels.SAAS_EXPORT),
            "SAAS_AUTO_FILL": _channel_to_dict(item.channels.SAAS_AUTO_FILL),
        },
        "links": [],  # populated only after unified_document_link table is approved + applied
    }


# ---------------------------------------------------------------------------
# Dependency — SupabaseRestClient instance per request
# ---------------------------------------------------------------------------

def _get_rest_client() -> SupabaseRestClient:
    return SupabaseRestClient()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
def list_document_catalog(
    page: int = Query(default=1, ge=1, description="1-based page number"),
    per_page: int = Query(default=50, ge=1, le=200, description="Items per page (max 200)"),
    q: str = Query(default="", description="Full-text search on title / doc_name"),
    sector: str = Query(default="", description="Filter by sector (SAAS records only)"),
    source_system: str = Query(
        default="ALL",
        pattern="^(ALL|SAAS|REFERENCE_CMS)$",
        description="Source system filter",
    ),
):
    """
    Returns a unified paginated catalog from document_forms (SAAS) and
    reference_form_public_view (REFERENCE_CMS).

    - No DB writes.
    - per_page is silently capped at 200.
    - sector filter applies to SAAS records only; REF records are always included.
    - links[] is always empty at this phase (unified_document_link table not applied).
    """
    try:
        client = _get_rest_client()
        result = get_unified_catalog(
            client,
            page=page,
            per_page=per_page,
            q=q,
            sector=sector,
            source_system=source_system,
        )
    except RuntimeError as exc:
        log.error("[document-catalog] client init error: %s", exc)
        raise HTTPException(status_code=503, detail="Catalog service unavailable")
    except Exception as exc:
        log.error("[document-catalog] list error: %s", exc)
        raise HTTPException(status_code=503, detail="Catalog service unavailable")

    return {
        "total": result.total,
        "page": result.page,
        "per_page": result.per_page,
        "items": [_item_to_dict(item) for item in result.items],
    }


@router.get("/{key:path}")
def get_catalog_item(key: str):
    """
    Returns a single catalog item by provisional key.

    key: DOC:<doc_id> for SAAS records, REF:<canonical_slug> for REFERENCE_CMS records.
    Returns 404 if not found or key format is invalid.
    links[] is always empty at this phase.
    """
    if not (key.startswith("DOC:") or key.startswith("REF:")):
        raise HTTPException(
            status_code=404,
            detail=f"Unknown key format: {key!r}. Expected DOC:<code> or REF:<slug>.",
        )

    try:
        client = _get_rest_client()
        item = get_document_detail(client, key)
    except RuntimeError as exc:
        log.error("[document-catalog] client init error: %s", exc)
        raise HTTPException(status_code=503, detail="Catalog service unavailable")
    except Exception as exc:
        log.error("[document-catalog] detail error key=%r: %s", key, exc)
        raise HTTPException(status_code=503, detail="Catalog service unavailable")

    if item is None:
        raise HTTPException(status_code=404, detail=f"Document not found: {key}")

    return _item_to_dict(item)
