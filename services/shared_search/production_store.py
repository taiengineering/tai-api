"""SupabaseSearchStore — production implementation of SearchStore.

WO-TAI-SHARED-SEARCH-F2. One Supabase-backed adapter for the ENTIRE
Foundation. Domain adapters never talk to Supabase's
`search_documents` / `search_rebuild_runs` / `search_rebuild_documents`
directly; they always go through this store via the Common Writer
and the Common Indexer.

Production apply of the F1 migration is a separate Owner-approved
step. This module has zero effect on production until the migration
has been applied — every method uses only tables the migration
declares. No new tables, no ad-hoc SQL.
"""
from __future__ import annotations

from typing import Any, Iterator, Optional

from services.shared_search.source_reader import SupabaseClient
from services.shared_search.store import SearchStore
from services.shared_search.writer import WriterRejected


CURRENT_TABLE = "search_documents"
RUNS_TABLE = "search_rebuild_runs"
STAGING_TABLE = "search_rebuild_documents"
PROMOTE_RPC = "promote_search_rebuild"


class SupabaseSearchStore(SearchStore):
    """SearchStore backed by Supabase.

    Constructed with any object that exposes `.table(name)` and
    `.rpc(name, params)` — same shape as `supabase-py`'s `Client`.
    Tests inject a fake with matching behavior.
    """

    def __init__(self, client: SupabaseClient):
        self.client = client

    # -- current projection --
    def upsert_current(self, doc: dict) -> None:
        # Upsert on the canonical identity key. The unique index on
        # (object_type, canonical_id) enforces the identity contract.
        payload = _wire_to_row(doc)
        (self.client.table(CURRENT_TABLE)
             .upsert(payload, on_conflict="object_type,canonical_id")
             .execute())

    def get_current(self, object_type: str, canonical_id: str) -> Optional[dict]:
        r = (self.client.table(CURRENT_TABLE)
                 .select("*")
                 .eq("object_type", object_type)
                 .eq("canonical_id", canonical_id)
                 .limit(1)
                 .execute())
        rows = list(getattr(r, "data", None) or [])
        return dict(rows[0]) if rows else None

    def delete_current(self, object_type: str, canonical_id: str) -> bool:
        r = (self.client.table(CURRENT_TABLE)
                 .delete()
                 .eq("object_type", object_type)
                 .eq("canonical_id", canonical_id)
                 .execute())
        rows = list(getattr(r, "data", None) or [])
        return len(rows) > 0

    def iter_current(self, object_type: Optional[str] = None) -> Iterator[dict]:
        from services.shared_search.source_reader import paginate_supabase
        def _filters(q):
            if object_type is not None:
                q = q.eq("object_type", object_type)
            return q
        yield from paginate_supabase(
            self.client,
            table=CURRENT_TABLE,
            select="*",
            apply_filters=_filters,
            order_column="object_type",  # stable ordering
        )

    def count_current(self, object_type: Optional[str] = None) -> int:
        q = self.client.table(CURRENT_TABLE).select("id", count="exact")
        if object_type is not None:
            q = q.eq("object_type", object_type)
        r = q.limit(1).execute()
        return int(getattr(r, "count", 0) or 0)

    # -- rebuild runs --
    def insert_run(self, run: dict) -> None:
        (self.client.table(RUNS_TABLE)
             .insert(dict(run), returning="minimal")
             .execute())

    def get_run(self, run_id: str) -> Optional[dict]:
        r = (self.client.table(RUNS_TABLE)
                 .select("*")
                 .eq("run_id", run_id)
                 .limit(1)
                 .execute())
        rows = list(getattr(r, "data", None) or [])
        return dict(rows[0]) if rows else None

    def update_run(self, run_id: str, **fields) -> None:
        (self.client.table(RUNS_TABLE)
             .update(dict(fields))
             .eq("run_id", run_id)
             .execute())

    # -- rebuild staging --
    def stage_document(self, run_id: str, doc: dict) -> None:
        row = {
            "run_id": run_id,
            "object_type": doc["object_type"],
            "canonical_id": doc["canonical_id"],
            "content_hash": doc["content_hash"],
            "document_json": doc["document_json"],
        }
        (self.client.table(STAGING_TABLE)
             .upsert(row, on_conflict="run_id,object_type,canonical_id")
             .execute())

    def count_staging(self, run_id: str) -> int:
        r = (self.client.table(STAGING_TABLE)
                 .select("run_id", count="exact")
                 .eq("run_id", run_id)
                 .limit(1)
                 .execute())
        return int(getattr(r, "count", 0) or 0)

    def iter_staging(self, run_id: str) -> Iterator[dict]:
        from services.shared_search.source_reader import paginate_supabase
        yield from paginate_supabase(
            self.client,
            table=STAGING_TABLE,
            select="run_id,object_type,canonical_id,content_hash,document_json",
            apply_filters=lambda q: q.eq("run_id", run_id),
            order_column="object_type",
        )

    # -- atomic promotion --
    def replace_current_from_staging(self, run_id: str) -> int:
        """Server-side atomic promotion via the SQL RPC.

        `promote_search_rebuild` (F1 migration):
          - refuses runs not in VALIDATED
          - DELETE + INSERT under one transaction
          - filters staging to `publication_status = 'PUBLISHED'`
        """
        r = self.client.rpc(PROMOTE_RPC, {"p_run_id": run_id}).execute()
        rows = list(getattr(r, "data", None) or [])
        if not rows:
            raise WriterRejected(
                f"promote_search_rebuild returned no rows for run_id={run_id}")
        return int(rows[0].get("promoted_count", 0))


def _wire_to_row(doc: dict) -> dict:
    """Translate the writer wire dict into a search_documents row.

    The wire dict already carries the exact column names the migration
    declares — this pass is mainly to keep provenance timestamps and
    fresh `indexed_at` correctly typed.
    """
    row = {
        "object_type": doc["object_type"],
        "canonical_id": doc["canonical_id"],
        "source_id": doc["source_id"],
        "source_key": doc.get("source_key"),
        "title": doc["title"],
        "summary": doc.get("summary"),
        "search_text": doc["search_text"],
        "aliases": doc.get("aliases") or [],
        "keywords": doc.get("keywords") or [],
        "subjects": doc.get("subjects") or [],
        "context": doc.get("context") or [],
        "public_url": doc.get("public_url"),
        "saas_url": doc.get("saas_url"),
        "publication_status": doc["publication_status"],
        "visibility_scopes": doc.get("visibility_scopes") or [],
        "source_updated_at": doc.get("source_updated_at"),
        "content_hash": doc["content_hash"],
    }
    if "indexed_at" in doc:
        row["indexed_at"] = doc["indexed_at"]
    return row
