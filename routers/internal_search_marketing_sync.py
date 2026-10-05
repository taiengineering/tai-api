"""Internal: Marketing Knowledge search-index sync endpoint.

POST /internal/shared-search/marketing-knowledge/sync
  payload: {"content_id": "<uuid>"}

Enqueues a MARKETING_KNOWLEDGE / KNOWLEDGE event into search_index_outbox
so the incremental consumer picks it up within ~1 min.

Auth: X-Internal-Secret header (INTERNAL_API_SECRET env).
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel

from services.shared_search.adapters.marketing_knowledge import to_canonical

log = logging.getLogger("internal_search_marketing_sync")

router = APIRouter(
    prefix="/internal/shared-search",
    tags=["internal-search-sync"],
)


class MarketingKnowledgeSyncPayload(BaseModel):
    content_id: str


def _auth(x_internal_secret: Optional[str]) -> None:
    expected = os.environ.get("INTERNAL_API_SECRET")
    if not expected or x_internal_secret != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="invalid internal secret",
        )


@router.post("/marketing-knowledge/sync")
def sync_marketing_knowledge(
    payload: MarketingKnowledgeSyncPayload,
    x_internal_secret: Optional[str] = Header(None, alias="X-Internal-Secret"),
):
    """Enqueue a single marketing_content row for MARKETING_KNOWLEDGE index sync."""
    _auth(x_internal_secret)

    content_id = (payload.content_id or "").strip()
    if not content_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="content_id is required",
        )

    canonical_id = to_canonical(content_id)
    event_key = f"mkt_knowledge_publish:{content_id}"

    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        sb.rpc("enqueue_search_index_sync", {
            "p_domain_name":  "MARKETING_KNOWLEDGE",
            "p_object_type":  "KNOWLEDGE",
            "p_canonical_id": canonical_id,
            "p_event_key":    event_key,
            "p_reason":       "marketing_knowledge_publish",
        }).execute()
    except Exception as exc:
        log.error(
            "enqueue_search_index_sync failed for %s: %s", canonical_id, exc
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"enqueue failed: {exc}",
        )

    log.info("enqueued MARKETING_KNOWLEDGE sync for %s", canonical_id)
    return {"ok": True, "canonical_id": canonical_id, "queued": True}
