"""OBJ02-B1: Document workspace read-model.

list_document_workspace() returns the catalog × schema binding state
for every document in document_forms, enriched with availability.
"""
from __future__ import annotations
from db.supabase_client import get_supabase

_APPROVED = "APPROVED_FOR_RUNTIME_USE"
_CANDIDATE = "CANDIDATE"


def list_document_workspace(
    page: int = 1,
    page_size: int = 50,
    availability: str = None,
    document_family: str = None,
) -> dict:
    """Return paginated catalog × schema binding workspace.

    Each row is a document_forms record enriched with:
      availability: READY_FOR_EDIT | PREPARING | NO_SCHEMA
      schema_id:    UUID of the APPROVED schema, or None
      schema_status: status string of the APPROVED schema, or None
      candidate_count: number of CANDIDATE schemas bound to this catalog doc

    Args:
        page:              1-based page number
        page_size:         rows per page (max 200)
        availability:      filter by availability value (optional)
        document_family:   filter by document_forms.document_family (optional)

    Returns:
        {
          "items": [...],
          "total": <int>,
          "page": <int>,
          "page_size": <int>,
        }
    """
    sb = get_supabase()
    page_size = min(page_size, 200)

    q = sb.table("document_forms").select(
        "id,doc_id,doc_name,document_family,created_at,updated_at",
        count="exact",
    )
    if document_family:
        q = q.eq("document_family", document_family)
    offset = (page - 1) * page_size
    q = q.order("document_family").order("doc_name").range(offset, offset + page_size - 1)
    catalog_res = q.execute()
    catalog_rows = catalog_res.data or []
    total = catalog_res.count or 0

    if not catalog_rows:
        return {"items": [], "total": total, "page": page, "page_size": page_size}

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
        if s["status"] == _CANDIDATE:
            candidate_count_map[cid] = candidate_count_map.get(cid, 0) + 1

    items = []
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

        items.append({
            **cat,
            "availability": avail,
            "schema_id": approved["id"] if approved else None,
            "schema_status": approved["status"] if approved else None,
            "candidate_count": ccount,
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }
