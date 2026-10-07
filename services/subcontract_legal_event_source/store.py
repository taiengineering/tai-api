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


def _parse_timestamp_strict(ts: Optional[str], field_name: str) -> datetime:
    """Parse a required timestamp string strictly.

    Contract:
    - missing/empty → HTTPException 422 (missing)
    - malformed (parse error) → HTTPException 422 (invalid format)
    - timezone-naive → HTTPException 422 (timezone required)
    - future → HTTPException 422 (future timestamp)
    - valid past/present → returns datetime
    """
    if not ts or not isinstance(ts, str):
        raise HTTPException(422, f"{field_name} 필수")
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(422, f"{field_name} 형식이 올바르지 않습니다. ISO-8601 timezone-aware 형식 필요.")
    if dt.tzinfo is None:
        raise HTTPException(422, f"{field_name}에 timezone 정보가 없습니다. timezone-aware ISO-8601 형식 필요.")
    if dt > datetime.now(timezone.utc):
        raise HTTPException(422, f"{field_name}이 미래 시각입니다.")
    return dt


def _validate_actor_company_exists(sb, company_id: str) -> None:
    """Verify that obligated_actor_company_id exists in companies master.

    Raises 422 if the company does not exist.
    """
    r = sb.table("companies").select("id").eq("id", company_id).limit(1).execute()
    if not r.data:
        raise HTTPException(422, f"obligated_actor_company_id가 존재하지 않는 회사입니다: {company_id}")


def _actor_candidate_ids(sb, *, site_id: str, subcontractor_id: str) -> List[Dict[str, str]]:
    """Scoped actor candidates: site tenant + same-site parent chain.

    Returns [{company_id, relationship_source: SITE_TENANT|PARENT_CONTRACTOR}].
    Current subcontractor's own company_id is excluded (they are the counterparty).
    Other-site parents are excluded. Cycle-safe.
    """
    seen: Dict[str, str] = {}

    site_r = sb.table("construction_sites").select("company_id").eq("id", site_id).limit(1).execute()
    if site_r.data:
        cid = str(site_r.data[0]["company_id"])
        seen[cid] = "SITE_TENANT"

    visited_subs = {str(subcontractor_id)}
    current_sub_id = str(subcontractor_id)
    while True:
        sub_r = (
            sb.table("subcontractors")
            .select("parent_subcontractor_id, company_id, site_id")
            .eq("id", current_sub_id)
            .limit(1)
            .execute()
        )
        if not sub_r.data:
            break
        sub = sub_r.data[0]
        parent_id = sub.get("parent_subcontractor_id")
        if not parent_id:
            break
        parent_id_str = str(parent_id)
        if parent_id_str in visited_subs:
            break
        parent_r = (
            sb.table("subcontractors")
            .select("company_id, site_id")
            .eq("id", parent_id_str)
            .limit(1)
            .execute()
        )
        if not parent_r.data:
            break
        parent = parent_r.data[0]
        if str(parent["site_id"]) != str(site_id):
            break
        cid = str(parent["company_id"])
        if cid not in seen:
            seen[cid] = "PARENT_CONTRACTOR"
        visited_subs.add(parent_id_str)
        current_sub_id = parent_id_str

    return [{"company_id": cid, "relationship_source": rel} for cid, rel in seen.items()]


def list_actor_candidates(sb, *, site_id: str, subcontractor_id: str) -> List[Dict]:
    """Scoped actor candidates with company names.

    Returns [{id, name, relationship_source}]. Used by the actor-candidates endpoint.
    """
    id_rows = _actor_candidate_ids(sb, site_id=site_id, subcontractor_id=subcontractor_id)
    if not id_rows:
        return []
    company_ids = [r["company_id"] for r in id_rows]
    rel_map = {r["company_id"]: r["relationship_source"] for r in id_rows}
    companies_r = sb.table("companies").select("id, name").in_("id", company_ids).execute()
    name_map = {str(c["id"]): c["name"] for c in (companies_r.data or [])}
    result = []
    for cid, rel in rel_map.items():
        name = name_map.get(cid)
        if name:
            result.append({"id": cid, "name": name, "relationship_source": rel})
    return result


def _validate_actor_candidate_scope(sb, event: Dict) -> None:
    """CONFIRM: obligated_actor_company_id must belong to scoped candidate set.

    Raises 422 if company is not in {SITE_TENANT ∪ PARENT_CONTRACTOR chain}.
    """
    company_id = str(event["obligated_actor_company_id"])
    candidates = _actor_candidate_ids(
        sb,
        site_id=str(event["site_id"]),
        subcontractor_id=str(event["subcontractor_id"]),
    )
    allowed = {r["company_id"] for r in candidates}
    if company_id not in allowed:
        raise HTTPException(
            422,
            "obligated_actor_company_id가 이 하도급 관계의 허용 후보 회사 범위 밖입니다.",
        )


def _validate_for_confirm(sb, event: Dict) -> None:
    """Confirm pre-conditions. Raises 422 (HTTPException) if required fields missing/invalid."""
    etype = event["event_type"]

    _parse_timestamp_strict(event.get("occurred_at"), "occurred_at")

    if not event.get("obligated_actor_company_id"):
        raise HTTPException(422, "obligated_actor_company_id 필수 (actor company 권원 미확인 시 CONFIRM 불가)")
    _validate_actor_company_exists(sb, str(event["obligated_actor_company_id"]))
    _validate_actor_candidate_scope(sb, event)

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
        if not event.get("evidence_ref"):
            raise HTTPException(422, "evidence_ref 필수 (ART37_E)")
        _parse_timestamp_strict(event.get("notice_received_at"), "notice_received_at")

    elif etype == "ART37_INSPECTION_COMPLETED_AS_DESIGNED":
        _parse_timestamp_strict(event.get("inspection_completed_at"), "inspection_completed_at")
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

    _validate_for_confirm(sb, event)
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
    if event["status"] != "CONFIRMED":
        raise HTTPException(409, f"CONFIRMED 상태만 VOID 가능합니다. 현재: {event['status']}")
    patch = {
        "status": "VOID",
        "voided_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    r = sb.table(TABLE).update(patch).eq("id", event_id).execute()
    if not r.data:
        raise HTTPException(500, "VOID 실패")
    return r.data[0]


def get_event_exact(sb, *, site_id: str, subcontractor_id: str, event_id: str) -> Dict:
    """Exact-binding event fetch: event_id + site_id + subcontractor_id must all match.

    Raises 404 if not found or if any of the three identifiers do not match.
    """
    r = (
        sb.table(TABLE)
        .select("*")
        .eq("id", event_id)
        .eq("site_id", site_id)
        .eq("subcontractor_id", subcontractor_id)
        .limit(1)
        .execute()
    )
    if not r.data:
        raise HTTPException(404, "이벤트를 찾을 수 없습니다.")
    return r.data[0]


class SubcontractLegalEventSourceLoadError(RuntimeError):
    """DB query failure loading confirmed subcontract legal event.

    Must NOT be treated as event-absent. LEG execution must be blocked.
    """
    code = "SUBCONTRACT_LEGAL_EVENT_SOURCE_UNAVAILABLE"

    def __init__(self, message: str, *, event_id: Optional[str] = None) -> None:
        super().__init__(message)
        self.event_id = event_id


def load_confirmed_subcontract_legal_event_context(
    sb,
    *,
    site_id: str,
    subcontractor_id: str,
    event_id: str,
) -> Optional[Dict]:
    """Exact-object eligibility: event_id + site_id + subcontractor_id + status=CONFIRMED.

    Contract:
    - event not found / wrong exact binding / DRAFT / VOID → returns None (ABSENT)
    - DB query failure → raises SubcontractLegalEventSourceLoadError (fail-closed)
    - matching CONFIRMED row → returns event dict
    """
    if sb is None:
        raise SubcontractLegalEventSourceLoadError(
            "subcontract legal event source client missing", event_id=event_id
        )
    try:
        r = (
            sb.table(TABLE)
            .select("*")
            .eq("id", event_id)
            .eq("site_id", site_id)
            .eq("subcontractor_id", subcontractor_id)
            .eq("status", "CONFIRMED")
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise SubcontractLegalEventSourceLoadError(
            f"construction_subcontract_legal_events 조회 실패: {exc}", event_id=event_id
        ) from exc
    result = getattr(r, "data", None)
    if not isinstance(result, list):
        raise SubcontractLegalEventSourceLoadError(
            "construction_subcontract_legal_events 응답 형식 오류", event_id=event_id
        )
    if not result:
        return None
    return result[0]
