"""SearchStore Protocol — the single write / read boundary that
every Domain adapter and the RebuildFramework go through.

WO-TAI-SHARED-SEARCH-F1 CO-C. Extracted so:

- `MemoryStore` (writer.py) implements it for tests + F1
- `SupabaseSearchStore` (production_store.py, F2) implements it for
  production
- Any future backend (a hosted search cluster, whatever) implements
  the same surface with no adapter changes.

**Every Domain adapter and the Common Indexer MUST talk to a
SearchStore. Direct writes against `search_documents` /
`search_rebuild_runs` / `search_rebuild_documents` from adapter
code are forbidden by convention and by the F2 audit test.**
"""
from __future__ import annotations

from typing import Iterator, Optional, Protocol, runtime_checkable


@runtime_checkable
class SearchStore(Protocol):
    """Uniform read/write surface for the Shared Search Foundation.

    Semantic contract (§Doc Contract §11 + §Foundation.md §3):

    - `upsert_current` / `get_current` / `delete_current` /
      `iter_current` / `count_current` — the current serving projection
    - `insert_run` / `get_run` / `update_run` — rebuild lifecycle
      state persistence
    - `stage_document` / `count_staging` / `iter_staging` — rebuild
      staging surface
    - `replace_current_from_staging(run_id) -> int` — atomic
      promotion (server-side in production; in-memory swap in tests)

    All method names + shapes match `services.shared_search.writer.MemoryStore`.
    A structural Protocol is enough — no ABC registration required.
    """

    # -- current projection --
    def upsert_current(self, doc: dict) -> None: ...
    def get_current(self, object_type: str, canonical_id: str) -> Optional[dict]: ...
    def delete_current(self, object_type: str, canonical_id: str) -> bool: ...
    def iter_current(self, object_type: Optional[str] = None) -> Iterator[dict]: ...
    def count_current(self, object_type: Optional[str] = None) -> int: ...

    # -- rebuild runs --
    def insert_run(self, run: dict) -> None: ...
    def get_run(self, run_id: str) -> Optional[dict]: ...
    def update_run(self, run_id: str, **fields) -> None: ...

    # -- rebuild staging --
    def stage_document(self, run_id: str, doc: dict) -> None: ...
    def count_staging(self, run_id: str) -> int: ...
    def iter_staging(self, run_id: str) -> Iterator[dict]: ...

    # -- atomic promotion --
    def replace_current_from_staging(self, run_id: str) -> int:
        """Replace `current` with the run's PUBLISHED staged rows.

        Backend contracts:
        - MemoryStore: single-critical-section swap (writer.py).
        - SupabaseSearchStore: calls `promote_search_rebuild(run_id)`
          server-side (F2). The SQL function filters to PUBLISHED only.
        """
        ...
