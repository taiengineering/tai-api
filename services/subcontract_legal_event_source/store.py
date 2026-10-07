"""
construction_subcontract_legal_events CRUD + DRAFT→CONFIRMED→VOID lifecycle.
CONFIRMED rows are the authoritative source for C1 EXISTING_SOURCE_FACT.
Hard DELETE = 0. CONFIRMED rows are immutable.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException


TABLE = "construction_subcontract_legal_events"

EVENT_TYPE_ACTOR_ROLE = {
    "ART35_DIRECT_PAYMENT_CONFIRMATION_REQUIRED": "GENERAL_CONTRACTOR",
    "ART35_DIRECT_PAYMENT_BASIS": "PROJECT_OWNER",
    "ART36_PAYMENT_INCREASE_RECEIVED": "GENERAL_CONTRACTOR",
    "ART36_PAYMENT_REDUCTION_RECEIVED": "GENERAL_CONTRACTOR",
    "ART37_COMPLETION_OR_PROGRESS_NOTICE_RECEIVED": "GENERAL_CONTRACTOR",
    "ART37_INSPECTION_COMPLETED_AS_DESIGNED": "GENERAL_CONTRACTOR",
}

VALID_BASIS_TYPES = frozenset({
    "AGREEMENT", "COURT_ORDER", "PAYMENT_DEFAULT_2X",
    "INSOLVENT", "NO_PAYMENT_GUARANTEE", "PUBLIC_LOWBID",
})

VALID_ADJUSTMENT_REASONS = frozenset({"DESIGN_CHANGE", "ECONOMIC_CHANGE"})
VALID_NOTICE_TYPES = frozenset({"COMPLETION", "PROGRESS"})


def _resolve_subcontractor_identity(sb, site_id: str, subcontractor_id: str) -> Dict[str, Any]:
    """Authoritative entity resolution from DB. Raises 404/409 on mismatch."""
    site_r = sb.table("construction_sites").select("company_id").eq("id", site_id).limit(1).execute()
    if not site_r.data:
        raise HTTPException(404, "현장을 찾을 수 없습니다.")
    tenant_company_id = site_r.data[0]["company_id"]

    sub_r = sb.table("subcontractors").select("id, site_id, company_id").eq("id", subcontractor_id).limit(1).execute()
    if not sub_r.data:
        raise HTTPException(404, "하도급업체를 찾을 수 없습니다.")
    sub = sub_r.data[0]
    if str(sub["site_id"]) != str(site_id):
        raise HTTPException(409, "하도급업체가 해당 현장에 속하지 않습니다.")

    return {
        "tenant_company_id": str(tenant_company_id),
        "subcontractor_company_id": str(sub["company_id"]),
    }


def list_events(sb, site_id: str, subcontractor_id: str) -> List[Dict]:
    r = sb.table(TABLE).select("*").eq("site_id", site_id).eq("subcontractor_id", subcontractor_id).order("created_at", desc=True).execute()
    return r.data or []


def get_event(sb, event_id: str) -> Dict:
    r = sb.table(TABLE).select("*").eq("id", event_id).limit(1).execute()
    if not r.data:
        raise HTTPException(404, "이벤트를 찾을 수 없습니다.")
    return r.data[0]


def create_draft(sb, site_id: str, subcontractor_id: str, body: Dict, created_by: Optional[str] = None) -> Dict:
    event_type = body.get("event_type")
    if event_type not in EVENT_TYPE_ACTOR_ROLE:
        raise HTTPException(422, f"유효하지 않은 event_type: {event_type}")

    identity = _resolve_subcontractor_identity(sb, site_id, subcontractor_id)
    obligated_actor_role = EVENT_TYPE_ACTOR_ROLE[event_type]

    row = {
        "site_id": site_id,
        "subcontractor_id": subcontractor_id,
        "tenant_company_id": identity["tenant_company_id"],
        "subcontractor_company_id": identity["subcontractor_company_id"],
        "event_type": event_type,
        "event_version": 1,
        "obligated_actor_role": obligated_actor_role,
        "obligated_actor_company_id": body.get("obligated_actor_company_id"),
        "counterparty_company_id": body.get("counterparty_company_id"),
        "occurred_at": body.get("occurred_at"),
        "basis_type": body.get("basis_type"),
        "adjustment_reason": body.get("adjustment_reason"),
        "original_amount": body.get("original_amount"),
        "adjusted_amount": body.get("adjusted_amount"),
        "notice_type": body.get("notice_type"),
        "notice_received_at": body.get("notice_received_at"),
        "inspection_completed_at": body.get("inspection_completed_at"),
        "design_conformance_confirmed": body.get("design_conformance_confirmed"),
        "notice_event_id": body.get("notice_event_id"),
        "scope_description": body.get("scope_description"),
        "evidence_ref": body.get("evidence_ref"),
        "status": "DRAFT",
        "confirmed_at": None,
        "voided_at": None,
        "created_by": created_by,
    }
    r = sb.table(TABLE).insert(row).execute()
    if not r.data:
        raise HTTPException(500, "이벤트 생성 실패")
    return r.data[0]


def update_draft(sb, event_id: str, body: Dict) -> Dict:
    existing = get_event(sb, event_id)
    if existing["status"] != "DRAFT":
        raise HTTPException(409, f"DRAFT 상태만 수정 가능합니다. 현재 상태: {existing['status']}")

    allowed_patch_fields = {
        "obligated_actor_company_id", "counterparty_company_id", "occurred_at",
        "basis_type", "adjustment_reason", "original_amount", "adjusted_amount",
        "notice_type", "notice_received_at", "inspection_completed_at",
        "design_conformance_confirmed", "notice_event_id", "scope_description", "evidence_ref",
    }
    patch = {k: v for k, v in body.items() if k in allowed_patch_fields}
    patch["updated_at"] = datetime.now(timezone.utc).isoformat()

    r = sb.table(TABLE).update(patch).eq("id", event_id).execute()
    if not r.data:
        raise HTTPException(500, "이벤트 수정 실패")
    return r.data[0]


def _validate_for_confirm(event: Dict) -> None:
    """Confirm pre-conditions. Raises 422 (HTTPException) if required fields missing."""
    etype = event["event_type"]

    if not event.get("occurred_at"):
        raise HTTPException(422, "occurred_at 필수")
    if not event.get("obligated_actor_company_id"):
        raise HTTPException(422, "obligated_actor_company_id 필수 (actor company 권원 미확인 시 CONFIRM 불가)")

    if etype == "ART35_DIRECT_PAYMENT_BASIS":
        if not event.get("basis_type") or event["basis_type"] not in VALID_BASIS_TYPES:
            raise HTTPException(422, "basis_type 필수 (ART35_DIRECT_PAYMENT_BASIS)")
        if not event.get("evidence_ref"):
            raise HTTPException(422, "evidence_ref 필수 (ART35_DIRECT_PAYMENT_BASIS)")

    elif etype in ("ART36_PAYMENT_INCREASE_RECEIVED", "ART36_PAYMENT_REDUCTION_RECEIVED"):
        if not event.get("adjustment_reason") or event["adjustment_reason"] not in VALID_ADJUSTMENT_REASONS:
            raise HTTPException(422, "adjustment_reason 필수 (ART36)")
        orig = event.get("original_amount")
        adj = event.get("adjusted_amount")
        if orig is None or adj is None:
            raise HTTPException(422, "original_amount, adjusted_amount 필수 (ART36)")
        if etype == "ART36_PAYMENT_INCREASE_RECEIVED" and float(adj) <= float(orig):
            raise HTTPException(422, "증액: adjusted_amount > original_amount 이어야 합니다.")
        if etype == "ART36_PAYMENT_REDUCTION_RECEIVED" and float(adj) >= float(orig):
            raise HTTPException(422, "감액: adjusted_amount < original_amount 이어야 합니다.")

    elif etype == "ART37_COMPLETION_OR_PROGRESS_NOTICE_RECEIVED":
        if not event.get("notice_type") or event["notice_type"] not in VALID_NOTICE_TYPES:
            raise HTTPException(422, "notice_type 필수 (ART37_E)")
        if not event.get("notice_received_at"):
            raise HTTPException(422, "notice_received_at 필수 (ART37_E)")
        nr = event["notice_received_at"]
        if isinstance(nr, str):
            try:
                nr_dt = datetime.fromisoformat(nr.replace("Z", "+00:00"))
                if nr_dt > datetime.now(timezone.utc):
                    raise HTTPException(422, "notice_received_at이 미래 시각입니다.")
            except ValueError:
                pass

    elif etype == "ART37_INSPECTION_COMPLETED_AS_DESIGNED":
        if not event.get("inspection_completed_at"):
            raise HTTPException(422, "inspection_completed_at 필수 (ART37_F)")
        if not event.get("design_conformance_confirmed"):
            raise HTTPException(422, "design_conformance_confirmed=true 필수 (ART37_F)")
        if not event.get("notice_event_id"):
            raise HTTPException(422, "notice_event_id 필수 (ART37_F — FK to ART37_E event)")
        if not event.get("evidence_ref"):
            raise HTTPException(422, "evidence_ref 필수 (ART37_F)")


def _validate_notice_event_link(sb, event: Dict) -> None:
    """ART37_F: notice_event_id must be CONFIRMED ART37_E of same site+subcontractor."""
    if event["event_type"] != "ART37_INSPECTION_COMPLETED_AS_DESIGNED":
        return
    notice_event_id = event.get("notice_event_id")
    if not notice_event_id:
        return
    r = sb.table(TABLE).select("id, event_type, site_id, subcontractor_id, status").eq("id", str(notice_event_id)).limit(1).execute()
    if not r.data:
        raise HTTPException(422, "notice_event_id가 존재하지 않습니다.")
    ne = r.data[0]
    if ne["event_type"] != "ART37_COMPLETION_OR_PROGRESS_NOTICE_RECEIVED":
        raise HTTPException(422, "notice_event_id는 ART37_COMPLETION_OR_PROGRESS_NOTICE_RECEIVED 이어야 합니다.")
    if ne["status"] != "CONFIRMED":
        raise HTTPException(422, "notice_event_id는 CONFIRMED 상태이어야 합니다.")
    if str(ne["site_id"]) != str(event["site_id"]):
        raise HTTPException(422, "notice_event_id의 site_id가 다릅니다.")
    if str(ne["subcontractor_id"]) != str(event["subcontractor_id"]):
        raise HTTPException(422, "notice_event_id의 subcontractor_id가 다릅니다.")


def confirm_event(sb, event_id: str) -> Dict:
    event = get_event(sb, event_id)
    if event["status"] != "DRAFT":
        raise HTTPException(409, f"DRAFT 상태만 CONFIRM 가능합니다. 현재: {event['status']}")

    _validate_for_confirm(event)
    _validate_notice_event_link(sb, event)

    patch = {
        "status": "CONFIRMED",
        "confirmed_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    r = sb.table(TABLE).update(patch).eq("id", event_id).execute()
    if not r.data:
        raise HTTPException(500, "CONFIRM 실패")
    return r.data[0]


def void_event(sb, event_id: str) -> Dict:
    event = get_event(sb, event_id)
    if event["status"] == "VOID":
        raise HTTPException(409, "이미 VOID 상태입니다.")
    patch = {
        "status": "VOID",
        "voided_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    r = sb.table(TABLE).update(patch).eq("id", event_id).execute()
    if not r.data:
        raise HTTPException(500, "VOID 실패")
    return r.data[0]
