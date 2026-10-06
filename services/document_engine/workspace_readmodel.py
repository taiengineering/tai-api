"""OBJ02-B1 (CORR-01/02): Document workspace read-model.

list_document_workspace() returns the catalog × schema binding state
for every document in document_forms, enriched with availability.

CORR-01: Uses actual document_forms columns (no document_family).
CORR-02: Availability filter applied BEFORE pagination so that
         total and page items are consistent across pages.
"""
from __future__ import annotations
from db.supabase_client import get_supabase

_APPROVED = "APPROVED_FOR_RUNTIME_USE"
_CANDIDATE = "CANDIDATE"
_KNOWN_DOCUMENT_FORMS_COLUMNS = frozenset({
    "id", "doc_id", "doc_name", "sector", "category",
    "law_ref", "obligation", "tai_grade", "tai_difficulty",
    "priority", "has_legal_form", "tai_auto", "tai_method",
    "doc_format", "doc_owner", "is_external_writer", "is_active",
})
_SELECT_COLUMNS = "id,doc_id,doc_name,sector,category,is_active,priority"


def list_document_workspace(
    page: int = 1,
    page_size: int = 50,
    availability: str = None,
    sector: str = None,
    category: str = None,
) -> dict:
    """Return paginated catalog × schema binding workspace.

    Filter order (CORR-02): sector/category → schema resolve → availability →
    filtered total → pagination. Never paginate before availability is known.

    Each row:
      id, doc_id, doc_name, sector, category, is_active, priority
      availability: READY_FOR_EDIT | PREPARING | NO_SCHEMA
      schema_id:    UUID | None
      schema_status: str | None
      candidate_count: int

    Returns:
        {
          "items": [...],
          "total": <filtered total, not raw catalog count>,
          "page": <int>,
          "page_size": <int>,
        }
    """
    sb = get_supabase()
    page_size = min(page_size, 200)

    # STEP 1: Fetch all matching catalog rows (no DB pagination yet)
    q = sb.table("document_forms").select(_SELECT_COLUMNS)
    if sector:
        q = q.eq("sector", sector)
    if category:
        q = q.eq("category", category)
    q = q.order("sector").order("doc_name")
    catalog_res = q.execute()
    catalog_rows = catalog_res.data or []

    if not catalog_rows:
        return {"items": [], "total": 0, "page": page, "page_size": page_size}

    # STEP 2: Batch resolve schemas for all catalog IDs
    catalog_ids = [r["id"] for r in catalog_rows]
    schema_res = (
        sb.table("runtime_form_schema")
        .select("id,status,form_name,catalog_document_id")
        .in_("catalog_document_id", catalog_ids)
        .execute()
    )
    schema_rows = schema_res.data or []

    approved_map: dict[str, dict] = {}
    candidate_count_map: dict[str, int] = {}
    for s in schema_rows:
        cid = s["catalog_document_id"]
        if s["status"] == _APPROVED:
            approved_map[cid] = s
        elif s["status"] == _CANDIDATE:
            candidate_count_map[cid] = candidate_count_map.get(cid, 0) + 1

    # STEP 3: Compute availability + apply availability filter
    all_items = []
    for cat in catalog_rows:
        cid = cat["id"]
        approved = approved_map.get(cid)
        ccount = candidate_count_map.get(cid, 0)

        if approved:
            avail = "READY_FOR_EDIT"
        elif ccount > 0:
            avail = "PREPARING"
        else:
            avail = "NO_SCHEMA"

        if availability and avail != availability:
            continue

        all_items.append({
            **cat,
            "availability": avail,
            "schema_id": approved["id"] if approved else None,
            "schema_status": approved["status"] if approved else None,
            "candidate_count": ccount,
        })

    # STEP 4: filtered total, then paginate
    filtered_total = len(all_items)
    offset = (page - 1) * page_size
    page_items = all_items[offset: offset + page_size]

    return {
        "items": page_items,
        "total": filtered_total,
        "page": page,
        "page_size": page_size,
    }
