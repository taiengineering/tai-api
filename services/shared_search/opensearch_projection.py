"""OpenSearch incremental projection helpers.

Single-document NOOP-checked upsert + delete for the incremental
indexing pipeline (durable-outbox pattern).

Design:
  - ``upsert_document(client, index, doc_id, wire)`` receives a canonical
    wire dict that has ALREADY been through ``prepare_search_document()``.
    The wire's ``content_hash`` field is the canonical hash (single
    authority — opensearch_store._doc_to_os_body). A NOOP check reads the
    stored ``content_hash`` from OpenSearch before writing.
  - ``delete_document(client, index, doc_id)`` deletes a single document.
  - ``get_document_content_hash(client, index, doc_id)`` reads the stored
    ``content_hash`` field from an existing OpenSearch document.

REMOVED:
  - ``_compute_content_hash()`` — was wrong: it hashed the OS body, not
    the canonical wire hash. Canonical hash comes from
    ``prepare_search_document()`` which uses
    ``services.shared_search.hash_utils.content_hash``.
  - ``doc_to_os_body()`` local copy — now imported from opensearch_store
    (single authority).
  - ``skip_noop`` parameter — NOOP check is always performed.
"""
from __future__ import annotations

import logging
from typing import Iterable, Optional

from opensearchpy import NotFoundError
from opensearchpy.helpers import bulk as os_bulk

from services.shared_search.opensearch_store import doc_to_os_body

logger = logging.getLogger(__name__)


def get_document_content_hash(
    client,
    index: str,
    doc_id: str,
) -> Optional[str]:
    """Read the ``content_hash`` field of an existing OpenSearch document.

    Returns ``None`` if the document does not exist or has no ``content_hash``.
    """
    try:
        resp = client.get(index=index, id=doc_id)
        return resp.get("_source", {}).get("content_hash")
    except NotFoundError:
        return None
    except Exception as exc:
        logger.warning("get_document_content_hash failed for %s/%s: %s", index, doc_id, exc)
        return None


def upsert_document(
    client,
    index: str,
    doc_id: str,
    wire: dict,
) -> str:
    """NOOP-checked upsert of a canonical wire dict into OpenSearch.

    The ``wire`` dict MUST have already been through
    ``prepare_search_document()``.  The canonical hash is taken from
    ``wire["content_hash"]`` — never recomputed here.

    Returns one of:
      ``"NOOP"``   — stored hash matches; no write performed.
      ``"UPSERT"`` — document written (new or updated).
    """
    canonical_hash = wire.get("content_hash")

    # NOOP check: compare canonical hash against what is stored
    stored_hash = get_document_content_hash(client, index, doc_id)
    if stored_hash is not None and stored_hash == canonical_hash:
        logger.debug("NOOP %s (hash=%s)", doc_id, canonical_hash)
        return "NOOP"

    body = doc_to_os_body(wire)
    client.index(index=index, id=doc_id, body=body, refresh=False)
    logger.debug("UPSERT %s (hash=%s)", doc_id, canonical_hash)
    return "UPSERT"


def get_document_content_hashes(
    client,
    index: str,
    doc_ids: list[str],
) -> dict[str, Optional[str]]:
    """Batch-read content_hash fields via OpenSearch _mget.

    Returns a dict mapping doc_id → content_hash (None if not found or
    field absent).  Raises on transport error (fail-closed).
    """
    if not doc_ids:
        return {}
    resp = client.mget(
        body={"docs": [{"_id": d, "_source": ["content_hash"]} for d in doc_ids]},
        index=index,
    )
    result: dict[str, Optional[str]] = {}
    for item in resp.get("docs", []):
        doc_id = item.get("_id")
        if item.get("found"):
            result[doc_id] = item.get("_source", {}).get("content_hash")
        else:
            result[doc_id] = None
    return result


def bulk_upsert_documents(
    client,
    index: str,
    items: Iterable[tuple[str, dict]],
    chunk_size: int = 500,
) -> tuple[int, int]:
    """Bulk-upsert (doc_id, wire) pairs into OpenSearch.

    Returns ``(success, failed)``.  DELETE is not supported — this
    helper is PUBLISHED-UPSERT-ONLY.
    """
    actions = [
        {
            "_index": index,
            "_id": doc_id,
            "_source": doc_to_os_body(wire),
        }
        for doc_id, wire in items
    ]
    if not actions:
        return 0, 0
    success, errors = os_bulk(
        client,
        actions,
        chunk_size=chunk_size,
        raise_on_error=False,
        stats_only=True,
    )
    failed = errors if isinstance(errors, int) else len(errors or [])
    return success, failed


def delete_document(
    client,
    index: str,
    doc_id: str,
) -> str:
    """Delete a document from OpenSearch.

    Returns one of:
      ``"DELETE"``      — document was present and deleted.
      ``"DELETE_NOOP"`` — document was not present (already gone).
    """
    try:
        client.delete(index=index, id=doc_id, refresh=False)
        logger.debug("DELETE %s", doc_id)
        return "DELETE"
    except NotFoundError:
        logger.debug("DELETE_NOOP %s (not found)", doc_id)
        return "DELETE_NOOP"
    except Exception as exc:
        logger.warning("delete_document failed for %s/%s: %s", index, doc_id, exc)
        raise
