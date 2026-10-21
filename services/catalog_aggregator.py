"""
services/catalog_aggregator.py
WO-TAI-DOC-UNIFIED-CATALOG-IMPLEMENT-001 — Phase 1

Read-only unified document catalog aggregation.
- No new DB tables required
- No DB writes
- Sources: document_forms (SAAS) + reference_form_public_view (REFERENCE_CMS)

Production schema contract:
  document_forms:             id, doc_id, doc_name, sector, category,
                              doc_format, file_url, is_active
  runtime_form_schema:        catalog_document_id, status
  reference_form_public_view: id, canonical_slug, title, qa_pass_files (JSONB)
                              — view enforces PUBLISHED + approved content hash
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

@dataclass
class ChannelState:
    state: str          # READY | BLOCKED | UNVERIFIED | NOT_APPLICABLE
    reason: str
    action_url: Optional[str] = None


@dataclass
class CatalogChannels:
    REFERENCE_DOWNLOAD: ChannelState
    OFFICIAL_ORIGINAL: ChannelState
    WEB_EDIT: ChannelState
    SAAS_EXPORT: ChannelState
    SAAS_AUTO_FILL: ChannelState


@dataclass
class CatalogItem:
    provisional_key: str
    source_system: str      # SAAS | REFERENCE_CMS
    source_code: str
    title: str
    normalized_title: str
    sector: str
    category: str
    official_flag: bool
    format_flag: Optional[str]
    channels: CatalogChannels
    db_uuid: Optional[str] = None   # internal DB id — excluded from API response


@dataclass
class CatalogPage:
    total: int
    page: int
    per_page: int
    items: list[CatalogItem] = field(default_factory=list)


# ---------------------------------------------------------------------------
# REST client (thin urllib wrapper — injected for testability)
# ---------------------------------------------------------------------------

class SupabaseRestClient:
    """Thin Supabase REST wrapper. Reads env vars; never hardcodes credentials."""

    def __init__(self) -> None:
        self._url: str = os.environ["SUPABASE_URL"]
        key = (
            os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            or os.environ.get("SUPABASE_SERVICE_KEY")
        )
        if not key:
            raise RuntimeError(
                "service_role 키가 설정되지 않았습니다. "
                "SUPABASE_SERVICE_ROLE_KEY 또는 SUPABASE_SERVICE_KEY를 설정하세요."
            )
        self._key: str = key

    def select(
        self,
        table: str,
        *,
        columns: str = "*",
        filters: Optional[dict[str, str]] = None,
        order: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        import urllib.request
        import urllib.parse
        import json

        params: dict[str, str] = {"select": columns}
        if filters:
            params.update(filters)
        if order:
            params["order"] = order
        if limit is not None:
            params["limit"] = str(limit)
        if offset is not None:
            params["offset"] = str(offset)

        url = f"{self._url}/rest/v1/{table}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(
            url,
            headers={
                "apikey": self._key,
                "Authorization": f"Bearer {self._key}",
                "Accept": "application/json",
                "Range-Unit": "items",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())


# ---------------------------------------------------------------------------
# Channel state computation (server-side only — UI must not override)
# ---------------------------------------------------------------------------

def compute_channel_state(
    record_type: str,
    schema_status: Optional[str],
    file_count: int,
    file_url: Optional[str],
    rights_state: Optional[str],
    *,
    factory_scope_verified: bool = False,
    active_instance_exists: bool = False,
) -> CatalogChannels:
    """
    record_type: 'SAAS' | 'REFERENCE_CMS'
    schema_status: runtime_form_schema.status for SAAS records
    file_count: len(qa_pass_files) for REF records
    file_url: document_forms.file_url for SAAS records
    rights_state: document_forms.doc_format for SAAS records
    factory_scope_verified: True only when caller confirms factory-level access (default False → BLOCKED)
    active_instance_exists: True only when caller confirms an active document instance exists
    """
    if record_type == "REFERENCE_CMS":
        ref_download = (
            ChannelState(
                state="READY",
                reason="PUBLISHED + QA_PASS files available",
                action_url=None,  # caller sets action_url with slug
            )
            if file_count >= 1
            else ChannelState(
                state="BLOCKED",
                reason="No QA_PASS files available for this reference form",
            )
        )
        return CatalogChannels(
            REFERENCE_DOWNLOAD=ref_download,
            OFFICIAL_ORIGINAL=ChannelState(
                state="NOT_APPLICABLE",
                reason="Reference form — no external law.go.kr link",
            ),
            WEB_EDIT=ChannelState(
                state="NOT_APPLICABLE",
                reason="Reference form — no SAAS schema binding",
            ),
            SAAS_EXPORT=ChannelState(
                state="NOT_APPLICABLE",
                reason="Reference form — no SAAS schema binding",
            ),
            SAAS_AUTO_FILL=ChannelState(
                state="NOT_APPLICABLE",
                reason="Reference form — no SAAS schema binding",
            ),
        )

    # SAAS record
    ref_download = ChannelState(
        state="NOT_APPLICABLE",
        reason="SAAS catalog entry — no linked reference form approved",
    )

    _is_law_link = bool(file_url and "flDownload.do" in file_url)
    _is_any_url = bool(file_url)
    if not _is_any_url:
        official_original = ChannelState(
            state="BLOCKED",
            reason="No file_url available for this SAAS entry",
        )
    elif _is_law_link:
        official_original = ChannelState(
            state="UNVERIFIED",
            reason="file_url present but binary not fetched; version/currency not confirmed",
        )
    else:
        official_original = ChannelState(
            state="UNVERIFIED",
            reason="file_url present but binary fetch and version confirmation required",
        )

    # WEB_EDIT: requires APPROVED schema AND confirmed factory scope.
    # Catalog context cannot confirm factory scope → fail-closed (BLOCKED) unless explicitly verified.
    if schema_status == "APPROVED_FOR_RUNTIME_USE" and factory_scope_verified:
        web_edit = ChannelState(
            state="READY",
            reason="Schema approved for runtime use; factory scope verified",
        )
    elif schema_status == "APPROVED_FOR_RUNTIME_USE":
        web_edit = ChannelState(
            state="BLOCKED",
            reason="Schema approved but factory scope not verified in catalog context",
        )
    else:
        web_edit = ChannelState(
            state="BLOCKED",
            reason="schema status=CANDIDATE; requires APPROVED_FOR_RUNTIME_USE + factory scope",
        )

    # SAAS_EXPORT: requires WEB_EDIT=READY AND active document instance.
    # Catalog context cannot confirm active instance → fail-closed unless explicitly verified.
    if web_edit.state == "READY" and active_instance_exists:
        saas_export = ChannelState(
            state="READY",
            reason="Web edit ready; active document instance exists",
        )
    else:
        saas_export = ChannelState(
            state="BLOCKED",
            reason="web edit not ready or active document instance not confirmed",
        )

    auto_fill = ChannelState(
        state="BLOCKED",
        reason="effective_safe=0; no approved source binding",
    )

    return CatalogChannels(
        REFERENCE_DOWNLOAD=ref_download,
        OFFICIAL_ORIGINAL=official_original,
        WEB_EDIT=web_edit,
        SAAS_EXPORT=saas_export,
        SAAS_AUTO_FILL=auto_fill,
    )


# ---------------------------------------------------------------------------
# Item builders
# ---------------------------------------------------------------------------

def _build_saas_item(row: dict[str, Any]) -> CatalogItem:
    source_code: str = row.get("doc_id", "")
    provisional_key = f"DOC:{source_code}"
    schema_status: Optional[str] = row.get("schema_status")
    file_url: Optional[str] = row.get("file_url")
    rights_state: Optional[str] = row.get("doc_format")
    channels = compute_channel_state(
        record_type="SAAS",
        schema_status=schema_status,
        file_count=0,
        file_url=file_url,
        rights_state=rights_state,
    )
    return CatalogItem(
        provisional_key=provisional_key,
        source_system="SAAS",
        source_code=source_code,
        title=row.get("doc_name", ""),
        normalized_title=row.get("doc_name", ""),
        sector=row.get("sector", ""),
        category=row.get("category", ""),
        official_flag=False,
        format_flag=rights_state,
        channels=channels,
        db_uuid=row.get("id"),
    )


def _build_ref_item(row: dict[str, Any]) -> CatalogItem:
    slug: str = row.get("canonical_slug", "")
    provisional_key = f"REF:{slug}"
    qa_pass_files = row.get("qa_pass_files") or []
    fc = len(qa_pass_files) if isinstance(qa_pass_files, list) else 0
    channels = compute_channel_state(
        record_type="REFERENCE_CMS",
        schema_status=None,
        file_count=fc,
        file_url=None,
        rights_state=None,
    )
    if channels.REFERENCE_DOWNLOAD.state == "READY":
        channels.REFERENCE_DOWNLOAD.action_url = f"/reference-forms/{slug}"
    return CatalogItem(
        provisional_key=provisional_key,
        source_system="REFERENCE_CMS",
        source_code=slug,
        title=row.get("title", ""),
        db_uuid=row.get("id"),
        normalized_title=row.get("title", ""),
        sector="",
        category="",
        official_flag=False,
        format_flag=None,
        channels=channels,
    )


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _matches_channel_filter(item: CatalogItem, channel_filter: str) -> bool:
    """
    channel_filter: 'CHANNEL_NAME:STATE' (e.g. 'WEB_EDIT:READY') or
                    'CHANNEL_NAME' alone (implicit READY).
    Empty string → no filter (all pass).
    Unknown channel name or state → no match (returns False).
    Router validates input before calling; this function is the post-fetch gate.
    """
    if not channel_filter:
        return True
    if ":" in channel_filter:
        ch_name, ch_state = channel_filter.split(":", 1)
    else:
        ch_name, ch_state = channel_filter, "READY"
    ch = getattr(item.channels, ch_name.strip(), None)
    if ch is None:
        return False
    return ch.state == ch_state.strip()


def get_unified_catalog(
    client: SupabaseRestClient,
    page: int = 1,
    per_page: int = 50,
    q: str = "",
    sector: str = "",
    category: str = "",
    status: str = "",
    channel_filter: str = "",
    source_system: str = "ALL",
) -> CatalogPage:
    """
    Paginated unified catalog from existing tables. No DB writes.
    source_system: 'ALL' | 'SAAS' | 'REFERENCE_CMS'
    category: filter by document_forms.category (SAAS records only)
    status: filter by schema_status ('CANDIDATE' | 'APPROVED_FOR_RUNTIME_USE') — SAAS only
    channel_filter: 'CHANNEL_NAME:STATE', e.g. 'WEB_EDIT:READY' — post-fetch filter
    per_page silently capped at 200.
    REF records: sector/category/status filter not applied (not in view).
    """
    if per_page > 200:
        per_page = 200
    offset = (page - 1) * per_page

    saas_items: list[CatalogItem] = []
    ref_items: list[CatalogItem] = []

    if source_system in ("ALL", "SAAS"):
        saas_filters: dict[str, str] = {"is_active": "eq.true"}
        if sector:
            saas_filters["sector"] = f"eq.{sector}"
        if category:
            saas_filters["category"] = f"eq.{category}"
        if q:
            saas_filters["doc_name"] = f"ilike.*{q}*"
        saas_rows = client.select(
            "document_forms",
            columns="id,doc_id,doc_name,sector,category,doc_format,file_url",
            filters=saas_filters,
        )
        if saas_rows:
            saas_ids = [r["id"] for r in saas_rows]
            schema_map: dict[str, str] = {}
            try:
                schema_rows = client.select(
                    "runtime_form_schema",
                    columns="catalog_document_id,status",
                    filters={"catalog_document_id": f"in.({','.join(saas_ids)})"},
                )
                for sr in schema_rows:
                    schema_map[sr["catalog_document_id"]] = sr["status"]
            except Exception:
                pass
            for row in saas_rows:
                row["schema_status"] = schema_map.get(row["id"], "CANDIDATE")
                # status filter (schema_status) — applied after lookup
                if status and row["schema_status"] != status:
                    continue
                saas_items.append(_build_saas_item(row))

    if source_system in ("ALL", "REFERENCE_CMS"):
        ref_filters: dict[str, str] = {}
        if q:
            ref_filters["title"] = f"ilike.*{q}*"
        ref_rows = client.select(
            "reference_form_public_view",
            columns="id,canonical_slug,title,qa_pass_files",
            filters=ref_filters,
        )
        for row in ref_rows:
            ref_items.append(_build_ref_item(row))

    all_items = saas_items + ref_items

    # channel_filter is a post-fetch filter applied to computed channel states
    if channel_filter:
        all_items = [item for item in all_items if _matches_channel_filter(item, channel_filter)]

    total = len(all_items)
    page_items = all_items[offset: offset + per_page]

    return CatalogPage(total=total, page=page, per_page=per_page, items=page_items)


_APPROVED_RELATION_TYPES = "in.(SAME_DOCUMENT_VERIFIED,RELATED_FORM)"


def get_approved_links_for_catalog(
    client: SupabaseRestClient,
    db_uuid: str,
    source_system: str,
) -> list[dict[str, Any]]:
    """Return APPROVED links (SAME_DOCUMENT_VERIFIED + RELATED_FORM) for catalog display.

    review_state must be APPROVED. PROPOSED, UNDER_REVIEW, REJECTED, RETIRED are excluded.
    Audit history and internal evidence are not exposed.

    Returns [] for a successful 0-result query.
    Raises on DB access failure so the caller can return 503.
    """
    if source_system == "SAAS":
        link_rows = client.select(
            "unified_document_link",
            columns="id,reference_form_id,relation_type,review_state",
            filters={
                "saas_catalog_id": f"eq.{db_uuid}",
                "review_state": "eq.APPROVED",
                "relation_type": _APPROVED_RELATION_TYPES,
            },
        )
        if not link_rows:
            return []
        ref_uuids = [r["reference_form_id"] for r in link_rows]
        ref_rows = client.select(
            "reference_form_public_view",
            columns="id,canonical_slug,title",
            filters={"id": f"in.({','.join(ref_uuids)})"},
        )
        ref_by_id = {r["id"]: r for r in ref_rows}
        result = []
        for lk in link_rows:
            ref = ref_by_id.get(lk["reference_form_id"])
            if ref:
                result.append({
                    "relation_type": lk["relation_type"],
                    "linked_key": f"REF:{ref['canonical_slug']}",
                    "linked_title": ref["title"],
                })
        return result
    else:
        # REFERENCE_CMS: look up by reference_form_id
        link_rows = client.select(
            "unified_document_link",
            columns="id,saas_catalog_id,relation_type,review_state",
            filters={
                "reference_form_id": f"eq.{db_uuid}",
                "review_state": "eq.APPROVED",
                "relation_type": _APPROVED_RELATION_TYPES,
            },
        )
        if not link_rows:
            return []
        saas_uuids = [r["saas_catalog_id"] for r in link_rows]
        saas_rows = client.select(
            "document_forms",
            columns="id,doc_id,doc_name",
            filters={"id": f"in.({','.join(saas_uuids)})"},
        )
        saas_by_id = {r["id"]: r for r in saas_rows}
        result = []
        for lk in link_rows:
            saas = saas_by_id.get(lk["saas_catalog_id"])
            if saas:
                result.append({
                    "relation_type": lk["relation_type"],
                    "linked_key": f"DOC:{saas['doc_id']}",
                    "linked_title": saas["doc_name"],
                })
        return result


def get_document_detail(
    client: SupabaseRestClient,
    provisional_key: str,
) -> Optional[CatalogItem]:
    """
    Resolves DOC:<code> or REF:<slug> to a single CatalogItem.
    Returns None if not found.
    """
    if provisional_key.startswith("DOC:"):
        code = provisional_key[4:]
        rows = client.select(
            "document_forms",
            columns="id,doc_id,doc_name,sector,category,doc_format,file_url",
            filters={"doc_id": f"eq.{code}", "is_active": "eq.true"},
        )
        if not rows:
            return None
        row = rows[0]
        schema_status = "CANDIDATE"
        try:
            schema_rows = client.select(
                "runtime_form_schema",
                columns="status",
                filters={"catalog_document_id": f"eq.{row['id']}"},
            )
            if schema_rows:
                schema_status = schema_rows[0]["status"]
        except Exception:
            pass
        row["schema_status"] = schema_status
        return _build_saas_item(row)

    if provisional_key.startswith("REF:"):
        slug = provisional_key[4:]
        rows = client.select(
            "reference_form_public_view",
            columns="id,canonical_slug,title,qa_pass_files",
            filters={"canonical_slug": f"eq.{slug}"},
        )
        if not rows:
            return None
        return _build_ref_item(rows[0])

    return None
