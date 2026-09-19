"""Common SearchDocument writer + in-memory store.

WO-TAI-SHARED-SEARCH-F1. All Domain adapters (F2) upsert through
`Writer.upsert_current()` — there is no Domain-specific write path.

Contract source:
- docs/search/TAI_SHARED_SEARCH_DOCUMENT_CONTRACT_v1.md §10 (adapter/writer)
- §11 (reindex + tombstone)
- Constitution §10 (fail-closed, fail-safe)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Iterator, Optional

from services.shared_search.contract import (
    PUBLICATION_STATUS_HOLD,
    PUBLICATION_STATUS_PUBLISHED,
    PUBLICATION_STATUS_REMOVED,
    SearchContractError,
)
from services.shared_search.document import SearchDocument, normalize_document
from services.shared_search.hash_utils import content_hash, _document_as_dict
from services.shared_search.store import SearchStore
from services.time import Clock, SYSTEM_CLOCK, now_kst


class WriterRejected(SearchContractError):
    """Raised when the writer refuses a SearchDocument."""


# ---------------------------------------------------------------------------
# Public canonical preparation helper (§5 — WO-TAI-SHARED-SEARCH-F3-G1)
# ---------------------------------------------------------------------------

def prepare_search_document(payload: dict) -> tuple["SearchDocument", dict]:
    """Normalize, validate, and hash a raw domain adapter payload.

    This is the SINGLE authority for canonical SearchDocument preparation.
    Both Writer._prepare() (Supabase/Memory path) and the OpenSearch
    rebuild bulk path MUST go through this function — no duplicate
    normalize + hash logic elsewhere.

    Args:
        payload: Raw dict from a Domain adapter (iter_documents output).

    Returns:
        (SearchDocument, wire_dict) where wire_dict is ready for storage.

    Raises:
        SearchContractError: if the payload fails contract validation.
    """
    doc = normalize_document(payload)
    doc.content_hash = content_hash(doc)
    wire = _document_as_dict(doc)
    return doc, wire


# ---------------------------------------------------------------------------
# In-memory store (fixture / test / SEARCH-03 handoff surface)
# ---------------------------------------------------------------------------


@dataclass
class MemoryStore:
    """Mirror of the SQL tables in
    supabase/migrations/20260919_shared_search_foundation.sql.

    Not tuned for scale — used by F1 tests + as the boundary a
    future SupabaseStore will implement identically.
    """
    _current: dict[tuple[str, str], dict] = field(default_factory=dict)
    _runs: dict[str, dict] = field(default_factory=dict)
    _staging: dict[str, dict[tuple[str, str], dict]] = field(default_factory=dict)

    # -- current projection --
    def upsert_current(self, doc: dict) -> None:
        key = (doc["object_type"], doc["canonical_id"])
        self._current[key] = dict(doc)

    def get_current(self, object_type: str, canonical_id: str) -> Optional[dict]:
        row = self._current.get((object_type, canonical_id))
        return dict(row) if row is not None else None

    def delete_current(self, object_type: str, canonical_id: str) -> bool:
        return self._current.pop((object_type, canonical_id), None) is not None

    def iter_current(
        self, object_type: Optional[str] = None,
    ) -> Iterator[dict]:
        for (ot, _cid), row in self._current.items():
            if object_type is not None and ot != object_type:
                continue
            yield dict(row)

    def count_current(self, object_type: Optional[str] = None) -> int:
        return sum(1 for _ in self.iter_current(object_type=object_type))

    def replace_current_from_staging(self, run_id: str) -> int:
        """Atomic-in-memory analog of the SQL promote function.

        Semantics match `public.promote_search_rebuild(run_id)`:

        - Only staged documents with `publication_status = 'PUBLISHED'`
          enter the current projection. HOLD / REMOVED staged rows
          are filtered out (Foundation §11.4 + WO §4).
        - Build-then-swap: the new current dict is fully built in a
          local variable before it is assigned to `self._current`.
          If any exception raises during iteration the pre-swap
          current is preserved (matches SQL transaction rollback).
        """
        if run_id not in self._staging:
            raise WriterRejected(f"no staging for run_id={run_id}")
        new_current: dict[tuple[str, str], dict] = {}
        for staged in self.iter_staging(run_id):
            wire = staged.get("document_json", staged)
            if wire.get("publication_status") != PUBLICATION_STATUS_PUBLISHED:
                continue
            key = (wire["object_type"], wire["canonical_id"])
            new_current[key] = dict(wire)
        # Atomic swap — either fully replaces or the whole operation
        # raised before reaching this line and `_current` is intact.
        self._current = new_current
        return len(new_current)

    # -- rebuild runs --
    def insert_run(self, run: dict) -> None:
        self._runs[run["run_id"]] = dict(run)
        self._staging.setdefault(run["run_id"], {})

    def get_run(self, run_id: str) -> Optional[dict]:
        row = self._runs.get(run_id)
        return dict(row) if row is not None else None

    def update_run(self, run_id: str, **fields) -> None:
        row = self._runs.get(run_id)
        if row is None:
            raise WriterRejected(f"unknown run_id={run_id}")
        row.update(fields)

    # -- rebuild staging --
    def stage_document(self, run_id: str, doc: dict) -> None:
        if run_id not in self._runs:
            raise WriterRejected(f"unknown run_id={run_id}")
        key = (doc["object_type"], doc["canonical_id"])
        self._staging[run_id][key] = dict(doc)

    def count_staging(self, run_id: str) -> int:
        return len(self._staging.get(run_id) or {})

    def iter_staging(self, run_id: str) -> Iterator[dict]:
        for row in (self._staging.get(run_id) or {}).values():
            yield dict(row)


# ---------------------------------------------------------------------------
# Common Writer
# ---------------------------------------------------------------------------


class Writer:
    """Single write surface for Shared Search.

    Adapters (F2) call:
        writer.upsert_current(payload)              # OBJECT REINDEX
        writer.stage(run_id, payload)               # FULL REBUILD
        writer.tombstone(object_type, canonical_id) # explicit removal

    Every path routes through `_prepare()` which validates,
    normalizes, and computes content_hash. Unknown / forbidden keys
    are rejected before any store call.
    """

    def __init__(self, store: SearchStore, clock: Clock = SYSTEM_CLOCK):
        # store: any SearchStore Protocol implementation (MemoryStore
        # in tests / F1; SupabaseSearchStore in F2 production).
        self.store = store
        # Time contract compliance (WO §3): no direct datetime.now /
        # timezone.utc — timestamps come from the injected Clock via
        # services.time.now_kst.
        self.clock = clock

    # -- helpers --
    def _prepare(self, payload: dict) -> tuple[SearchDocument, dict]:
        """Delegate to the shared canonical prepare helper (§5 F3-G1)."""
        return prepare_search_document(payload)

    # -- current-projection APIs --
    def upsert_current(self, payload: dict) -> SearchDocument:
        doc, wire = self._prepare(payload)
        # Tombstoning path: HOLD / REMOVED must never surface as
        # discoverable. Foundation choice = physical delete from the
        # current projection (Doc Contract §11.4 tombstone option B).
        if doc.publication_status in (PUBLICATION_STATUS_HOLD,
                                      PUBLICATION_STATUS_REMOVED):
            self.store.delete_current(doc.object_type, doc.canonical_id)
            return doc
        # PUBLISHED path.
        wire["indexed_at"] = now_kst(self.clock).isoformat()
        self.store.upsert_current(wire)
        return doc

    def tombstone(self, object_type: str, canonical_id: str) -> bool:
        if not object_type or not canonical_id:
            raise WriterRejected("tombstone requires object_type + canonical_id")
        return self.store.delete_current(object_type, canonical_id)

    # -- rebuild-staging APIs --
    def stage(self, run_id: str, payload: dict) -> SearchDocument:
        run = self.store.get_run(run_id)
        if run is None:
            raise WriterRejected(f"unknown run_id={run_id}")
        if run.get("status") != "RUNNING":
            raise WriterRejected(
                f"cannot stage into run_id={run_id} in status "
                f"{run.get('status')}")
        doc, wire = self._prepare(payload)
        # A rebuild carries every SearchDocument regardless of state —
        # the promote step selects only PUBLISHED ones for the
        # current projection. But we still refuse forbidden keys /
        # invalid enums at stage time.
        self.store.stage_document(run_id, {
            "object_type": doc.object_type,
            "canonical_id": doc.canonical_id,
            "content_hash": doc.content_hash,
            "document_json": wire,
        })
        return doc
