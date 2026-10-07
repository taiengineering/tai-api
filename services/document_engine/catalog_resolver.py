"""OBJ02-B1: Catalog-to-runtime schema resolver.

Resolves which runtime_form_schema is APPROVED_FOR_RUNTIME_USE
for a given catalog document (document_forms.id).

Availability states:
  READY_FOR_EDIT   — exactly one APPROVED_FOR_RUNTIME_USE schema exists
  PREPARING        — one or more CANDIDATE schemas exist, none approved
  NO_SCHEMA        — no runtime_form_schema row bound to this catalog doc
"""
from __future__ import annotations
from typing import Optional
from db.supabase_client import get_supabase

_APPROVED = "APPROVED_FOR_RUNTIME_USE"
_CANDIDATE = "CANDIDATE"


def resolve_catalog_runtime_schema(catalog_document_id: str) -> dict:
    """Return schema + fields + availability for a catalog document.

    Args:
        catalog_document_id: document_forms.id (UUID string).
            Named catalog_document_id to distinguish from the business key
            document_forms.doc_id (e.g. 'DOC-CHK-001').

    Returns:
        {
          "availability": "READY_FOR_EDIT" | "PREPARING" | "NO_SCHEMA",
          "schema": <runtime_form_schema row> | None,
          "fields": [<runtime_field rows>],
          "checklists": [<runtime_checklist_item rows>],
          "evidence_fields": [<runtime_evidence_field rows>],
        }

    Raises:
        ValueError: catalog_document_id not found in document_forms
    """
    sb = get_supabase()

    catalog_row = (
        sb.table("document_forms")
        .select("id,doc_id,doc_name")
        .eq("id", catalog_document_id)
        .single()
        .execute()
    )
    if not catalog_row.data:
        raise ValueError(f"catalog document not found: {catalog_document_id}")

    schemas = (
        sb.table("runtime_form_schema")
        .select("id,status,form_name,version,catalog_document_id,source_trace")
        .eq("catalog_document_id", catalog_document_id)
        .execute()
    )
    rows = schemas.data or []

    approved = [r for r in rows if r["status"] == _APPROVED]
    candidates = [r for r in rows if r["status"] == _CANDIDATE]

    if len(approved) == 1:
        schema = approved[0]
        availability = "READY_FOR_EDIT"
    elif len(approved) > 1:
        # uq_rfs_catalog_active_approved should prevent this; guard anyway
        raise RuntimeError(
            f"integrity violation: multiple APPROVED_FOR_RUNTIME_USE schemas "
            f"for catalog_document_id={catalog_document_id}"
        )
    elif candidates:
        schema = None
        candidate_schema = candidates[0]
        availability = "PREPARING"
    else:
        schema = None
        candidate_schema = None
        availability = "NO_SCHEMA"

    fields: list = []
    checklists: list = []
    evidence_fields: list = []

    query_schema = schema if schema else (candidates[0] if candidates else None)
    if query_schema:
        schema_id = query_schema["id"]
        fields = (sb.table("runtime_field").select("*").eq("form_schema_id", schema_id).order("field_order").execute()).data or []
        checklists = (sb.table("runtime_checklist_item").select("*").eq("form_schema_id", schema_id).order("item_order").execute()).data or []
        evidence_fields = (sb.table("runtime_evidence_field").select("*").eq("form_schema_id", schema_id).execute()).data or []

    return {
        "availability": availability,
        "active_schema_id": schema["id"] if schema else None,
        "active_schema_status": schema["status"] if schema else None,
        "candidate_schema_id": candidates[0]["id"] if (candidates and not schema) else None,
        "candidate_schema_status": _CANDIDATE if (candidates and not schema) else None,
        "schema": schema,
        "fields": fields,
        "checklists": checklists,
        "evidence_fields": evidence_fields,
    }
