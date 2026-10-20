"""
services/document_link_review_write.py
WO-TAI-DOC-WP03B-IMPLEMENT-001

Write-path service for unified_document_link.
All mutations go through DB RPC functions (fn_udl_propose / fn_udl_transition)
so that the audit trigger can bind app.actor atomically with the DML.

DB writes: via supabase.rpc() only — no direct INSERT/UPDATE from Python.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

log = logging.getLogger(__name__)


class DocumentLinkWriteError(Exception):
    """Domain error from the RPC layer."""

    def __init__(self, error_code: str, detail: str = "") -> None:
        super().__init__(detail or error_code)
        self.error_code = error_code
        self.detail = detail


def _extract(resp: Any) -> Any:
    """Extract .data from a supabase-py ExecuteResponse."""
    if hasattr(resp, "data"):
        return resp.data
    return resp


def propose_link(
    supabase: Any,
    *,
    actor_id: str,
    saas_catalog_id: str,
    reference_form_id: str,
    relation_type: str,
    evidence_note: str,
) -> dict[str, Any]:
    """
    Create a new unified_document_link row in PROPOSED state.
    actor_id is bound to the audit trail via app.actor session variable (set inside the RPC).
    Raises DocumentLinkWriteError on domain errors; lets other exceptions propagate.
    """
    params = {
        "p_actor_id":          actor_id,
        "p_saas_catalog_id":   saas_catalog_id,
        "p_reference_form_id": reference_form_id,
        "p_relation_type":     relation_type,
        "p_evidence_note":     evidence_note,
    }
    resp = supabase.rpc("fn_udl_propose", params).execute()
    data = _extract(resp)
    if not isinstance(data, dict):
        raise DocumentLinkWriteError(
            "MALFORMED_RESPONSE",
            f"fn_udl_propose returned unexpected type: {type(data).__name__}",
        )
    if data.get("ok") is True:
        return data.get("data") or {}
    raise DocumentLinkWriteError(
        data.get("error") or "PROPOSE_FAILED",
        data.get("detail") or "",
    )


def transition_link(
    supabase: Any,
    *,
    actor_id: str,
    link_id: str,
    new_state: str,
    owner_approval_ref: Optional[str] = None,
    final_relation_type: Optional[str] = None,
) -> dict[str, Any]:
    """
    Transition a unified_document_link to new_state.
    actor_id is bound to the audit trail via app.actor session variable.
    owner_approval_ref is required for UNDER_REVIEW→APPROVED and APPROVED→RETIRED transitions.
    final_relation_type optionally overrides relation_type on APPROVED transition.
    Raises DocumentLinkWriteError on domain errors; lets other exceptions propagate.
    """
    params = {
        "p_actor_id":            actor_id,
        "p_link_id":             link_id,
        "p_new_state":           new_state,
        "p_owner_approval_ref":  owner_approval_ref,
        "p_final_relation_type": final_relation_type,
    }
    resp = supabase.rpc("fn_udl_transition", params).execute()
    data = _extract(resp)
    if not isinstance(data, dict):
        raise DocumentLinkWriteError(
            "MALFORMED_RESPONSE",
            f"fn_udl_transition returned unexpected type: {type(data).__name__}",
        )
    if data.get("ok") is True:
        return data.get("data") or {}
    raise DocumentLinkWriteError(
        data.get("error") or "TRANSITION_FAILED",
        data.get("detail") or "",
    )
