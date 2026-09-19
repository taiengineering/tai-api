"""OpenSearchSearchStore — WO-TAI-SHARED-SEARCH-F3 §32-§38.

Implements the F3 rebuild flow against OpenSearch:
  - candidate physical index creation (§33)
  - SearchDocument bulk indexing via Bulk API (§34)
  - refresh + count validation
  - atomic alias promotion (§37)
  - run metadata persistence in tai-shared-search-runs (§39)
  - rollback (§38): keeps CURRENT + PREVIOUS physical indexes

Follows the F1 rebuild philosophy:
  begin → stage → validate → promote

Bulk mandatory: never one HTTP call per document.
Domain-specific bulk writers are forbidden.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Iterable, Optional

from opensearchpy import OpenSearch
from opensearchpy.helpers import bulk as os_bulk

from services.shared_search.opensearch_client import (
    CURRENT_ALIAS,
    RUNS_INDEX,
    OpenSearchUnavailable,
    check_health,
    get_client,
)
from services.shared_search.opensearch_mapping import (
    INDEX_BODY,
    build_alias_action,
    candidate_index_name,
)
from services.time.tai_time import SYSTEM_CLOCK

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BULK_CHUNK_SIZE    = 500    # documents per bulk request (§34 — single authority)
BULK_MAX_RETRIES   = 3
RUN_STATUS_RUNNING   = "RUNNING"
RUN_STATUS_VALIDATED = "VALIDATED"
RUN_STATUS_PROMOTED  = "PROMOTED"
RUN_STATUS_FAILED    = "FAILED"


# ---------------------------------------------------------------------------
# Document _id helper (§36)
# ---------------------------------------------------------------------------

def document_id(object_type: str, canonical_id: str) -> str:
    """Deterministic OpenSearch _id from identity pair.
    Single authority — no per-domain _id generation.
    """
    return f"{object_type}::{canonical_id}"


# ---------------------------------------------------------------------------
# OpenSearchSearchStore
# ---------------------------------------------------------------------------

class OpenSearchSearchStore:
    """Manages rebuild lifecycle against an OpenSearch cluster.

    All writes go through this class.  Retrieval (read) uses
    opensearch_reader.OpenSearchSearchReader instead.
    """

    def __init__(self, client: Optional[OpenSearch] = None):
        self._client = client or get_client()

    # --- run metadata ---

    def begin_run(self, expected_domains: list[str]) -> str:
        """Open a new rebuild run. Returns run_id (UUID)."""
        run_id = str(uuid.uuid4())
        self._ensure_runs_index()
        self._client.index(
            index=RUNS_INDEX,
            id=run_id,
            body={
                "run_id": run_id,
                "status": RUN_STATUS_RUNNING,
                "candidate_index": candidate_index_name(run_id),
                "previous_index": None,
                "started_at": _now_iso(),
                "completed_at": None,
                "expected_domains": expected_domains,
                "completed_domains": [],
                "expected_count": 0,
                "indexed_count": 0,
                "failed_bulk_items": 0,
                "failure": None,
                "manifest": {},
            },
            refresh=True,
        )
        return run_id

    def _update_run(self, run_id: str, **fields: Any) -> None:
        self._client.update(
            index=RUNS_INDEX, id=run_id,
            body={"doc": fields},
            refresh=True,
        )

    def fail_run(self, run_id: str, reason: str) -> None:
        self._update_run(run_id,
                         status=RUN_STATUS_FAILED,
                         failure=reason,
                         completed_at=_now_iso())

    # --- candidate index ---

    def create_candidate_index(self, run_id: str) -> str:
        """Create physical candidate index. Returns index name."""
        idx = candidate_index_name(run_id)
        if self._client.indices.exists(index=idx):
            raise RuntimeError(
                f"Candidate index {idx!r} already exists. "
                "Delete it before starting a new run."
            )
        self._client.indices.create(index=idx, body=INDEX_BODY)
        logger.info("Created candidate index %s", idx)
        return idx

    # --- bulk indexing ---

    def stage_documents(
        self,
        run_id: str,
        documents: Iterable[dict],
        *,
        object_type: Optional[str] = None,
    ) -> tuple[int, int]:
        """Bulk-index SearchDocument dicts into the candidate index.

        Returns (indexed_count, failed_count).
        `documents` may be a lazy iterator — streamed in BULK_CHUNK_SIZE batches.
        """
        idx = candidate_index_name(run_id)

        def _actions():
            for doc in documents:
                otype = doc.get("object_type", object_type or "")
                cid   = doc.get("canonical_id", "")
                body  = _doc_to_os_body(doc)
                yield {
                    "_index": idx,
                    "_id":    document_id(otype, cid),
                    "_source": body,
                }

        success, errors = os_bulk(
            self._client,
            _actions(),
            chunk_size=BULK_CHUNK_SIZE,
            max_retries=BULK_MAX_RETRIES,
            raise_on_error=False,
            stats_only=False,
        )
        failed = len(errors) if isinstance(errors, list) else errors

        # Update run metadata
        run_doc = self._get_run(run_id)
        prev_indexed = run_doc.get("indexed_count", 0)
        prev_failed  = run_doc.get("failed_bulk_items", 0)
        self._update_run(run_id,
                         indexed_count=prev_indexed + success,
                         failed_bulk_items=prev_failed + failed)
        if failed:
            logger.warning("Bulk had %d failed items for run %s", failed, run_id)
        return success, failed

    # --- validation ---

    def validate_run(self, run_id: str, *, expected_count: int) -> bool:
        """Refresh + count validation. Returns True on PASS."""
        idx = candidate_index_name(run_id)
        self._client.indices.refresh(index=idx)
        count_resp = self._client.count(index=idx)
        actual = count_resp.get("count", 0)
        self._update_run(run_id, expected_count=expected_count, indexed_count=actual)
        if actual == 0:
            self.fail_run(run_id, f"validation_failed: count=0")
            return False
        logger.info("Validation: expected=%d, actual=%d", expected_count, actual)
        self._update_run(run_id, status=RUN_STATUS_VALIDATED)
        return True

    # --- atomic alias promotion (§37) ---

    def promote(self, run_id: str) -> str:
        """Atomic alias switch: new candidate → tai-shared-search-current.

        Keeps PREVIOUS index alive (§38).  Returns new physical index name.
        """
        new_idx = candidate_index_name(run_id)
        old_idx = self._current_physical_index()
        action_body = build_alias_action(new_idx, old_idx)
        self._client.indices.update_aliases(body=action_body)
        self._update_run(run_id,
                         status=RUN_STATUS_PROMOTED,
                         previous_index=old_idx,
                         completed_at=_now_iso())
        logger.info("Promoted %s → %s (alias: %s)", old_idx, new_idx, CURRENT_ALIAS)
        return new_idx

    # --- rollback (§38) ---

    def rollback(self, run_id: str) -> None:
        """Revert alias to previous index. Does NOT delete new index."""
        run_doc = self._get_run(run_id)
        prev = run_doc.get("previous_index")
        if not prev:
            raise RuntimeError(f"Run {run_id} has no previous_index to roll back to.")
        new_idx = candidate_index_name(run_id)
        action_body = build_alias_action(prev, new_idx)
        self._client.indices.update_aliases(body=action_body)
        logger.info("Rollback: alias %s → %s", CURRENT_ALIAS, prev)

    # --- helpers ---

    def _get_run(self, run_id: str) -> dict:
        r = self._client.get(index=RUNS_INDEX, id=run_id)
        return r.get("_source", {})

    def _current_physical_index(self) -> Optional[str]:
        """Return the physical index currently backing CURRENT_ALIAS, or None."""
        try:
            resp = self._client.indices.get_alias(name=CURRENT_ALIAS)
            # keys = physical index names
            for idx_name in resp:
                return idx_name
        except Exception:
            return None
        return None

    def _ensure_runs_index(self) -> None:
        if not self._client.indices.exists(index=RUNS_INDEX):
            self._client.indices.create(
                index=RUNS_INDEX,
                body={
                    "settings": {"number_of_shards": 1, "number_of_replicas": 0},
                    "mappings": {
                        "properties": {
                            "run_id":          {"type": "keyword"},
                            "status":          {"type": "keyword"},
                            "candidate_index": {"type": "keyword"},
                            "previous_index":  {"type": "keyword"},
                            "started_at":      {"type": "date"},
                            "completed_at":    {"type": "date"},
                            "expected_domains":{"type": "keyword"},
                            "completed_domains":{"type": "keyword"},
                            "expected_count":  {"type": "integer"},
                            "indexed_count":   {"type": "integer"},
                            "failed_bulk_items":{"type": "integer"},
                            "failure":         {"type": "text"},
                            "manifest":        {"type": "object", "enabled": False},
                        }
                    },
                },
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return SYSTEM_CLOCK.now().isoformat()


def _doc_to_os_body(doc: dict) -> dict:
    """Convert a SearchDocument dict to OpenSearch document body.

    subjects / context are kept as nested objects.
    source_updated_at / indexed_at are ISO strings — OpenSearch date field accepts these.
    """
    body = dict(doc)
    # Ensure subjects/context are lists (not tuples) for JSON serialisation
    body["subjects"] = list(doc.get("subjects") or [])
    body["context"]  = list(doc.get("context")  or [])
    body["aliases"]  = list(doc.get("aliases")  or [])
    body["keywords"] = list(doc.get("keywords") or [])
    body["visibility_scopes"] = list(doc.get("visibility_scopes") or [])
    body["indexed_at"] = _now_iso()
    return body
