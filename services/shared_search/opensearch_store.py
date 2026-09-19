"""OpenSearchSearchStore — WO-TAI-SHARED-SEARCH-F3 §32-§38 + F3-G1 §6-§15.

Manages rebuild lifecycle against an OpenSearch cluster:
  begin_run → create_candidate_index
  → stage_documents (bulk via Bulk API)
  → validate_run (HARD: failed_bulk_items=0 AND actual==expected AND per-domain parity)
  → promote (HARD: status==VALIDATED guard, pre-flight count re-check)
  → rollback (restores alias, records metadata)

Hard-fail rules (§8-§13 F3-G1):
  - failed_bulk_items > 0 → FAILED (§8)
  - actual_count != expected_count → FAILED (§9)
  - expected_count == 0 → FAILED (§9)
  - per-domain count mismatch → FAILED (§10)
  - promote() called with status != VALIDATED → REJECTED (§12)
  - promote() with pre-flight count mismatch → REJECTED (§13)

NOTE — Duplicate detection (§7-§9 F3-G1):
  OpenSearch _id is not aggregatable; _id cardinality aggregation is
  NOT supported. Duplicate detection is NOT done here. It is done
  in the canonical preparation stage in opensearch_rebuild.py via
  a global_seen identity set BEFORE any write.

All writes go through this class. Retrieval (read) uses
opensearch_reader.OpenSearchSearchReader.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Iterable, Optional

from opensearchpy import OpenSearch
from opensearchpy.helpers import bulk as os_bulk

from services.shared_search.opensearch_client import (
    CURRENT_ALIAS,
    RUNS_INDEX,
    OpenSearchUnavailable,
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
BULK_CHUNK_SIZE    = 500
BULK_MAX_RETRIES   = 3

RUN_STATUS_RUNNING   = "RUNNING"
RUN_STATUS_VALIDATED = "VALIDATED"
RUN_STATUS_PROMOTED  = "PROMOTED"
RUN_STATUS_FAILED    = "FAILED"


class RebuildRejected(Exception):
    """Raised when a rebuild safety check prevents a dangerous operation."""


# ---------------------------------------------------------------------------
# Document _id helper (§36)
# ---------------------------------------------------------------------------

def document_id(object_type: str, canonical_id: str) -> str:
    """Deterministic OpenSearch _id from identity pair. Single authority."""
    return f"{object_type}::{canonical_id}"


# ---------------------------------------------------------------------------
# OpenSearchSearchStore
# ---------------------------------------------------------------------------

class OpenSearchSearchStore:
    """Rebuild lifecycle manager for OpenSearch.

    NOT a SearchStore (F1 Protocol) — this is an OpenSearch rebuild
    and projection store. F1 canonical preparation is done externally
    via prepare_search_document() before calling stage_documents().
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
                # expected_count is set at validation time (§7: prepared PUBLISHED count)
                "expected_count": 0,
                "indexed_count": 0,
                "failed_bulk_items": 0,
                "duplicate_count": 0,
                "failure": None,
                # Per-domain counters: {domain_name: {expected, indexed}}
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
            raise RebuildRejected(
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
        domain_name: Optional[str] = None,
        prepared_count: int = 0,
    ) -> tuple[int, int]:
        """Bulk-index canonical wire dicts into the candidate index.

        IMPORTANT: documents must already be through prepare_search_document().
        Only PUBLISHED documents are staged (§6 F3-G1).

        Args:
            run_id: Active rebuild run ID.
            documents: Iterable of canonical wire dicts (PUBLISHED only).
            domain_name: Domain label for per-domain manifest tracking (§10).
            prepared_count: Count of PUBLISHED docs attempted (§7 — set before
                bulk so expected != indexed on failure).

        Returns:
            (indexed_count, failed_count)
        """
        idx = candidate_index_name(run_id)

        def _actions():
            for doc in documents:
                otype = doc.get("object_type", "")
                cid   = doc.get("canonical_id", "")
                yield {
                    "_index": idx,
                    "_id":    document_id(otype, cid),
                    "_source": _doc_to_os_body(doc),
                }

        success, errors = os_bulk(
            self._client,
            _actions(),
            chunk_size=BULK_CHUNK_SIZE,
            max_retries=BULK_MAX_RETRIES,
            raise_on_error=False,
            stats_only=True,
        )
        failed = errors if isinstance(errors, int) else len(errors or [])

        # Hard fail §8: any bulk failure → FAILED immediately
        if failed > 0:
            reason = (
                f"Bulk failure: {failed} item(s) failed for domain={domain_name}. "
                "Promotion blocked."
            )
            self.fail_run(run_id, reason)
            logger.error(reason)
            raise RebuildRejected(reason)

        # Update run metadata
        run_doc = self._get_run(run_id)
        prev_indexed = run_doc.get("indexed_count", 0)
        manifest = run_doc.get("manifest") or {}

        if domain_name:
            manifest[domain_name] = {
                "expected": prepared_count,
                "indexed": success,
            }

        self._update_run(run_id,
                         indexed_count=prev_indexed + success,
                         failed_bulk_items=0,
                         manifest=manifest)
        return success, 0

    # --- validation (§9) ---

    def validate_run(
        self,
        run_id: str,
        *,
        expected_count: int,
        per_domain_expected: Optional[dict[str, int]] = None,
    ) -> bool:
        """Hard validation (§9 F3-G1).

        PASS conditions:
          1. failed_bulk_items == 0
          2. actual_index_count == expected_count
          3. expected_count > 0
          4. per-domain count parity (if per_domain_expected provided)

        Any failure → RUN_STATUS_FAILED + raises RebuildRejected.
        """
        idx = candidate_index_name(run_id)
        self._client.indices.refresh(index=idx)

        # Check for existing bulk failures
        run_doc = self._get_run(run_id)
        failed_items = run_doc.get("failed_bulk_items", 0)
        if failed_items > 0:
            reason = f"Validation blocked: {failed_items} bulk failures recorded."
            self.fail_run(run_id, reason)
            raise RebuildRejected(reason)

        # expected_count > 0
        if expected_count == 0:
            reason = "Validation blocked: expected_count == 0 (no PUBLISHED documents prepared)."
            self.fail_run(run_id, reason)
            raise RebuildRejected(reason)

        # actual == expected
        count_resp = self._client.count(index=idx)
        actual = count_resp.get("count", 0)
        self._update_run(run_id, expected_count=expected_count, indexed_count=actual)

        if actual != expected_count:
            reason = (
                f"Validation FAILED: actual={actual} != expected={expected_count}. "
                "Promotion blocked."
            )
            self.fail_run(run_id, reason)
            raise RebuildRejected(reason)

        # Per-domain parity (§10)
        if per_domain_expected:
            manifest = run_doc.get("manifest") or {}
            mismatches = []
            for domain, exp in per_domain_expected.items():
                actual_domain = manifest.get(domain, {}).get("indexed", 0)
                if actual_domain != exp:
                    mismatches.append(
                        f"{domain}: expected={exp} indexed={actual_domain}"
                    )
            if mismatches:
                reason = (
                    "Per-domain validation FAILED: " + "; ".join(mismatches)
                )
                self.fail_run(run_id, reason)
                raise RebuildRejected(reason)

        logger.info("Validation PASS: expected=%d, actual=%d", expected_count, actual)
        self._update_run(run_id, status=RUN_STATUS_VALIDATED)
        return True

    # --- atomic alias promotion (§12-§14) ---

    def promote(self, run_id: str) -> str:
        """Atomic alias switch with hard guards (§12-§14 F3-G1).

        Guards (raise RebuildRejected if violated):
          - run status must be VALIDATED
          - failed_bulk_items must be 0
          - indexed_count must == expected_count
          - candidate index must exist
          - pre-flight count re-check must pass

        Keeps PREVIOUS physical index alive (§38).
        """
        run_doc = self._get_run(run_id)

        # §12 — status guard
        status = run_doc.get("status")
        if status != RUN_STATUS_VALIDATED:
            raise RebuildRejected(
                f"promote() requires status=VALIDATED; got status={status!r}. "
                "Call validate_run() first."
            )

        # §12 — fail-safe counters
        if run_doc.get("failed_bulk_items", 0) > 0:
            raise RebuildRejected(
                "promote() blocked: failed_bulk_items > 0."
            )
        expected = run_doc.get("expected_count", 0)
        indexed  = run_doc.get("indexed_count", 0)
        if indexed != expected or expected == 0:
            raise RebuildRejected(
                f"promote() blocked: indexed={indexed} != expected={expected}."
            )

        # §13 — candidate existence + pre-flight count re-check
        new_idx = candidate_index_name(run_id)
        if not self._client.indices.exists(index=new_idx):
            raise RebuildRejected(
                f"promote() blocked: candidate index {new_idx!r} does not exist."
            )
        # Pre-flight count re-read
        self._client.indices.refresh(index=new_idx)
        live_count = self._client.count(index=new_idx).get("count", 0)
        if live_count != expected:
            raise RebuildRejected(
                f"promote() pre-flight count mismatch: live={live_count} != expected={expected}."
            )

        # §14 — alias target must not already be new_idx
        old_idx = self._current_physical_index()
        if old_idx == new_idx:
            raise RebuildRejected(
                f"promote() blocked: alias already points to {new_idx}."
            )

        action_body = build_alias_action(new_idx, old_idx)
        self._client.indices.update_aliases(body=action_body)
        self._update_run(run_id,
                         status=RUN_STATUS_PROMOTED,
                         previous_index=old_idx,
                         completed_at=_now_iso())
        logger.info("Promoted %s → %s (alias: %s)", old_idx, new_idx, CURRENT_ALIAS)
        return new_idx

    # --- rollback (§15) ---

    def rollback(self, run_id: str) -> None:
        """Revert alias to previous index. Records rollback metadata."""
        run_doc = self._get_run(run_id)
        prev = run_doc.get("previous_index")
        if not prev:
            raise RebuildRejected(
                f"Run {run_id} has no previous_index to roll back to."
            )
        new_idx = candidate_index_name(run_id)
        action_body = build_alias_action(prev, new_idx)
        self._client.indices.update_aliases(body=action_body)
        self._update_run(
            run_id,
            rollback_at=_now_iso(),
            rollback_target=prev,
        )
        logger.info("Rollback: alias %s → %s", CURRENT_ALIAS, prev)

    # --- helpers ---

    def _get_run(self, run_id: str) -> dict:
        r = self._client.get(index=RUNS_INDEX, id=run_id)
        return r.get("_source", {})

    def _current_physical_index(self) -> Optional[str]:
        try:
            resp = self._client.indices.get_alias(name=CURRENT_ALIAS)
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
                            "run_id":           {"type": "keyword"},
                            "status":           {"type": "keyword"},
                            "candidate_index":  {"type": "keyword"},
                            "previous_index":   {"type": "keyword"},
                            "started_at":       {"type": "date"},
                            "completed_at":     {"type": "date"},
                            "expected_domains": {"type": "keyword"},
                            "completed_domains":{"type": "keyword"},
                            "expected_count":   {"type": "integer"},
                            "indexed_count":    {"type": "integer"},
                            "failed_bulk_items":{"type": "integer"},
                            "duplicate_count":  {"type": "integer"},  # set by rebuild tool, not store
                            "failure":          {"type": "text"},
                            "rollback_at":      {"type": "date"},
                            "rollback_target":  {"type": "keyword"},
                            "manifest":         {"type": "object", "enabled": False},
                        }
                    },
                },
            )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return SYSTEM_CLOCK.now().isoformat()


def _doc_to_os_body(doc: dict) -> dict:
    """Convert a canonical wire dict to OpenSearch document body.

    The input must already be through prepare_search_document().
    Only PUBLISHED documents should reach this function (§6 F3-G1).
    """
    body = dict(doc)
    body["subjects"]          = list(doc.get("subjects") or [])
    body["context"]           = list(doc.get("context")  or [])
    body["aliases"]           = list(doc.get("aliases")  or [])
    body["keywords"]          = list(doc.get("keywords") or [])
    body["visibility_scopes"] = list(doc.get("visibility_scopes") or [])
    body["indexed_at"]        = _now_iso()
    return body
