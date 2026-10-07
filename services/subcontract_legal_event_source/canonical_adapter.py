"""
Confirmed subcontract legal event → canonical C1 facts.
acquisition_mode = EXISTING_SOURCE_FACT
source_kind = OPERATIONAL_EVENT_RECORD

Rules:
- Single confirmed event only (no latest scan, no history scan)
- Never emit False — absent = {}
- Wrong status → {}
- Wrong site/subcontractor → {}
"""
from __future__ import annotations
from typing import Any, Dict


def project_confirmed_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Project one confirmed event row → canonical fact dict.

    Returns {} if event is not CONFIRMED or event_type is unrecognized.
    Never synthesizes False. Missing → absent.
    """
    if not event or event.get("status") != "CONFIRMED":
        return {}

    etype = event.get("event_type", "")
    actor_role = event.get("obligated_actor_role")

    if etype == "ART35_DIRECT_PAYMENT_CONFIRMATION_REQUIRED":
        if not actor_role:
            return {}
        return {
            "subcontract_legal_actor_role": actor_role,
            "art35_direct_payment_confirmation_required": True,
        }

    if etype == "ART35_DIRECT_PAYMENT_BASIS":
        basis = event.get("basis_type")
        if not actor_role or not basis:
            return {}
        return {
            "subcontract_legal_actor_role": actor_role,
            "art35_direct_payment_basis_type": basis,
        }

    if etype == "ART36_PAYMENT_INCREASE_RECEIVED":
        if not actor_role:
            return {}
        return {
            "subcontract_legal_actor_role": actor_role,
            "art36_contract_adjustment_direction": "INCREASE",
        }

    if etype == "ART36_PAYMENT_REDUCTION_RECEIVED":
        if not actor_role:
            return {}
        return {
            "subcontract_legal_actor_role": actor_role,
            "art36_contract_adjustment_direction": "DECREASE",
        }

    if etype == "ART37_COMPLETION_OR_PROGRESS_NOTICE_RECEIVED":
        if not actor_role:
            return {}
        return {
            "subcontract_legal_actor_role": actor_role,
            "art37_completion_or_progress_notice_received": True,
        }

    if etype == "ART37_INSPECTION_COMPLETED_AS_DESIGNED":
        if not actor_role:
            return {}
        return {
            "subcontract_legal_actor_role": actor_role,
            "art37_inspection_completed_as_designed": True,
        }

    return {}


def get_event_provenance(event: Dict[str, Any]) -> Dict[str, Any]:
    """Return provenance metadata for the projected facts."""
    return {
        "mode": "EXISTING_SOURCE_FACT",
        "source_kind": "OPERATIONAL_EVENT_RECORD",
        "event_id": str(event.get("id", "")),
        "subcontractor_id": str(event.get("subcontractor_id", "")),
        "event_type": event.get("event_type", ""),
        "confirmed_at": str(event.get("confirmed_at", "")),
    }
