"""Incremental projection writer — WO-TAI-SHARED-SEARCH-INCREMENTAL-001 §15.

Single module responsible for all alias-targeted document writes during
incremental sync.  The rebuild path (opensearch_store.py) manages full
index lifecycle; this module manages per-document UPSERT and DELETE
against the *current* alias.

Public surface:
    resolve_alias_target(client)               → physical index name
    get_document_content_hash(client, idx, id) → str | None
    upsert_document(client, alias, doc_id, body, content_hash) → str ("UPSERT"|"NOOP")
    delete_document(client, alias, doc_id)     → str ("DELETE"|"NOT_FOUND")

Alias safety guard (§17): every write verifies the alias resolves to
exactly one physical index.  0 or 2+ targets raises AliasNotReady.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Optional

from opensearchpy import NotFoundError, OpenSearch
from opensearchpy.exceptions import TransportError

from services.shared_search.opensearch_client import CURRENT_ALIAS, get_client
from services.time.tai_time import SYSTEM_CLOCK

logger = logging.getLogger(__name__)


class AliasNotReady(Exception):
    """Alias resolves to 0 or ≥2 physical indices — writes are unsafe."""


class ProjectionWriteError(Exception):
    """Unexpected write failure; caller should fail the outbox event."""


# ---------------------------------------------------------------------------
# Alias resolution (§17)
# ---------------------------------------------------------------------------

def resolve_alias_target(client: Optional[OpenSearch] = None) -> str:
    """Return the single physical index name the current alias points to.

    Raises AliasNotReady if the alias is absent or ambiguous.
    """
    c = client or get_client()
    try:
        raw = c.indices.get_alias(name=CURRENT_ALIAS)
    except NotFoundError:
        raise AliasNotReady(
            f"Alias '{CURRENT_ALIAS}' does not exist — full rebuild required."
        )
    except TransportError as exc:
        raise AliasNotReady(f"Alias lookup failed: {exc}") from exc

    indices = list(raw.keys())
    if len(indices) != 1:
        raise AliasNotReady(
            f"Alias '{CURRENT_ALIAS}' must point to exactly 1 index; "
            f"found {len(indices)}: {indices}"
        )
    return indices[0]


# ---------------------------------------------------------------------------
# Content hash helpers (§19)
# ---------------------------------------------------------------------------

def _compute_content_hash(body: dict) -> str:
    """Deterministic SHA-256 of the document body (excluding indexed_at)."""
    stable = {k: v for k, v in body.items() if k != "indexed_at"}
    serialized = json.dumps(stable, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode()).hexdigest()


def get_document_content_hash(
    client: OpenSearch,
    index: str,
    doc_id: str,
) -> Optional[str]:
    """Fetch existing document's content_hash field.  Returns None if absent."""
    try:
        resp = client.get(index=index, id=doc_id, _source=["content_hash"])
        return resp["_source"].get("content_hash")
    except NotFoundError:
        return None
    except TransportError as exc:
        logger.warning("content_hash fetch failed for %s: %s", doc_id, exc)
        return None


# ---------------------------------------------------------------------------
# doc_to_os_body — public re-export of opensearch_store internal (§16)
# ---------------------------------------------------------------------------

def doc_to_os_body(doc: dict) -> dict:
    """Convert canonical wire dict to OpenSearch document body.

    Mirrors opensearch_store._doc_to_os_body; use this from incremental
    paths so opensearch_store.py internals need not be made public.
    """
    body = dict(doc)
    body["subjects"]          = list(doc.get("subjects") or [])
    body["context"]           = list(doc.get("context")  or [])
    body["aliases"]           = list(doc.get("aliases")  or [])
    body["keywords"]          = list(doc.get("keywords") or [])
    body["visibility_scopes"] = list(doc.get("visibility_scopes") or [])
    body["indexed_at"]        = SYSTEM_CLOCK.now().isoformat()
    return body


# ---------------------------------------------------------------------------
# Upsert (§18-§19)
# ---------------------------------------------------------------------------

def upsert_document(
    client: OpenSearch,
    index: str,
    doc_id: str,
    body: dict,
    *,
    skip_noop: bool = True,
) -> str:
    """Index a document into *index* (physical name, not alias).

    Returns:
        "NOOP"   — content_hash unchanged; write skipped (§19)
        "UPSERT" — document written

    Raises ProjectionWriteError on transport failure.
    """
    body = doc_to_os_body(body)
    new_hash = _compute_content_hash(body)
    body["content_hash"] = new_hash

    if skip_noop:
        existing_hash = get_document_content_hash(client, index, doc_id)
        if existing_hash == new_hash:
            logger.debug("NOOP %s (hash unchanged)", doc_id)
            return "NOOP"

    try:
        client.index(index=index, id=doc_id, body=body, refresh=False)
    except TransportError as exc:
        raise ProjectionWriteError(
            f"upsert failed for {doc_id}: {exc}"
        ) from exc

    logger.debug("UPSERT %s → %s", doc_id, index)
    return "UPSERT"


# ---------------------------------------------------------------------------
# Delete (§20)
# ---------------------------------------------------------------------------

def delete_document(
    client: OpenSearch,
    index: str,
    doc_id: str,
) -> str:
    """Delete a document from *index*.

    Returns:
        "DELETE"    — document removed
        "NOT_FOUND" — document was not present (idempotent)

    Raises ProjectionWriteError on unexpected transport failure.
    """
    try:
        client.delete(index=index, id=doc_id, refresh=False)
        logger.debug("DELETE %s from %s", doc_id, index)
        return "DELETE"
    except NotFoundError:
        logger.debug("NOT_FOUND %s (delete idempotent)", doc_id)
        return "NOT_FOUND"
    except TransportError as exc:
        raise ProjectionWriteError(
            f"delete failed for {doc_id}: {exc}"
        ) from exc
