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
from typing import Optional

from opensearchpy import NotFoundError

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
