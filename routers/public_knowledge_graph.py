"""Public OBJ-GRAPH read model.

GET /public/knowledge-graph/context
GET /public/knowledge-graph/items/{content_type}/{content_id}/contexts
GET /public/knowledge-graph/items/{content_type}/{content_id}/related

Production adapters are lazy. Import does not query the database.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/public/knowledge-graph", tags=["Public knowledge graph"])

_override_store = None
_override_hydrator = None
_production = None


def configure_graph_read(*, store, hydrator) -> None:
    global _override_store, _override_hydrator, _production
    _override_store = store
    _override_hydrator = hydrator
    _production = None


def reset_graph_read() -> None:
    configure_graph_read(store=None, hydrator=None)


def _lazy_production():
    from db.supabase_client import get_supabase
    from services.knowledge_graph_hydrate import ProductionKnowledgeHydrator
    from services.knowledge_graph_store import SupabaseGraphStore

    sb = get_supabase()
    return SupabaseGraphStore(sb), ProductionKnowledgeHydrator(sb)


def _require_backend():
    global _production
    if _override_store is not None and _override_hydrator is not None:
        return _override_store, _override_hydrator
    try:
        if _production is None:
            _production = _lazy_production()
        return _production
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="GRAPH_READ_UNAVAILABLE") from None


def _safe_read(fn):
    try:
        return fn()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="GRAPH_READ_UNAVAILABLE") from None


@router.get("/context")
def public_graph_context(
    relation_type: str = Query(...),
    relation_key: str = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    content_type: str | None = Query(None),
):
    from services.knowledge_graph_svc import read_context

    store, hydrator = _require_backend()
    return _safe_read(
        lambda: read_context(
            store,
            hydrator,
            relation_type=relation_type,
            relation_key=relation_key,
            page=page,
            page_size=page_size,
            content_type=content_type,
        )
    )


@router.get("/items/{content_type}/{content_id}/contexts")
def public_graph_item_contexts(content_type: str, content_id: str):
    from services.knowledge_graph_svc import read_item_contexts

    store, hydrator = _require_backend()
    return _safe_read(
        lambda: read_item_contexts(store, hydrator, content_type=content_type, content_id=content_id)
    )


@router.get("/items/{content_type}/{content_id}/related")
def public_graph_related(content_type: str, content_id: str):
    from services.knowledge_graph_svc import read_related

    store, hydrator = _require_backend()
    return _safe_read(
        lambda: read_related(store, hydrator, content_type=content_type, content_id=content_id)
    )
