"""
routers/document_catalog.py
WO-TAI-DOC-UNIFIED-CATALOG-IMPLEMENT-001 — Phase 1 (CORR-001 + CORR-002 + CORR-003)

GET /api/document-catalog        — unified document list (SAAS + REFERENCE_CMS)
GET /api/document-catalog/{key}  — single document detail by provisional key

Auth: get_current_user (Supabase JWT validation) + role_code == "001" (platform admin only).
  - Missing token / no Authorization header → 401 (raised by get_current_user)
  - Invalid token → 401 (raised by get_current_user after Supabase rejection)
  - Valid user, role_code != "001" → 403 (raised by _require_admin)
  - Inactive/suspended account → 403 (raised by get_current_user)
  - Admin role_code 001 → 200
  Note: role_code "002" is 안전관리자 (safety manager), not platform admin.
        All other admin endpoints use "001" only; this endpoint matches that pattern.
Status: PROPOSED — not deployed
Source/DB mutations: 0
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from routers.auth import get_current_user
from services.catalog_aggregator import (
    CatalogItem,
    SupabaseRestClient,
    get_approved_links_for_catalog,
    get_document_detail,
    get_unified_catalog,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/document-catalog", tags=["Document catalog"])

_ADMIN_ROLES = frozenset({"001"})

_VALID_CHANNEL_NAMES = frozenset({
    "REFERENCE_DOWNLOAD", "OFFICIAL_ORIGINAL", "WEB_EDIT", "SAAS_EXPORT", "SAAS_AUTO_FILL"
})
_VALID_CHANNEL_STATES = frozenset({"READY", "BLOCKED", "UNVERIFIED", "NOT_APPLICABLE"})


def _normalise_channel(channel: str) -> str:
    """
    Accepts 'CHANNEL_NAME' (→ implicit READY) or 'CHANNEL_NAME:STATE'.
    Returns normalised 'CHANNEL_NAME:STATE'.
    Raises HTTPException 422 on unknown channel name or state.
    """
    if not channel:
        return channel
    if ":" in channel:
        ch_name, ch_state = channel.split(":", 1)
    else:
        ch_name, ch_state = channel, "READY"
    if ch_name not in _VALID_CHANNEL_NAMES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"유효하지 않은 채널명: {ch_name!r}. "
                f"허용값: {sorted(_VALID_CHANNEL_NAMES)}"
            ),
        )
    if ch_state not in _VALID_CHANNEL_STATES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"유효하지 않은 채널 상태: {ch_state!r}. "
                f"허용값: {sorted(_VALID_CHANNEL_STATES)}"
            ),
        )
    return f"{ch_name}:{ch_state}"


def _require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role_code") not in _ADMIN_ROLES:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "DOCUMENT_CATALOG_FORBIDDEN",
                "message": "관리자만 접근 가능합니다.",
            },
        )
    return current_user


# ---------------------------------------------------------------------------
# Serialisation helpers (dataclasses → plain dicts; no raw storage paths)
# ---------------------------------------------------------------------------

def _channel_to_dict(ch: Any) -> dict[str, Any]:
    d: dict[str, Any] = {"state": ch.state, "reason": ch.reason}
    if ch.action_url is not None:
        d["action_url"] = ch.action_url
    return d


def _item_to_dict(
    item: CatalogItem,
    links: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
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
        # links: APPROVED SAME_DOCUMENT_VERIFIED only (populated in detail endpoint)
        "links": links if links is not None else [],
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
    _admin: dict = Depends(_require_admin),
    page: int = Query(default=1, ge=1, description="1-based page number"),
    per_page: int = Query(default=50, ge=1, description="Items per page (silently capped at 200)"),
    q: str = Query(default="", description="Full-text search on title / doc_name"),
    sector: str = Query(default="", description="Filter by sector (SAAS records only)"),
    category: str = Query(default="", description="Filter by category (SAAS records only)"),
    status: str = Query(
        default="",
        description="Filter by schema_status: CANDIDATE | APPROVED_FOR_RUNTIME_USE (SAAS only)",
    ),
    channel: str = Query(
        default="",
        description=(
            "Filter by channel. "
            "Name only (e.g. WEB_EDIT) → READY. "
            "Name:State (e.g. WEB_EDIT:BLOCKED) → explicit state."
        ),
    ),
    source_system: str = Query(
        default="ALL",
        pattern="^(ALL|SAAS|REFERENCE_CMS)$",
        description="Source system filter",
    ),
):
    """
    Returns a unified paginated catalog from document_forms (SAAS) and
    reference_form_public_view (REFERENCE_CMS).

    Auth: Bearer JWT required → 401 if missing/invalid; 403 if not role 001.
    No DB writes. per_page silently capped at 200 (no error above 200).
    sector/category/status filters apply to SAAS records only.
    channel: 'WEB_EDIT' → READY; 'WEB_EDIT:BLOCKED' → explicit; unknown name/state → 422.
    WEB_EDIT and SAAS_EXPORT are fail-closed in catalog context (factory scope unverified).
    links[] is always empty at this phase (unified_document_link table not applied).
    """
    channel_normalised = _normalise_channel(channel)
    try:
        client = _get_rest_client()
        result = get_unified_catalog(
            client,
            page=page,
            per_page=per_page,
            q=q,
            sector=sector,
            category=category,
            status=status,
            channel_filter=channel_normalised,
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
def get_catalog_item(
    key: str,
    _admin: dict = Depends(_require_admin),
):
    """
    Returns a single catalog item by provisional key.

    key: DOC:<doc_id> for SAAS records, REF:<canonical_slug> for REFERENCE_CMS records.
    Auth: Bearer JWT required → 401 if missing/invalid; 403 if not role 001.
    Returns 404 if not found or key format invalid.
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

    links: list[dict[str, Any]] = []
    if item.db_uuid:
        try:
            links = get_approved_links_for_catalog(client, item.db_uuid, item.source_system)
        except Exception as exc:
            log.error("[document-catalog] link fetch error key=%r: %s", key, exc)
            raise HTTPException(status_code=503, detail="Catalog link service unavailable")

    return _item_to_dict(item, links=links)
