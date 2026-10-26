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


def _resolve_evidence_connections_for_catalog(
    sb, evidence_fields: list, fields: list, schema_id: str
) -> list:
    """Resolve Evidence↔Field FK connections for catalog API response.

    Returns list of resolved connection dicts. UNRESOLVED entries are included
    with status='UNRESOLVED' so the frontend can distinguish failure modes.
    Does NOT raise — caller should surface UNRESOLVED entries to the frontend.
    """
    if not evidence_fields:
        return []
    field_by_candidate = {
        str(f.get("field_candidate_id") or ""): f
        for f in fields
        if f.get("field_candidate_id")
    }
    connections = []
    for ev in evidence_fields:
        ev_id = str(ev.get("id") or "")
        evidence_candidate_id = str(ev.get("evidence_candidate_id") or "")
        if not evidence_candidate_id:
            connections.append({
                "evidence_field_id": ev_id,
                "status": "UNRESOLVED",
                "reason": "no_evidence_candidate_id",
            })
            continue
        efc_res = (
            sb.table("evidence_field_candidate")
            .select("id,field_candidate_id,status")
            .eq("id", evidence_candidate_id)
            .single()
            .execute()
        )
        efc = efc_res.data if efc_res and efc_res.data else None
        if not efc:
            connections.append({
                "evidence_field_id": ev_id,
                "status": "UNRESOLVED",
                "reason": "evidence_candidate_not_found",
            })
            continue
        field_candidate_id = str(efc.get("field_candidate_id") or "")
        matched_fields = [
            f for f in fields
            if str(f.get("field_candidate_id") or "") == field_candidate_id
            and str(f.get("form_schema_id") or "") == schema_id
        ]
        if len(matched_fields) == 0:
            connections.append({
                "evidence_field_id": ev_id,
                "status": "UNRESOLVED",
                "reason": "no_matching_field",
                "evidence_candidate_status": str(efc.get("status") or "UNKNOWN"),
            })
        elif len(matched_fields) > 1:
            connections.append({
                "evidence_field_id": ev_id,
                "status": "UNRESOLVED",
                "reason": "ambiguous_field",
                "evidence_candidate_status": str(efc.get("status") or "UNKNOWN"),
            })
        else:
            rf = matched_fields[0]
            connections.append({
                "evidence_field_id": ev_id,
                "status": "RESOLVED",
                "evidence_candidate_status": str(efc.get("status") or "UNKNOWN"),
                "field_id": str(rf.get("id") or ""),
                "field_key": str(rf.get("field_key") or ""),
                "input_type": str(rf.get("input_type") or ""),
            })
    return connections


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
    resolved_evidence_connections: list = []

    query_schema = schema if schema else (candidates[0] if candidates else None)
    if query_schema:
        schema_id = query_schema["id"]
        fields = (sb.table("runtime_field").select("*").eq("form_schema_id", schema_id).order("field_order").execute()).data or []
        checklists = (sb.table("runtime_checklist_item").select("*").eq("form_schema_id", schema_id).order("item_order").execute()).data or []
        evidence_fields = (sb.table("runtime_evidence_field").select("*").eq("form_schema_id", schema_id).execute()).data or []
        resolved_evidence_connections = _resolve_evidence_connections_for_catalog(
            sb, evidence_fields, fields, schema_id
        )

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
        "resolved_evidence_connections": resolved_evidence_connections,
    }
