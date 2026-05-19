"""Runtime Activation Service — candidate → runtime objects.

Only this service creates runtime_task / runtime_schedule from candidates.
"""
from __future__ import annotations

import uuid
from typing import Optional

from db.supabase_client import get_supabase
from services import runtime_task_service as task_svc
from watch_engine.runtime_bus.event_envelope import create_envelope, emit_envelope


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
    """Activate a candidate: create runtime_task + schedule + doc/evidence."""
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
        # Default: migrate all candidate docs
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

    # 6. Update candidate status
    sb.table("runtime_candidate").update({
        "status": "activated",
        "activated_task_id": task_id,
        "activated_at": "now()",
        "activated_by": assignee_id,
    }).eq("id", candidate_id).execute()

    # 7. Emit activation event
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
    }
