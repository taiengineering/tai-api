"""Public OBJ-GRAPH read model.

GET /public/knowledge-graph/context
GET /public/knowledge-graph/items/{content_type}/{content_id}/contexts
GET /public/knowledge-graph/items/{content_type}/{content_id}/related

tai-api is the read owner. Browser does not query Graph tables directly.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from services.knowledge_graph_svc import (
    MemoryHydrator,
    MemoryGraphStore,
    read_context,
    read_item_contexts,
    read_related,
)

router = APIRouter(prefix="/public/knowledge-graph", tags=["Public knowledge graph"])

_store: MemoryGraphStore | None = None
_hydrator: MemoryHydrator | None = None


def configure_graph_read(*, store, hydrator) -> None:
    global _store, _hydrator
    _store = store
    _hydrator = hydrator


def reset_graph_read() -> None:
    configure_graph_read(store=None, hydrator=None)


def _require_backend():
    if _store is None or _hydrator is None:
        raise HTTPException(status_code=503, detail="GRAPH_READ_UNAVAILABLE")
    return _store, _hydrator


@router.get("/context")
def public_graph_context(
    relation_type: str = Query(...),
    relation_key: str = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    content_type: str | None = Query(None),
):
    store, hydrator = _require_backend()
    return read_context(
        store,
        hydrator,
        relation_type=relation_type,
        relation_key=relation_key,
        page=page,
        page_size=page_size,
        content_type=content_type,
    )


@router.get("/items/{content_type}/{content_id}/contexts")
def public_graph_item_contexts(content_type: str, content_id: str):
    store, hydrator = _require_backend()
    return read_item_contexts(store, hydrator, content_type=content_type, content_id=content_id)


@router.get("/items/{content_type}/{content_id}/related")
def public_graph_related(content_type: str, content_id: str):
    store, hydrator = _require_backend()
    return read_related(store, hydrator, content_type=content_type, content_id=content_id)
