"""Deterministic content_hash for a SearchDocument.

WO-TAI-SHARED-SEARCH-F1. Contract source:
docs/search/TAI_SHARED_SEARCH_DOCUMENT_CONTRACT_v1.md §5.

Only retrieval-scoped fields participate in the hash. Transient
fields (search_document_id, indexed_at, source_updated_at, provenance
keys) are excluded so a Domain-side "touch" that doesn't change
retrieval semantics does not force a reindex.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from services.shared_search.document import SearchDocument


def content_hash(doc: SearchDocument) -> str:
    """SHA-256 hex of the canonical retrieval-scoped serialization."""
    canonical = {
        "object_type": doc.object_type,
        "canonical_id": doc.canonical_id,
        "title": doc.title,
        "summary": doc.summary,
        "search_text": doc.search_text,
        # normalize_document already sorted + deduplicated these lists.
        "aliases": list(doc.aliases),
        "keywords": list(doc.keywords),
        "subjects": [dict(s) for s in doc.subjects],
        "context": [dict(c) for c in doc.context],
        "publication_status": doc.publication_status,
        "visibility_scopes": list(doc.visibility_scopes),
        "public_url": doc.public_url,
        "saas_url": doc.saas_url,
    }
    payload = json.dumps(
        canonical,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _document_as_dict(doc: SearchDocument) -> dict[str, Any]:
    """Wire shape for staging JSON. Adapters + writer share this."""
    return {
        "object_type": doc.object_type,
        "canonical_id": doc.canonical_id,
        "source_id": doc.source_id,
        "source_key": doc.source_key,
        "title": doc.title,
        "summary": doc.summary,
        "search_text": doc.search_text,
        "aliases": list(doc.aliases),
        "keywords": list(doc.keywords),
        "subjects": [dict(s) for s in doc.subjects],
        "context": [dict(c) for c in doc.context],
        "public_url": doc.public_url,
        "saas_url": doc.saas_url,
        "publication_status": doc.publication_status,
        "visibility_scopes": list(doc.visibility_scopes),
        "source_updated_at": (doc.source_updated_at.isoformat()
                              if doc.source_updated_at else None),
        "content_hash": doc.content_hash,
    }
