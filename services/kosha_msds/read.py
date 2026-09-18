"""OBJ-CHEM-06 canonical MSDS read service (internal, read-only).

Reads from the existing published-gated view
    public.kosha_msds_current
and, when needed, from
    public.kosha_msds_sections
    public.kosha_msds_chemicals   (only to pick up columns the current
                                    view does not project, e.g. last_date;
                                    always joined via the id from the
                                    current view so the publish gate is
                                    preserved)

No new schema, no new engine, no new RPC. No DB mutation. No public
router in this WO. This is the internal service layer that a future
router (CHEM-07) will call.

The service accepts any object that quacks like MsdsReadStore. Two
implementations live below:

- MemoryMsdsReadStore   -- in-memory replica for tests
- SupabaseMsdsReadStore -- production SELECT-only client

The service functions themselves never open a client; the caller
provides one. Non-current chemicals are never returned; sections for a
non-current chemical are never returned.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from services.kosha_msds.contract import (
    ALLOWED_PUBLICATION_SCOPES,
    ALLOWED_SECTIONS,
    PUBLICATION_SCOPE_FULL,
    PUBLICATION_SCOPE_SEO_PREVIEW,
    SECTION_MAX,
    SECTION_MIN,
)

CURRENT_VIEW = "kosha_msds_current"
PREVIEW_VIEW = "kosha_msds_seo_preview_current"
SECTIONS_TABLE = "kosha_msds_sections"
CHEMICALS_TABLE = "kosha_msds_chemicals"


def _view_for_scope(scope: str) -> str:
    """Return the SQL view name for the given publication scope.

    FULL         → kosha_msds_current           (PUBLISHED_FULL only)
    SEO_PREVIEW  → kosha_msds_seo_preview_current (PUBLISHED_SEO_PREVIEW only)

    Unknown scope raises ValueError — callers must validate the scope
    before reaching store methods.
    """
    if scope == PUBLICATION_SCOPE_FULL:
        return CURRENT_VIEW
    if scope == PUBLICATION_SCOPE_SEO_PREVIEW:
        return PREVIEW_VIEW
    raise ValueError(f"unknown publication scope: {scope!r}")


def _validate_scope(scope: Optional[str]) -> str:
    if scope is None:
        return PUBLICATION_SCOPE_FULL
    if scope not in ALLOWED_PUBLICATION_SCOPES:
        raise ValueError(f"scope must be one of {sorted(ALLOWED_PUBLICATION_SCOPES)}, got {scope!r}")
    return scope

DEFAULT_LIMIT = 20
MAX_LIMIT = 100

# Columns the current view projects (see supabase/migrations/20260914_kosha_msds_catalog.sql:169-202).
CURRENT_VIEW_SELECT = (
    "id,content_id,source_id,source_key,chem_id,identity_status,"
    "chemical_name_ko,chemical_name_en,cas_no,ke_no,en_no,un_no,"
    "source_content_hash,source_dataset_url,snapshot_id"
)
# Extra columns fetched from kosha_msds_chemicals for a chemical that
# IS already in the current view. This preserves the publish gate.
CHEMICALS_EXTRA_SELECT = "id,last_date"

SECTIONS_SELECT = (
    "chemical_id,section_no,payload_json,section_hash,result_code,"
    "result_message,fetched_at"
)


class SectionNoOutOfRange(ValueError):
    """Raised on section_no outside 1..16."""


def _validate_section_no(section_no: int) -> int:
    if not isinstance(section_no, int) or isinstance(section_no, bool):
        raise SectionNoOutOfRange(f"section_no must be int, got {type(section_no).__name__}")
    if section_no not in ALLOWED_SECTIONS:
        raise SectionNoOutOfRange(
            f"section_no must be {SECTION_MIN}..{SECTION_MAX}, got {section_no}"
        )
    return section_no


def _clamp_pagination(limit: int, offset: int) -> tuple[int, int]:
    lim = int(limit) if limit is not None else DEFAULT_LIMIT
    off = int(offset) if offset is not None else 0
    if lim <= 0:
        lim = DEFAULT_LIMIT
    if lim > MAX_LIMIT:
        lim = MAX_LIMIT
    if off < 0:
        off = 0
    return lim, off


def _current_row_to_contract(row: dict, *, last_date: Optional[str]) -> dict:
    return {
        "chem_id": row.get("chem_id"),
        "content_id": row.get("content_id"),
        "identity_status": row.get("identity_status"),
        "chemical_name_ko": row.get("chemical_name_ko"),
        "chemical_name_en": row.get("chemical_name_en"),
        "cas_no": row.get("cas_no"),
        "ke_no": row.get("ke_no"),
        "en_no": row.get("en_no"),
        "un_no": row.get("un_no"),
        "last_date": last_date,
        "provenance": {
            "source_id": row.get("source_id"),
            "source_key": row.get("source_key"),
            "source_content_hash": row.get("source_content_hash"),
            "source_dataset_url": row.get("source_dataset_url"),
            "snapshot_id": row.get("snapshot_id"),
        },
    }


def _section_row_to_contract(row: dict) -> dict:
    return {
        "section_no": int(row.get("section_no")),
        "payload_json": row.get("payload_json"),
        "section_hash": row.get("section_hash"),
        "result_code": row.get("result_code"),
        "fetched_at": row.get("fetched_at"),
    }


# ---------------------------------------------------------------------------
# Store interface
# ---------------------------------------------------------------------------


class MemoryMsdsReadStore:
    """In-memory read-only replica for tests. SELECT-only interface.

    Callers seed:
      * `current_rows`         — FULL scope (kosha_msds_current mirror)
      * `chemicals`            — for last_date lookups (extra columns)
      * `sections`             — section payloads (shared across scopes)
      * `preview_rows`         — SEO_PREVIEW scope (kosha_msds_seo_preview_current mirror)

    Sections are shared: a section row belongs to a chemical (by chemical_id),
    not to a scope. Membership is determined by which scope's *_rows list
    contains that chemical.

    All methods take a `scope` keyword-only parameter (default FULL) so
    existing callers see identical behavior. No insert/update/delete
    methods are exposed.
    """

    def __init__(
        self,
        *,
        current_rows: Optional[Iterable[dict]] = None,
        chemicals: Optional[Iterable[dict]] = None,
        sections: Optional[Iterable[dict]] = None,
        preview_rows: Optional[Iterable[dict]] = None,
    ):
        self._current: list[dict] = [dict(r) for r in (current_rows or [])]
        self._preview: list[dict] = [dict(r) for r in (preview_rows or [])]
        self._chemicals: dict[str, dict] = {
            str(r.get("id")): dict(r) for r in (chemicals or []) if r.get("id")
        }
        self._sections: list[dict] = [dict(r) for r in (sections or [])]

    def _rows_for_scope(self, scope: str) -> list[dict]:
        return self._preview if scope == PUBLICATION_SCOPE_SEO_PREVIEW else self._current

    def get_current_by_chem_id(self, chem_id: str, *, scope: str = PUBLICATION_SCOPE_FULL) -> Optional[dict]:
        for row in self._rows_for_scope(scope):
            if row.get("chem_id") == chem_id:
                return dict(row)
        return None

    def chemical_extra(self, chemical_id: str) -> dict:
        return dict(self._chemicals.get(str(chemical_id), {}))

    def list_current(self, *, limit: int, offset: int, scope: str = PUBLICATION_SCOPE_FULL) -> tuple[list[dict], int]:
        rows = sorted(self._rows_for_scope(scope), key=lambda r: r.get("chem_id") or "")
        return [dict(r) for r in rows[offset : offset + limit]], len(rows)

    def search_current(
        self,
        *,
        chem_id: Optional[str] = None,
        cas_no: Optional[str] = None,
        ke_no: Optional[str] = None,
        en_no: Optional[str] = None,
        un_no: Optional[str] = None,
        name_ko: Optional[str] = None,
        name_en: Optional[str] = None,
        limit: int,
        offset: int,
        scope: str = PUBLICATION_SCOPE_FULL,
    ) -> tuple[list[dict], int]:
        matches = []
        needle_ko = (name_ko or "").strip().lower()
        needle_en = (name_en or "").strip().lower()
        for row in self._rows_for_scope(scope):
            if chem_id and row.get("chem_id") != chem_id:
                continue
            if cas_no and row.get("cas_no") != cas_no:
                continue
            if ke_no and row.get("ke_no") != ke_no:
                continue
            if en_no and row.get("en_no") != en_no:
                continue
            if un_no and row.get("un_no") != un_no:
                continue
            if needle_ko and needle_ko not in (row.get("chemical_name_ko") or "").lower():
                continue
            if needle_en and needle_en not in (row.get("chemical_name_en") or "").lower():
                continue
            matches.append(dict(row))
        matches.sort(key=lambda r: r.get("chem_id") or "")
        total = len(matches)
        return matches[offset : offset + limit], total

    def sections_for_chemical(self, chemical_id: str) -> list[dict]:
        rows = [
            dict(s) for s in self._sections if str(s.get("chemical_id")) == str(chemical_id)
        ]
        rows.sort(key=lambda s: int(s.get("section_no") or 0))
        return rows

    def section_for_chemical(self, chemical_id: str, section_no: int) -> Optional[dict]:
        for s in self._sections:
            if str(s.get("chemical_id")) == str(chemical_id) and int(s.get("section_no") or 0) == int(section_no):
                return dict(s)
        return None


class SupabaseMsdsReadStore:
    """Supabase SELECT-only read store. No insert/update/delete methods.

    A single Supabase client is used for every read. Every table
    reference goes through the current view (kosha_msds_current) for
    membership, so the publish gate cannot be bypassed by accident.
    """

    def __init__(self, sb=None):
        if sb is None:
            from db.supabase_client import get_supabase
            sb = get_supabase()
        self.sb = sb

    def get_current_by_chem_id(self, chem_id: str, *, scope: str = PUBLICATION_SCOPE_FULL) -> Optional[dict]:
        r = (
            self.sb.table(_view_for_scope(scope))
            .select(CURRENT_VIEW_SELECT)
            .eq("chem_id", chem_id)
            .limit(1)
            .execute()
        )
        rows = r.data or []
        return dict(rows[0]) if rows else None

    def chemical_extra(self, chemical_id: str) -> dict:
        r = (
            self.sb.table(CHEMICALS_TABLE)
            .select(CHEMICALS_EXTRA_SELECT)
            .eq("id", chemical_id)
            .limit(1)
            .execute()
        )
        rows = r.data or []
        return dict(rows[0]) if rows else {}

    def list_current(self, *, limit: int, offset: int, scope: str = PUBLICATION_SCOPE_FULL) -> tuple[list[dict], int]:
        r = (
            self.sb.table(_view_for_scope(scope))
            .select(CURRENT_VIEW_SELECT, count="exact")
            .order("chem_id")
            .range(offset, offset + limit - 1)
            .execute()
        )
        return list(r.data or []), int(r.count or 0)

    def search_current(
        self,
        *,
        chem_id: Optional[str] = None,
        cas_no: Optional[str] = None,
        ke_no: Optional[str] = None,
        en_no: Optional[str] = None,
        un_no: Optional[str] = None,
        name_ko: Optional[str] = None,
        name_en: Optional[str] = None,
        limit: int,
        offset: int,
        scope: str = PUBLICATION_SCOPE_FULL,
    ) -> tuple[list[dict], int]:
        q = self.sb.table(_view_for_scope(scope)).select(CURRENT_VIEW_SELECT, count="exact")
        if chem_id:
            q = q.eq("chem_id", chem_id)
        if cas_no:
            q = q.eq("cas_no", cas_no)
        if ke_no:
            q = q.eq("ke_no", ke_no)
        if en_no:
            q = q.eq("en_no", en_no)
        if un_no:
            q = q.eq("un_no", un_no)
        if name_ko:
            q = q.ilike("chemical_name_ko", f"%{name_ko}%")
        if name_en:
            q = q.ilike("chemical_name_en", f"%{name_en}%")
        r = q.order("chem_id").range(offset, offset + limit - 1).execute()
        return list(r.data or []), int(r.count or 0)

    def sections_for_chemical(self, chemical_id: str) -> list[dict]:
        r = (
            self.sb.table(SECTIONS_TABLE)
            .select(SECTIONS_SELECT)
            .eq("chemical_id", chemical_id)
            .order("section_no")
            .execute()
        )
        return list(r.data or [])

    def section_for_chemical(self, chemical_id: str, section_no: int) -> Optional[dict]:
        r = (
            self.sb.table(SECTIONS_TABLE)
            .select(SECTIONS_SELECT)
            .eq("chemical_id", chemical_id)
            .eq("section_no", section_no)
            .limit(1)
            .execute()
        )
        rows = r.data or []
        return dict(rows[0]) if rows else None


# ---------------------------------------------------------------------------
# Service operations
# ---------------------------------------------------------------------------


def get_by_chem_id(
    chem_id: str,
    *,
    store,
    include_sections: bool = True,
    scope: Optional[str] = None,
) -> Optional[dict]:
    """Return the current chemical + its sections, or None if not current.

    Non-current chemicals are never returned. Section payloads are only
    included when include_sections=True; the summary shape is otherwise
    identical. `scope` selects the publication view:
      - PUBLICATION_SCOPE_FULL (default)   → kosha_msds_current
      - PUBLICATION_SCOPE_SEO_PREVIEW      → kosha_msds_seo_preview_current

    Sections are shared across scopes; membership is enforced by the
    view lookup before section reads.
    """
    scope = _validate_scope(scope)
    if not isinstance(chem_id, str) or not chem_id:
        return None
    row = store.get_current_by_chem_id(chem_id, scope=scope)
    if row is None:
        return None
    extra = store.chemical_extra(row.get("id")) if row.get("id") else {}
    payload = _current_row_to_contract(row, last_date=extra.get("last_date"))
    if include_sections:
        sections = store.sections_for_chemical(row["id"])
        payload["sections"] = [_section_row_to_contract(s) for s in sections]
    return payload


def get_section(
    chem_id: str,
    section_no: int,
    *,
    store,
    scope: Optional[str] = None,
) -> Optional[dict]:
    """Return a single section for a CURRENT chemical, or None.

    Section number is validated first (1..16). Membership in the scoped
    current view is checked BEFORE reading the section — a chemical that
    is not in the scoped view will always return None for section reads,
    regardless of whether kosha_msds_sections contains a row.
    """
    scope = _validate_scope(scope)
    _validate_section_no(section_no)
    if not isinstance(chem_id, str) or not chem_id:
        return None
    row = store.get_current_by_chem_id(chem_id, scope=scope)
    if row is None:
        return None
    section = store.section_for_chemical(row["id"], section_no)
    if section is None:
        return None
    return _section_row_to_contract(section)


def list_current(
    *,
    store,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    scope: Optional[str] = None,
) -> dict:
    """Deterministic list of current chemicals ordered by chem_id ASC.

    Returns {"items": [...], "total": int, "limit": int, "offset": int}.
    Section payloads are NOT included in listings; use get_by_chem_id
    for the section-level payload. `scope` selects the publication view.
    """
    scope = _validate_scope(scope)
    lim, off = _clamp_pagination(limit, offset)
    rows, total = store.list_current(limit=lim, offset=off, scope=scope)
    return {
        "items": [
            _current_row_to_contract(row, last_date=None) for row in rows
        ],
        "total": int(total),
        "limit": lim,
        "offset": off,
    }


def search(
    *,
    store,
    chem_id: Optional[str] = None,
    cas_no: Optional[str] = None,
    ke_no: Optional[str] = None,
    en_no: Optional[str] = None,
    un_no: Optional[str] = None,
    name_ko: Optional[str] = None,
    name_en: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    scope: Optional[str] = None,
) -> dict:
    """Simple filter search over the scoped current view.

    Priority (implicit, in that exact-match filters narrow before name):
      1. exact chem_id
      2. exact CAS / KE / EN / UN
      3. name partial match (chemical_name_ko / chemical_name_en, ilike %..%)

    Does not implement ranking. If two search parameters are given they
    are AND-ed. Returns the same envelope shape as list_current().
    `scope` selects the publication view.
    """
    scope = _validate_scope(scope)
    lim, off = _clamp_pagination(limit, offset)
    rows, total = store.search_current(
        chem_id=chem_id, cas_no=cas_no, ke_no=ke_no, en_no=en_no, un_no=un_no,
        name_ko=name_ko, name_en=name_en, limit=lim, offset=off, scope=scope,
    )
    return {
        "items": [
            _current_row_to_contract(row, last_date=None) for row in rows
        ],
        "total": int(total),
        "limit": lim,
        "offset": off,
    }
