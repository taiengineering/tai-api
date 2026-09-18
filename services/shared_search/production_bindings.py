"""Production Domain-adapter registry.

WO-TAI-SHARED-SEARCH-F2 CO §5, §35. Consumers instantiate every
Domain adapter in ONE call:

    from services.shared_search.production_bindings import (
        build_production_adapters,
    )

    adapters = build_production_adapters(supabase)
    indexer.full_rebuild(adapters)

Each Domain's fetcher is a thin closure over the shared
`paginate_supabase` helper. The registry is where the "which
Supabase view / table / filter" decision lives — Domain adapters
stay generic.

Production tables / views referenced (all verified in
supabase/migrations/*.sql or the Domain's own service module):

    kosha_guide_current
    csi_accident_current
    kosha_msds_seo_preview_current
    kosha_msds_current
    kosha_msds_snapshots         (for _snapshot_completed_at)
    kosha_safety_materials       (+ snapshot_items / details / holds)
    safe_help_content
    industrial_accident_precedents
    law_master + law_version + law_article  (LEGAL — deferred; see §32)
    risk_canonical_nodes         (RISK — empty yield until RISK-C02)

**Zero write.** Zero RPC. Zero DDL. Zero DML. Zero env change. The
registry only builds adapter objects — the caller decides when to
run `iter_documents()`.
"""
from __future__ import annotations

from typing import Any, Callable, Iterable, Iterator, Optional

from services.shared_search.adapters import (
    ChemAdapter, CsiAccidentAdapter, GuideAdapter,
    KnowledgeAdapter, LegalAdapter, PrecedentAdapter,
    RiskAdapter, SafetyMaterialAdapter,
)
from services.shared_search.source_reader import (
    SupabaseClient, paginate_supabase,
)


# ---------------------------------------------------------------------------
# Shared helpers — used by more than one Domain
# ---------------------------------------------------------------------------


def _fetch_one(
    client: SupabaseClient,
    *,
    table: str,
    select: str,
    key_column: str,
    key_value: Any,
    extra_filters: Optional[Callable[[Any], Any]] = None,
) -> Optional[dict]:
    """Single-row fetch. Common across every adapter's `fetch_by_id`
    hook so no Domain re-implements the `.eq(...).limit(1)` boilerplate."""
    q = client.table(table).select(select).eq(key_column, key_value)
    if extra_filters is not None:
        q = extra_filters(q)
    r = q.limit(1).execute()
    rows = list(getattr(r, "data", None) or [])
    return dict(rows[0]) if rows else None


def _snapshot_completed_at(
    client: SupabaseClient,
    *,
    snapshot_table: str,
    snapshot_id: Optional[str],
) -> Optional[str]:
    """Read snapshot.completed_at for a given snapshot_id. Cached
    per-call by adapter; caller memoizes if needed."""
    if not snapshot_id:
        return None
    r = (client.table(snapshot_table)
             .select("completed_at")
             .eq("id", snapshot_id)
             .limit(1)
             .execute())
    rows = list(getattr(r, "data", None) or [])
    if not rows:
        return None
    return rows[0].get("completed_at")


# ---------------------------------------------------------------------------
# Per-Domain builders
# ---------------------------------------------------------------------------


def _make_guide_adapter(client: SupabaseClient) -> GuideAdapter:
    def _iter_current() -> Iterator[dict]:
        # kosha_guide_current already joins the latest COMPLETED
        # snapshot; the view carries `snapshot_id` per row. Resolve
        # `_snapshot_completed_at` once because every row shares the
        # same snapshot_id (view predicate).
        snapshot_completed: dict[str, Optional[str]] = {}
        for row in paginate_supabase(
            client,
            table="kosha_guide_current",
            select=("id,guide_no,guide_title,category_code,category_name,"
                    "guide_url,regist_date,content_hash,snapshot_id"),
            order_column="id",
        ):
            sid = row.get("snapshot_id")
            if sid not in snapshot_completed:
                snapshot_completed[sid] = _snapshot_completed_at(
                    client, snapshot_table="kosha_guide_snapshots",
                    snapshot_id=sid)
            row["_snapshot_completed_at"] = snapshot_completed[sid]
            yield row

    def _by_id(guide_id: str) -> Optional[dict]:
        row = _fetch_one(
            client, table="kosha_guide_current",
            select=("id,guide_no,guide_title,category_code,category_name,"
                    "guide_url,regist_date,content_hash,snapshot_id"),
            key_column="id", key_value=guide_id,
        )
        if row is not None and row.get("snapshot_id"):
            row["_snapshot_completed_at"] = _snapshot_completed_at(
                client, snapshot_table="kosha_guide_snapshots",
                snapshot_id=row["snapshot_id"])
        return row

    return GuideAdapter(fetch_current=_iter_current, fetch_by_id=_by_id)


def _make_csi_adapter(client: SupabaseClient) -> CsiAccidentAdapter:
    def _iter_current() -> Iterator[dict]:
        snapshot_completed: dict[str, Optional[str]] = {}
        for row in paginate_supabase(
            client,
            table="csi_accident_current",
            select=("content_id,source_id,source_key,identity_status,"
                    "identity_reason,title,occurred_at,construction_type,"
                    "process_major,process_minor,object_major,object_minor,"
                    "work_process,accident_type_major,accident_type,"
                    "cause_major,cause_mid,cause_minor,cause_detail,"
                    "summary,snapshot_id"),
            apply_filters=lambda q: q.eq("identity_status", "READY"),
            order_column="content_id",
        ):
            sid = row.get("snapshot_id")
            if sid not in snapshot_completed:
                snapshot_completed[sid] = _snapshot_completed_at(
                    client, snapshot_table="csi_accident_snapshots",
                    snapshot_id=sid)
            row["_snapshot_completed_at"] = snapshot_completed[sid]
            yield row

    def _by_id(content_id: str) -> Optional[dict]:
        row = _fetch_one(
            client, table="csi_accident_current",
            select=("content_id,source_id,source_key,identity_status,title,"
                    "occurred_at,work_process,accident_type,accident_type_major,"
                    "process_major,process_minor,object_major,cause_major,"
                    "construction_type,summary,snapshot_id"),
            key_column="content_id", key_value=content_id,
        )
        if row is not None and row.get("snapshot_id"):
            row["_snapshot_completed_at"] = _snapshot_completed_at(
                client, snapshot_table="csi_accident_snapshots",
                snapshot_id=row["snapshot_id"])
        return row

    return CsiAccidentAdapter(
        fetch_current=_iter_current, fetch_by_content_id=_by_id)


def _make_chem_adapter(client: SupabaseClient) -> ChemAdapter:
    """CHEM binding chooses between SEO preview + FULL views based on
    which one has rows. Both views project the same columns
    (verified in the CHEM catalog migration). We prefer FULL when
    non-empty (a FULL cutover has landed); else SEO preview.
    """
    def _pick_source() -> str:
        for candidate in ("kosha_msds_current",
                          "kosha_msds_seo_preview_current"):
            r = (client.table(candidate)
                     .select("id", count="exact").limit(1).execute())
            if int(getattr(r, "count", 0) or 0) > 0:
                return candidate
        return "kosha_msds_seo_preview_current"

    def _iter_current() -> Iterator[dict]:
        table = _pick_source()
        snapshot_completed: dict[str, Optional[str]] = {}
        for row in paginate_supabase(
            client,
            table=table,
            select=("id,content_id,source_id,source_key,chem_id,"
                    "identity_status,chemical_name_ko,chemical_name_en,"
                    "cas_no,ke_no,en_no,un_no,source_content_hash,"
                    "source_dataset_url,snapshot_id"),
            order_column="id",
        ):
            sid = row.get("snapshot_id")
            if sid not in snapshot_completed:
                snapshot_completed[sid] = _snapshot_completed_at(
                    client, snapshot_table="kosha_msds_snapshots",
                    snapshot_id=sid)
            row["_snapshot_completed_at"] = snapshot_completed[sid]
            yield row

    def _by_id(chem_uuid: str) -> Optional[dict]:
        for table in ("kosha_msds_current",
                      "kosha_msds_seo_preview_current"):
            row = _fetch_one(
                client, table=table,
                select=("id,content_id,source_id,source_key,chem_id,"
                        "chemical_name_ko,chemical_name_en,cas_no,ke_no,"
                        "en_no,un_no,snapshot_id"),
                key_column="id", key_value=chem_uuid,
            )
            if row is not None:
                if row.get("snapshot_id"):
                    row["_snapshot_completed_at"] = _snapshot_completed_at(
                        client, snapshot_table="kosha_msds_snapshots",
                        snapshot_id=row["snapshot_id"])
                return row
        return None

    return ChemAdapter(fetch_current=_iter_current, fetch_by_id=_by_id)


def _make_knowledge_adapter(client: SupabaseClient) -> KnowledgeAdapter:
    def _iter_current() -> Iterator[dict]:
        yield from paginate_supabase(
            client,
            table="safe_help_content",
            select=("doc_id,slug,title,question,answer_short,body,menu_group,"
                    "status,updated_at"),
            apply_filters=lambda q: q.eq("status", "PUBLISHED"),
            order_column="doc_id",
        )

    def _by_id(doc_id: str) -> Optional[dict]:
        return _fetch_one(
            client, table="safe_help_content",
            select=("doc_id,slug,title,question,answer_short,body,menu_group,"
                    "status,updated_at"),
            key_column="doc_id", key_value=doc_id,
        )

    return KnowledgeAdapter(fetch_current=_iter_current, fetch_by_id=_by_id)


def _make_precedent_adapter(client: SupabaseClient) -> PrecedentAdapter:
    def _iter_current() -> Iterator[dict]:
        yield from paginate_supabase(
            client,
            table="industrial_accident_precedents",
            select=("id,case_number,case_name,court_name,decision_date,"
                    "sector,hazard_type,summary,source_url,prec_seq,"
                    "source,is_active,collected_at"),
            apply_filters=lambda q: q.eq("is_active", True),
            order_column="id",
        )

    def _by_id(pid: str) -> Optional[dict]:
        return _fetch_one(
            client, table="industrial_accident_precedents",
            select=("id,case_number,case_name,court_name,decision_date,"
                    "sector,hazard_type,summary,source_url,prec_seq,"
                    "source,is_active,collected_at"),
            key_column="id", key_value=pid,
        )

    return PrecedentAdapter(fetch_current=_iter_current, fetch_by_id=_by_id)


def _make_safety_material_adapter(client: SupabaseClient) -> SafetyMaterialAdapter:
    """Material assembly = catalog + latest COMPLETED snapshot
    membership + details + storage holds. All four SoTs are read
    here; the shared `paginate_supabase` still does each pass. The
    adapter itself doesn't know about the joins (Foundation §17)."""

    def _latest_snapshot_id() -> Optional[str]:
        r = (client.table("kosha_safety_material_snapshots")
                 .select("id,completed_at,status")
                 .eq("status", "COMPLETED")
                 .order("completed_at", desc=True)
                 .limit(1)
                 .execute())
        rows = list(getattr(r, "data", None) or [])
        return rows[0]["id"] if rows else None

    def _iter_current() -> Iterator[dict]:
        snap = _latest_snapshot_id()
        if snap is None:
            return
        # Membership → catalog id
        membership = list(paginate_supabase(
            client,
            table="kosha_safety_material_snapshot_items",
            select="material_id",
            apply_filters=lambda q: q.eq("snapshot_id", snap),
            order_column="material_id",
        ))
        member_ids = [m["material_id"] for m in membership if m.get("material_id")]
        if not member_ids:
            return
        snap_completed = _snapshot_completed_at(
            client, snapshot_table="kosha_safety_material_snapshots",
            snapshot_id=snap)
        # Chunked lookups keep any single query small.
        for start in range(0, len(member_ids), 500):
            batch = member_ids[start:start + 500]
            catalogs = {
                c["id"]: c for c in (client.table("kosha_safety_materials")
                    .select("id,title,url,category,industry_category,accident_type,product_type")
                    .in_("id", batch).execute().data or [])
            }
            details = {
                d["material_id"]: d for d in (client.table("kosha_safety_material_details")
                    .select("material_id,source_med_seq,source_title,source_description,"
                            "source_url,source_published_at,source_updated_at")
                    .in_("material_id", batch).execute().data or [])
            }
            # Real schema uses status ∈ {OPEN, RESOLVED} + resolved_at
            # (NOT a `resolved` boolean). Any status != RESOLVED counts
            # as an active hold; unknown/null status is fail-closed —
            # treated as an active hold — per F2 FINAL §1.
            holds = {
                h["material_id"] for h in (client.table("kosha_safety_material_storage_holds")
                    .select("material_id,status")
                    .in_("material_id", batch).execute().data or [])
                if (h.get("status") or "OPEN") != "RESOLVED"
            }
            for mid in batch:
                cat = catalogs.get(mid) or {}
                det = details.get(mid) or {}
                row = {**cat, **det,
                       "id": mid,
                       "storage_hold": mid in holds,
                       "_snapshot_completed_at": snap_completed}
                yield row

    def _by_id(material_id: str) -> Optional[dict]:
        cat = _fetch_one(
            client, table="kosha_safety_materials",
            select="id,title,url,category,industry_category,accident_type,product_type",
            key_column="id", key_value=material_id,
        )
        if cat is None:
            return None
        det = _fetch_one(
            client, table="kosha_safety_material_details",
            select=("material_id,source_med_seq,source_title,source_description,"
                    "source_url,source_published_at,source_updated_at"),
            key_column="material_id", key_value=material_id,
        ) or {}
        hold_row = _fetch_one(
            client, table="kosha_safety_material_storage_holds",
            select="material_id,status",
            key_column="material_id", key_value=material_id,
        )
        active_hold = bool(
            hold_row
            and (hold_row.get("status") or "OPEN") != "RESOLVED"
        )
        return {**cat, **det,
                "id": material_id,
                "storage_hold": active_hold,
                "_snapshot_completed_at": _snapshot_completed_at(
                    client, snapshot_table="kosha_safety_material_snapshots",
                    snapshot_id=_latest_snapshot_id())}

    return SafetyMaterialAdapter(fetch_current=_iter_current, fetch_by_id=_by_id)


def _make_legal_adapter(client: SupabaseClient) -> LegalAdapter:
    """LEGAL binds directly to law_master + law_version + law_article.

    F2 FINAL §3-§10: `law_article_current` does NOT exist in
    production; the binding assembles the current-eligible set at
    query time by:

        1. loading active law_master rows keyed by current_version_id
        2. paginating law_article filtered to those current_version_id
           values and `is_deleted_in_version = false`
        3. joining the law_name from law_master back onto each row

    canonical_id = `law_article.id` (Domain PK). WO §7 forbids
    `article_internal_key` — production has 35,412 current-eligible
    articles but only 7,642 distinct `article_internal_key` and
    33,482 distinct `law_id + article_internal_key`. Semantic
    identity continuity across law revisions is a Legal Domain
    governance decision, not something F2 invents.

    Production reality (per F2 CO §27):
      - legal_obligations has 0 rows → obligation_atom BLOCKED
      - norm_cluster BLOCKED
    """
    LAW_MASTER_SELECT = "id,law_name,is_active,current_version_id"
    # Real columns verified via information_schema on production
    # (F2 FINAL §14 read-only discovery). `published_at` /
    # `version_effective_at` do NOT exist — timestamp resolution uses
    # `enforcement_date` (per law_article + fall back to
    # law_article.updated_at).
    LAW_ARTICLE_SELECT = (
        "id,law_id,law_version_id,article_no,article_sub_no,"
        "article_title,article_text,is_deleted_in_version,"
        "enforcement_date,updated_at"
    )
    CURRENT_VERSION_CHUNK = 400   # keep any single `.in_()` small

    def _active_masters() -> tuple[dict[str, dict], list[str]]:
        masters: dict[str, dict] = {}
        current_version_ids: list[str] = []
        for m in paginate_supabase(
            client,
            table="law_master",
            select=LAW_MASTER_SELECT,
            apply_filters=lambda q: q.eq("is_active", True),
            order_column="id",
        ):
            mid = m.get("id")
            cvid = m.get("current_version_id")
            if not mid or not cvid:
                continue
            masters[mid] = m
            current_version_ids.append(cvid)
        # De-duplicate + sort for deterministic order.
        current_version_ids = sorted(set(current_version_ids))
        return masters, current_version_ids

    def _law_name_by_version(masters: dict[str, dict]) -> dict[str, str]:
        # Map current_version_id → law_name (for the join back onto
        # article rows).
        out: dict[str, str] = {}
        for m in masters.values():
            cvid = m.get("current_version_id")
            name = m.get("law_name")
            if cvid and name:
                out[cvid] = name
        return out

    def _iter_current() -> Iterator[dict]:
        masters, current_version_ids = _active_masters()
        if not current_version_ids:
            return
        name_map = _law_name_by_version(masters)

        for start in range(0, len(current_version_ids), CURRENT_VERSION_CHUNK):
            batch = current_version_ids[start:start + CURRENT_VERSION_CHUNK]
            # Chunked SELECT for law_article. `.in_()` on
            # law_version_id + `.eq("is_deleted_in_version", False)`.
            # Range-paginate WITHIN the chunk to survive large chunks.
            batch_start = 0
            while True:
                q = (client.table("law_article")
                         .select(LAW_ARTICLE_SELECT)
                         .in_("law_version_id", batch)
                         .eq("is_deleted_in_version", False)
                         .order("id")
                         .range(batch_start, batch_start + 999))
                r = q.execute()
                rows = list(getattr(r, "data", None) or [])
                if not rows:
                    break
                for row in rows:
                    cvid = row.get("law_version_id")
                    row["law_name"] = name_map.get(cvid)
                    row["record_kind"] = "law_article"
                    yield row
                if len(rows) < 1000:
                    break
                batch_start += 1000

    def _by_id(article_id: str) -> Optional[dict]:
        row = _fetch_one(
            client, table="law_article",
            select=LAW_ARTICLE_SELECT,
            key_column="id", key_value=article_id,
        )
        if row is None:
            return None
        if row.get("is_deleted_in_version") is True:
            return None
        # Look up the law_master via law_id → must be active AND its
        # current_version_id must equal this row's law_version_id.
        master = _fetch_one(
            client, table="law_master",
            select=LAW_MASTER_SELECT,
            key_column="id", key_value=row.get("law_id"),
        )
        if master is None:
            return None
        if not master.get("is_active"):
            return None
        if master.get("current_version_id") != row.get("law_version_id"):
            return None
        row["law_name"] = master.get("law_name")
        row["record_kind"] = "law_article"
        return row

    return LegalAdapter(fetch_current=_iter_current, fetch_by_id=_by_id)


def _make_risk_adapter(_client: SupabaseClient) -> RiskAdapter:
    # F2 §24: RISK yields zero until RISK-C02 opens the ACTIVE gate.
    # No fetcher wired here — the adapter's default empty iterator
    # is the correct behavior today.
    return RiskAdapter()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build_production_adapters(client: SupabaseClient) -> list:
    """Return the full set of production Domain adapters, ordered
    for a full rebuild. The Consumer does NOT build fetchers itself.

    Caller responsibilities:
      - hand in a Supabase-py client (or duck-typed equivalent)
      - decide when to run the Indexer (this function performs zero
        I/O by itself)
    """
    return [
        _make_guide_adapter(client),
        _make_safety_material_adapter(client),
        _make_csi_adapter(client),
        _make_chem_adapter(client),
        _make_knowledge_adapter(client),
        _make_precedent_adapter(client),
        _make_legal_adapter(client),
        _make_risk_adapter(client),
    ]
