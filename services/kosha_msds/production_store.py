"""WO-CHEM-SEO-PREVIEW-EXECUTE-001 — Supabase adapters for materialize + publish.

Provides live Supabase-backed stores that implement the same read/write
contract as `services.kosha_msds.materialize_writer.MemoryMaterializeStore`
and `services.kosha_msds.publish.MemoryPublishStore`. The stores talk to
the pre-existing `kosha_msds_*` tables via `db.supabase_client.get_supabase()`.

Design invariants:
  * Never DELETE. Never TRUNCATE. Never REFERENCES/TRIGGER changes.
    (Migration 20260914 revokes DELETE from service_role; a mistaken
    call here would fail at the DB anyway, but we mirror the fence.)
  * enumeration_mode is written once at INSERT (fail-closed trigger
    fn_kosha_msds_snapshot_enumeration_immutable blocks any change).
  * publish_state transitions go through promote_to_state() only, which
    accepts PUBLISHED_FULL and PUBLISHED_SEO_PREVIEW.
  * All writes are chunked by CHEMICAL_BATCH_SIZE / SECTION_BATCH_SIZE /
    SNAPSHOT_ITEM_BATCH_SIZE to bound each REST round-trip.

The stores are only opened by the SEO preview production executor
(`tools/chem_seo_preview/execute_production.py`) and only when the
executor has explicitly asserted publication_scope=SEO_PREVIEW +
owner-approved. The prior WO-CHEM-08/WO-CHEM-10 module-level fences
(PRODUCTION_WRITE_ALLOWED, PRODUCTION_PUBLISH_ALLOWED) remain False;
the executor passes wo_scope_allows_write=True /
wo_scope_allows_publish=True kwargs at the assertion sites only.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from services.kosha_msds.contract import (
    ENUMERATION_FULL_OFFICIAL,
    PUBLICATION_SCOPE_FULL,
    PUBLICATION_SCOPE_SEO_PREVIEW,
    PUBLISH_PUBLISHED_FULL,
    PUBLISH_PUBLISHED_SEO_PREVIEW,
    SNAPSHOT_COMPLETED,
    SNAPSHOT_FAILED,
    SNAPSHOT_RUNNING,
)

CHEMICALS_TABLE = "kosha_msds_chemicals"
SECTIONS_TABLE = "kosha_msds_sections"
SNAPSHOTS_TABLE = "kosha_msds_snapshots"
SNAPSHOT_ITEMS_TABLE = "kosha_msds_snapshot_items"

CHEMICAL_SELECT = (
    "id,content_id,source_id,source_key,chem_id,identity_status,"
    "chemical_name_ko,chemical_name_en,cas_no,ke_no,en_no,un_no,"
    "last_date,source_content_hash,source_dataset_url,is_current"
)
SECTION_SELECT = "chemical_id,section_no,section_hash"
SNAPSHOT_SELECT = (
    "id,source_id,run_type,status,enumeration_mode,publish_state,"
    "expected_count,discovered_count,started_at,completed_at,"
    "source_contract_version,metrics_json"
)
SNAPSHOT_ITEM_SELECT = "snapshot_id,chemical_id,detail_status,in_snapshot,source_content_hash,identity_status"


def _chunk(seq: list, size: int) -> list[list]:
    if size <= 0:
        raise ValueError(f"chunk size must be > 0, got {size}")
    return [seq[i:i + size] for i in range(0, len(seq), size)]


def _enqueue_chem_snapshot(sb, snapshot_id: str) -> None:
    """Enqueue SYNC_OBJECT for NEW snapshot items UNION OLD snapshot items (BLOCKER 5B)."""
    import logging
    log = logging.getLogger(__name__)
    try:
        new_rows = sb.table(SNAPSHOT_ITEMS_TABLE) \
                     .select("chemical_id") \
                     .eq("snapshot_id", snapshot_id) \
                     .execute()
        new_ids = {r["chemical_id"] for r in (new_rows.data or []) if r.get("chemical_id")}

        prev_ids: set = set()
        prev_snap = (sb.table(SNAPSHOTS_TABLE)
                       .select("id").eq("status", SNAPSHOT_COMPLETED)
                       .neq("id", snapshot_id)
                       .order("completed_at", desc=True).limit(1).execute())
        if prev_snap.data:
            prev_sid = prev_snap.data[0]["id"]
            prev_rows = sb.table(SNAPSHOT_ITEMS_TABLE) \
                          .select("chemical_id") \
                          .eq("snapshot_id", prev_sid) \
                          .execute()
            prev_ids = {r["chemical_id"] for r in (prev_rows.data or []) if r.get("chemical_id")}

        for chem_id in new_ids | prev_ids:
            sb.rpc("enqueue_search_index_sync", {
                "p_domain_name":  "CHEM",
                "p_object_type":  "CHEM",
                "p_canonical_id": str(chem_id),
                "p_event_key":    f"chem_snapshot:{snapshot_id}:{chem_id}",
                "p_reason":       "snapshot_completed",
            }).execute()
    except Exception as exc:
        log.warning("enqueue_chem_snapshot failed: %s", exc)


# ---------------------------------------------------------------------------
# Materialize store — matches the interface consumed by
# services.kosha_msds.materialize_writer (see MemoryMaterializeStore).
# ---------------------------------------------------------------------------


class SupabaseMaterializeStore:
    """Live Supabase adapter for CHEM-08 writer.

    Method contract mirrors MemoryMaterializeStore. See writer.py for
    which methods it calls at which point in the pipeline. Every write
    goes through the four kosha_msds_* tables that migration 20260914
    already created.
    """

    def __init__(self, sb=None):
        if sb is None:
            from db.supabase_client import get_supabase
            sb = get_supabase()
        self.sb = sb

    # -- read side --

    def get_chemical_by_natural_key(self, source_id: str, source_key: str) -> Optional[dict]:
        r = (
            self.sb.table(CHEMICALS_TABLE)
            .select(CHEMICAL_SELECT)
            .eq("source_id", source_id)
            .eq("source_key", source_key)
            .limit(1)
            .execute()
        )
        rows = r.data or []
        return dict(rows[0]) if rows else None

    def get_section(self, chemical_id: str, section_no: int) -> Optional[dict]:
        r = (
            self.sb.table(SECTIONS_TABLE)
            .select(SECTION_SELECT)
            .eq("chemical_id", chemical_id)
            .eq("section_no", int(section_no))
            .limit(1)
            .execute()
        )
        rows = r.data or []
        return dict(rows[0]) if rows else None

    def latest_running_snapshot(self) -> Optional[dict]:
        r = (
            self.sb.table(SNAPSHOTS_TABLE)
            .select(SNAPSHOT_SELECT)
            .eq("status", SNAPSHOT_RUNNING)
            .order("started_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = r.data or []
        return dict(rows[0]) if rows else None

    def get_snapshot(self, snapshot_id: str) -> Optional[dict]:
        r = (
            self.sb.table(SNAPSHOTS_TABLE)
            .select(SNAPSHOT_SELECT)
            .eq("id", snapshot_id)
            .limit(1)
            .execute()
        )
        rows = r.data or []
        return dict(rows[0]) if rows else None

    # -- write side --

    def insert_snapshot(self, snapshot: dict) -> None:
        self.sb.table(SNAPSHOTS_TABLE).insert(dict(snapshot)).execute()

    def update_snapshot_status(self, snapshot_id: str, status: str) -> None:
        if status not in {SNAPSHOT_RUNNING, SNAPSHOT_COMPLETED, SNAPSHOT_FAILED}:
            raise ValueError(f"invalid snapshot status: {status!r}")
        patch: dict[str, Any] = {"status": status}
        if status == SNAPSHOT_COMPLETED:
            # Repo time contract: never `datetime.now()` / `timezone.utc`
            # directly (services/time is the sanctioned time source).
            from services.time import now_kst, serialize_external_utc
            patch["completed_at"] = serialize_external_utc(now_kst())
        (
            self.sb.table(SNAPSHOTS_TABLE)
            .update(patch)
            .eq("id", snapshot_id)
            .execute()
        )
        if status == SNAPSHOT_COMPLETED:
            _enqueue_chem_snapshot(self.sb, snapshot_id)

    def insert_chemicals(self, rows: list[dict]) -> None:
        if not rows:
            return
        # Chunk to bound REST round-trip size. CHEMICAL_BATCH_SIZE is
        # authoritative — see materialize_writer.CHEMICAL_BATCH_SIZE.
        from services.kosha_msds.materialize_writer import CHEMICAL_BATCH_SIZE
        for batch in _chunk(rows, CHEMICAL_BATCH_SIZE):
            self.sb.table(CHEMICALS_TABLE).insert(list(batch)).execute()

    def insert_sections(self, rows: list[dict]) -> None:
        if not rows:
            return
        from services.kosha_msds.materialize_writer import SECTION_BATCH_SIZE
        for batch in _chunk(rows, SECTION_BATCH_SIZE):
            self.sb.table(SECTIONS_TABLE).insert(list(batch)).execute()

    def insert_snapshot_items(self, rows: list[dict]) -> None:
        if not rows:
            return
        from services.kosha_msds.materialize_writer import SNAPSHOT_ITEM_BATCH_SIZE
        for batch in _chunk(rows, SNAPSHOT_ITEM_BATCH_SIZE):
            self.sb.table(SNAPSHOT_ITEMS_TABLE).insert(list(batch)).execute()

    def update_chemical(
        self,
        source_id: str,
        source_key: str,
        mutable_fields: dict,
    ) -> None:
        """Update mutable columns on an existing chemical row.

        Canonical identity (id / content_id / source_id / source_key /
        chem_id) is refused by the writer's field-mutability contract;
        we mirror the check here for defense-in-depth.
        """
        from services.kosha_msds.materialize_writer import (
            CHEMICAL_IMMUTABLE_FIELDS,
        )
        bad = set(mutable_fields.keys()) & CHEMICAL_IMMUTABLE_FIELDS
        if bad:
            raise ValueError(
                f"cannot update immutable chemical fields {sorted(bad)}"
            )
        if not mutable_fields:
            return
        (
            self.sb.table(CHEMICALS_TABLE)
            .update(dict(mutable_fields))
            .eq("source_id", source_id)
            .eq("source_key", source_key)
            .execute()
        )

    # -- bulk read side (WO-CHEM-FULL-READINESS-001 PATCH-A) --

    # Chunk size for `source_key IN (...)` chemical fetches. Keeps
    # PostgREST URL length bounded; each chunk is one REST round-trip.
    _CHEMICAL_KEY_CHUNK = 200
    # Chunk size for `chemical_id IN (...)` section fetches. The
    # section rows within a chunk are further paginated by the default
    # PostgREST page cap (1000).
    _SECTION_CHEM_CHUNK = 200
    _SECTION_PAGE = 1000

    def get_chemicals_by_natural_keys(
        self,
        pairs,
    ) -> dict[tuple[str, str], dict]:
        """Batch-read every chemical whose natural key appears in `pairs`.

        Groups by source_id, then issues one REST round-trip per chunk
        of source_keys via `.in_("source_key", chunk)`. Under FULL
        (20,568 chemicals, one source_id = KOSHA_MSDS, chunk size 200)
        this is ~103 REST round-trips vs. 20,568 point reads.
        """
        by_source: dict[str, list[str]] = {}
        for sid, skey in pairs:
            by_source.setdefault(str(sid), []).append(str(skey))
        out: dict[tuple[str, str], dict] = {}
        for sid, keys in by_source.items():
            for chunk in _chunk(sorted(set(keys)), self._CHEMICAL_KEY_CHUNK):
                r = (
                    self.sb.table(CHEMICALS_TABLE)
                    .select(CHEMICAL_SELECT)
                    .eq("source_id", sid)
                    .in_("source_key", list(chunk))
                    .execute()
                )
                for row in (r.data or []):
                    key = (sid, str(row.get("source_key")))
                    out[key] = dict(row)
        return out

    def get_sections_by_chemical_ids(
        self,
        chemical_ids,
    ) -> dict[tuple[str, int], dict]:
        """Batch-read every (chemical_id, section_no) row for the given
        chemical UUIDs. Chunked by chemical_id and paginated within each
        chunk. Under FULL (20,568 chemicals × 16 sections = 329,088
        pairs, chemical chunk size 200, page size 1000) this is
        ~103 × ⌈3,200 / 1,000⌉ ≈ 412 REST round-trips vs. 329,088
        point reads.
        """
        wanted = sorted({str(cid) for cid in chemical_ids})
        if not wanted:
            return {}
        out: dict[tuple[str, int], dict] = {}
        select = "chemical_id,section_no,payload_json,section_hash,result_code,result_message,fetched_at"
        for chunk in _chunk(wanted, self._SECTION_CHEM_CHUNK):
            offset = 0
            while True:
                r = (
                    self.sb.table(SECTIONS_TABLE)
                    .select(select)
                    .in_("chemical_id", list(chunk))
                    .order("chemical_id")
                    .order("section_no")
                    .range(offset, offset + self._SECTION_PAGE - 1)
                    .execute()
                )
                batch = list(r.data or [])
                for row in batch:
                    out[(str(row.get("chemical_id")),
                         int(row.get("section_no")))] = dict(row)
                if len(batch) < self._SECTION_PAGE:
                    break
                offset += self._SECTION_PAGE
        return out

    def update_section(
        self,
        chemical_id: str,
        section_no: int,
        mutable_fields: dict,
    ) -> None:
        """Update mutable columns on an existing section row.

        (chemical_id, section_no) is the natural key and never changes.
        """
        from services.kosha_msds.materialize_writer import (
            SECTION_IMMUTABLE_FIELDS,
        )
        bad = set(mutable_fields.keys()) & SECTION_IMMUTABLE_FIELDS
        if bad:
            raise ValueError(
                f"cannot update immutable section fields {sorted(bad)}"
            )
        if not mutable_fields:
            return
        (
            self.sb.table(SECTIONS_TABLE)
            .update(dict(mutable_fields))
            .eq("chemical_id", chemical_id)
            .eq("section_no", int(section_no))
            .execute()
        )


# ---------------------------------------------------------------------------
# Publish store — matches the interface consumed by
# services.kosha_msds.publish (see MemoryPublishStore).
# ---------------------------------------------------------------------------


class SupabasePublishStore:
    """Live Supabase adapter for CHEM-10 promoter.

    Method contract mirrors MemoryPublishStore. The single write path is
    promote_to_state(); nothing else in this class mutates rows.
    """

    def __init__(self, sb=None):
        if sb is None:
            from db.supabase_client import get_supabase
            sb = get_supabase()
        self.sb = sb

    # -- census methods (WO-CHEM-FULL-READINESS-004 PATCH-1 §A) --
    # All read-only counts. PostgREST returns the count via the
    # `Content-Range` header, exposed on the response as `.count`.

    def _count(self, table: str, *filters) -> int:
        q = self.sb.table(table).select("id", count="exact").limit(1)
        for k, v in filters:
            q = q.eq(k, v)
        r = q.execute()
        return int(getattr(r, "count", None) or 0)

    def count_chemicals(self) -> int:
        return self._count(CHEMICALS_TABLE)

    def count_sections(self) -> int:
        # Sections have no `id` column projected; use chemical_id for the
        # count key. PostgREST count is independent of the projection.
        r = (
            self.sb.table(SECTIONS_TABLE)
            .select("chemical_id", count="exact")
            .limit(1)
            .execute()
        )
        return int(getattr(r, "count", None) or 0)

    def count_snapshots(self) -> int:
        return self._count(SNAPSHOTS_TABLE)

    def count_snapshot_items(self) -> int:
        r = (
            self.sb.table(SNAPSHOT_ITEMS_TABLE)
            .select("snapshot_id", count="exact")
            .eq("in_snapshot", True)
            .limit(1)
            .execute()
        )
        return int(getattr(r, "count", None) or 0)

    def count_snapshots_by_status(self, status: str) -> int:
        return self._count(SNAPSHOTS_TABLE, ("status", status))

    def count_snapshots_by_publish_state(self, state: str) -> int:
        return self._count(SNAPSHOTS_TABLE, ("publish_state", state))

    def find_full_candidate(self) -> Optional[dict]:
        """Return one snapshot that is COMPLETED / FULL_OFFICIAL /
        NOT_PUBLISHED (i.e. ready for CHEM-10 preflight). None if
        no such snapshot exists. Used by the ops observer's FULL
        readiness collector to feed
        services.kosha_msds.cutover.is_full_ready.
        """
        from services.kosha_msds.contract import (
            ENUMERATION_FULL_OFFICIAL, PUBLISH_NOT_PUBLISHED,
            SNAPSHOT_COMPLETED,
        )
        r = (
            self.sb.table(SNAPSHOTS_TABLE)
            .select(SNAPSHOT_SELECT)
            .eq("status", SNAPSHOT_COMPLETED)
            .eq("enumeration_mode", ENUMERATION_FULL_OFFICIAL)
            .eq("publish_state", PUBLISH_NOT_PUBLISHED)
            .order("completed_at", desc=True)
            .order("started_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = r.data or []
        return dict(rows[0]) if rows else None

    def get_snapshot(self, snapshot_id: str) -> Optional[dict]:
        r = (
            self.sb.table(SNAPSHOTS_TABLE)
            .select(SNAPSHOT_SELECT)
            .eq("id", snapshot_id)
            .limit(1)
            .execute()
        )
        rows = r.data or []
        return dict(rows[0]) if rows else None

    def snapshot_items(self, snapshot_id: str) -> list[dict]:
        # Paginated fetch: the preview slice is 1,997 rows which fits in
        # a single Supabase page, but future FULL rollouts (20,568) need
        # pagination. We stay safe under either.
        page_size = 1000
        offset = 0
        acc: list[dict] = []
        while True:
            r = (
                self.sb.table(SNAPSHOT_ITEMS_TABLE)
                .select(SNAPSHOT_ITEM_SELECT)
                .eq("snapshot_id", snapshot_id)
                .eq("in_snapshot", True)
                .range(offset, offset + page_size - 1)
                .execute()
            )
            batch = list(r.data or [])
            acc.extend(batch)
            if len(batch) < page_size:
                break
            offset += page_size
        return acc

    # Supabase PostgREST default page cap. A single .execute() returns
    # at most this many rows regardless of how many match. For 1,997
    # chemicals × 16 sections we cannot stuff a whole chunk into one
    # round-trip without pagination.
    _SECTIONS_PAGE_SIZE = 1000
    # chemical_id chunk size for the .in_ filter — keeps the URL length
    # bounded but the section count per chunk can still exceed 1000.
    _CHEM_ID_CHUNK = 200

    def _iter_sections_for_chem_ids(self, chem_ids: list[str]):
        """Paginated read of (chemical_id, section_no) rows for the given
        UUIDs. Yields every row exactly once, streaming across chemical_id
        chunks AND across pages within each chunk. Complete enumeration
        is required for the publish preflight counts to match the 1,997 ×
        16 = 31,952 expectation.
        """
        for chunk in _chunk(sorted(chem_ids), self._CHEM_ID_CHUNK):
            offset = 0
            while True:
                r = (
                    self.sb.table(SECTIONS_TABLE)
                    .select("chemical_id,section_no")
                    .in_("chemical_id", chunk)
                    .order("chemical_id")
                    .order("section_no")
                    .range(offset, offset + self._SECTIONS_PAGE_SIZE - 1)
                    .execute()
                )
                batch = list(r.data or [])
                for row in batch:
                    yield row
                if len(batch) < self._SECTIONS_PAGE_SIZE:
                    break
                offset += self._SECTIONS_PAGE_SIZE

    def section_count_for_snapshot(self, snapshot_id: str) -> int:
        # DISTINCT (chemical_id, section_no) count for the chemicals in
        # this snapshot's membership. Paginated section walk so >1000
        # rows per chemical_id chunk are counted (PostgREST default cap).
        items = self.snapshot_items(snapshot_id)
        chem_ids = {str(i.get("chemical_id")) for i in items}
        if not chem_ids:
            return 0
        pairs: set[tuple[str, int]] = set()
        for row in self._iter_sections_for_chem_ids(sorted(chem_ids)):
            pairs.add((str(row.get("chemical_id")), int(row.get("section_no"))))
        return len(pairs)

    def duplicate_section_pairs_for_snapshot(self, snapshot_id: str) -> int:
        # Rely on the DB's PRIMARY KEY (chemical_id, section_no) — a
        # true duplicate is impossible at the DB level. The count is
        # therefore always 0. We still enumerate defensively (paginated,
        # same as section_count_for_snapshot) in case a future schema
        # change relaxes the PK.
        items = self.snapshot_items(snapshot_id)
        chem_ids = {str(i.get("chemical_id")) for i in items}
        if not chem_ids:
            return 0
        seen: dict[tuple[str, int], int] = {}
        for row in self._iter_sections_for_chem_ids(sorted(chem_ids)):
            key = (str(row.get("chemical_id")), int(row.get("section_no")))
            seen[key] = seen.get(key, 0) + 1
        return sum(1 for c in seen.values() if c > 1)

    def latest_published_snapshot(
        self,
        *,
        publication_scope: str = PUBLICATION_SCOPE_FULL,
    ) -> Optional[dict]:
        target_state = (
            PUBLISH_PUBLISHED_SEO_PREVIEW
            if publication_scope == PUBLICATION_SCOPE_SEO_PREVIEW
            else PUBLISH_PUBLISHED_FULL
        )
        r = (
            self.sb.table(SNAPSHOTS_TABLE)
            .select(SNAPSHOT_SELECT)
            .eq("status", SNAPSHOT_COMPLETED)
            .eq("enumeration_mode", ENUMERATION_FULL_OFFICIAL)
            .eq("publish_state", target_state)
            .order("completed_at", desc=True)
            .order("started_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = r.data or []
        return dict(rows[0]) if rows else None

    def promote_to_published_full(self, snapshot_id: str) -> None:
        """Explicit FULL promotion — not used by this WO but preserved
        so the interface matches MemoryPublishStore."""
        self.promote_to_state(snapshot_id, PUBLISH_PUBLISHED_FULL)

    def promote_to_state(self, snapshot_id: str, target_state: str) -> None:
        if target_state not in (PUBLISH_PUBLISHED_FULL, PUBLISH_PUBLISHED_SEO_PREVIEW):
            raise ValueError(
                f"target_state must be PUBLISHED_FULL or PUBLISHED_SEO_PREVIEW, "
                f"got {target_state!r}"
            )
        # publish_state is atomic-per-row; historical snapshots are not
        # demoted (WO §19). completed_at is set when the run finished; we
        # do not overwrite it on promotion.
        (
            self.sb.table(SNAPSHOTS_TABLE)
            .update({"publish_state": target_state})
            .eq("id", snapshot_id)
            .execute()
        )
