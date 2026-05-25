"""Runtime Activation Service v1.1 — candidate → runtime objects + inspection_sets.

v1.1: Activation also creates/updates inspection_sets + inspection_set_items
      for inspection-anchor.html compatibility.

Only this service creates runtime_task / runtime_schedule from candidates.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from db.supabase_client import get_supabase
from services import runtime_task_service as task_svc
from watch_engine.runtime_bus.event_envelope import create_envelope, emit_envelope

logger = logging.getLogger(__name__)

# ----- candidate_type → obligation_type mapping -----
_CANDIDATE_TO_OBLIGATION: dict[str, str] = {
    "inspection": "INSPECT",
    "appointment": "APPOINT",
    "report": "REPORT",
    "training": "DOCUMENT",
    "compliance_check": "ACTION",
    "permit": "DOCUMENT",
}

_DEFAULT_CYCLES: dict[str, tuple] = {
    "INSPECT": ("year", 1),
    "APPOINT": ("year", 1),
    "REPORT": ("year", 1),
    "DOCUMENT": ("year", 1),
    "ACTION": ("year", 1),
}


def _sync_inspection_set(
    cand: dict,
    assignee_id: str | None,
    next_due_date: str | None,
    task_id: str,
    docs_created: list[dict],
) -> dict | None:
    """Create or update inspection_set + items on candidate activation.

    - If inspection_set already exists (from Legal Adapter projection), UPDATE with
      assignee, schedule_anchor_date, and link to activated task.
    - If not exists, CREATE new inspection_set.
    - Create inspection_set_items from document requirements.

    Returns created/updated inspection_set or None on failure.
    """
    try:
        sb = get_supabase()
        payload = cand.get("payload") or {}
        law_name = payload.get("law_name") or ""
        law_article = payload.get("article") or ""
        tenant_id = str(cand["tenant_id"])
        facility_id = str(cand["facility_id"])
        obl_type = _CANDIDATE_TO_OBLIGATION.get(cand["candidate_type"], "OTHER")
        cycle_unit, cycle_value = _DEFAULT_CYCLES.get(obl_type, ("year", 1))

        # Check if inspection_set already exists (from projection)
        existing = (
            sb.table("inspection_sets")
            .select("id")
            .eq("factory_id", facility_id)
            .eq("law_name", law_name)
            .eq("law_article", law_article)
            .limit(1)
            .execute()
        )

        if existing.data:
            # UPDATE existing with activation data
            set_id = existing.data[0]["id"]
            update_data = {"status_code": "ACTIVATED"}
            if assignee_id:
                update_data["assignee_user_id"] = assignee_id
            if next_due_date:
                update_data["schedule_anchor_date"] = next_due_date
                update_data["anchor_confirmed"] = True
            sb.table("inspection_sets").update(update_data).eq("id", set_id).execute()
            logger.info("Inspection set updated on activation: %s", set_id)
        else:
            # CREATE new inspection_set
            set_id = str(uuid.uuid4())
            row = {
                "id": set_id,
                "company_id": tenant_id,
                "factory_id": facility_id,
                "inspection_set_name": (cand.get("title") or "")[:200],
                "law_name": law_name,
                "law_article": law_article,
                "obligation_type": obl_type,
                "obligation_summary": cand.get("description") or cand.get("title"),
                "cycle_unit": cycle_unit,
                "cycle_value": cycle_value,
                "source": "LEGAL_ENGINE",
                "status_code": "ACTIVATED",
                "is_active": True,
                "assignee_user_id": assignee_id,
            }
            if next_due_date:
                row["schedule_anchor_date"] = next_due_date
                row["anchor_confirmed"] = True
            sb.table("inspection_sets").insert(row).execute()
            logger.info("Inspection set created on activation: %s", set_id)

        # CREATE inspection_set_items from document requirements
        if docs_created:
            for i, doc in enumerate(docs_created):
                item_row = {
                    "id": str(uuid.uuid4()),
                    "inspection_set_id": set_id,
                    "item_name": doc.get("title") or f"점검항목 {i + 1}",
                    "sort_order": i + 1,
                    "is_active": True,
                }
                try:
                    sb.table("inspection_set_items").insert(item_row).execute()
                except Exception:
                    pass  # skip duplicates

        return {"inspection_set_id": set_id, "items_created": len(docs_created)}
    except Exception as e:
        logger.warning("Failed to sync inspection_set on activation: %s", e)
        return None


async def activate_candidate(
    candidate_id: str,
    assignee_id: Optional[str] = None,
    recurrence_rule: Optional[str] = None,
    next_due_date: Optional[str] = None,
    custom_title: Optional[str] = None,
    custom_description: Optional[str] = None,
    selected_document_ids: list[str] = None,
    selected_evidence_ids: list[str] = None,
) -> dict:
    """Activate a candidate: create runtime_task + schedule + doc/evidence + inspection_set."""
    sb = get_supabase()

    # 1. Fetch candidate
    res = sb.table("runtime_candidate").select("*").eq("id", candidate_id).execute()
    if not res.data:
        raise ValueError(f"Candidate {candidate_id} not found")
    cand = res.data[0]

    if cand["status"] not in ("projected", "pending_review", "approved"):
        raise ValueError(f"Cannot activate candidate in status={cand['status']}")

    # 2. Create runtime_task
    task = await task_svc.create_task({
        "tenant_id": str(cand["tenant_id"]),
        "facility_id": str(cand["facility_id"]),
        "source_engine": cand["source_engine"],
        "source_ref_id": cand.get("source_ref_id"),
        "source_event_id": cand.get("source_event_id"),
        "trace_id": cand["trace_id"],
        "task_type": cand["candidate_type"],
        "title": custom_title or cand["title"],
        "description": custom_description or cand.get("description"),
        "priority": cand["priority"],
        "assignee_id": assignee_id,
        "due_date": next_due_date,
        "metadata": {"candidate_id": candidate_id, **(cand.get("metadata") or {})},
    })
    task_id = task["id"]

    # 3. Create runtime_schedule (if due date provided)
    schedule = None
    if next_due_date:
        sched_row = {
            "id": str(uuid.uuid4()),
            "tenant_id": str(cand["tenant_id"]),
            "facility_id": str(cand["facility_id"]),
            "task_id": task_id,
            "schedule_type": "periodic" if recurrence_rule else "one_time",
            "recurrence_rule": recurrence_rule,
            "next_due_date": next_due_date,
            "inspector_id": assignee_id,
            "status": "active",
        }
        sb.table("runtime_schedule").insert(sched_row).execute()
        schedule = sched_row

    # 4. Migrate document requirements
    doc_ids = selected_document_ids or []
    if not doc_ids:
        doc_res = sb.table("runtime_candidate_document_req").select("*").eq("candidate_id", candidate_id).execute()
        doc_ids = [d["id"] for d in (doc_res.data or [])]

    docs_created = []
    for did in doc_ids:
        d_res = sb.table("runtime_candidate_document_req").select("*").eq("id", did).execute()
        if d_res.data:
            d = d_res.data[0]
            row = {
                "id": str(uuid.uuid4()),
                "tenant_id": str(cand["tenant_id"]),
                "facility_id": str(cand["facility_id"]),
                "task_id": task_id,
                "document_type": d["document_type"],
                "title": d["title"],
                "document_form_id": d.get("document_form_id"),
            }
            sb.table("runtime_document_requirement").insert(row).execute()
            docs_created.append(row)

    # 5. Migrate evidence requirements
    evi_ids = selected_evidence_ids or []
    if not evi_ids:
        evi_res = sb.table("runtime_candidate_evidence_req").select("*").eq("candidate_id", candidate_id).execute()
        evi_ids = [e["id"] for e in (evi_res.data or [])]

    evis_created = []
    for eid in evi_ids:
        e_res = sb.table("runtime_candidate_evidence_req").select("*").eq("id", eid).execute()
        if e_res.data:
            e = e_res.data[0]
            row = {
                "id": str(uuid.uuid4()),
                "tenant_id": str(cand["tenant_id"]),
                "facility_id": str(cand["facility_id"]),
                "task_id": task_id,
                "evidence_type": e["evidence_type"],
                "title": e["title"],
            }
            sb.table("runtime_evidence_requirement").insert(row).execute()
            evis_created.append(row)

    # 6. Sync inspection_sets + inspection_set_items
    inspection_result = _sync_inspection_set(
        cand=cand,
        assignee_id=assignee_id,
        next_due_date=next_due_date,
        task_id=task_id,
        docs_created=docs_created,
    )

    # 7. Update candidate status
    sb.table("runtime_candidate").update({
        "status": "activated",
        "activated_task_id": task_id,
        "activated_at": "now()",
        "activated_by": assignee_id,
    }).eq("id", candidate_id).execute()

    # 8. Emit activation event
    envelope = create_envelope(
        event_type="runtime.candidate_activated",
        tenant_id=str(cand["tenant_id"]),
        source="binding_engine",
        payload={"candidate_id": candidate_id, "task_id": task_id, "title": task["title"]},
        trace_id=cand["trace_id"],
    )
    await emit_envelope(envelope)

    return {
        "candidate_id": candidate_id,
        "task": task,
        "schedule": schedule,
        "documents_created": len(docs_created),
        "evidence_created": len(evis_created),
        "inspection_set": inspection_result,
    }
