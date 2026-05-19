"""Runtime Binding Engine — Core Candidate Projection.

Converts RuntimeCandidateInput → runtime_candidate + sub-objects.
Does NOT create runtime_task. That happens only on activation.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from db.supabase_client import get_supabase
from models.runtime_candidate_contract import RuntimeCandidateInput
from watch_engine.runtime_bus.event_envelope import create_envelope, emit_envelope

logger = logging.getLogger(__name__)


async def project_candidate(inp: RuntimeCandidateInput) -> dict:
    """Project a single candidate input into candidate storage."""
    sb = get_supabase()
    cid = inp.candidate_id

    # 1. Insert runtime_candidate
    row = {
        "id": cid,
        "tenant_id": inp.tenant_id,
        "facility_id": inp.facility_id,
        "candidate_type": inp.candidate_type,
        "candidate_category": inp.candidate_category,
        "title": inp.title,
        "description": inp.description,
        "source_engine": inp.source_engine,
        "source_ref_id": inp.source_ref_id,
        "source_event_id": inp.source_event_id,
        "trace_id": inp.trace_id,
        "priority": inp.priority,
        "confidence": inp.confidence,
        "status": "projected",
        "requires_activation": inp.requires_activation,
        "payload": inp.payload,
        "source_trace": inp.source_trace,
    }
    sb.table("runtime_candidate").insert(row).execute()

    # 2. Document requirement candidates
    for doc in inp.document_suggestions:
        sb.table("runtime_candidate_document_req").insert({
            "id": str(uuid.uuid4()),
            "tenant_id": inp.tenant_id,
            "candidate_id": cid,
            "document_type": doc.get("document_type", "form"),
            "title": doc.get("title", ""),
            "document_form_id": doc.get("document_form_id"),
        }).execute()

    # 3. Evidence requirement candidates
    for evi in inp.evidence_suggestions:
        sb.table("runtime_candidate_evidence_req").insert({
            "id": str(uuid.uuid4()),
            "tenant_id": inp.tenant_id,
            "candidate_id": cid,
            "evidence_type": evi.get("evidence_type", "file"),
            "title": evi.get("title", ""),
        }).execute()

    # 4. Schedule candidate
    if inp.schedule_suggestion:
        sb.table("runtime_candidate_schedule").insert({
            "id": str(uuid.uuid4()),
            "tenant_id": inp.tenant_id,
            "candidate_id": cid,
            "schedule_type": inp.schedule_suggestion.get("schedule_type", "periodic"),
            "recurrence_rule": inp.schedule_suggestion.get("recurrence_rule"),
            "suggested_due_date": inp.schedule_suggestion.get("suggested_due_date"),
        }).execute()

    # 5. Emit projection event
    envelope = create_envelope(
        event_type="runtime.candidate_projected",
        tenant_id=inp.tenant_id,
        source="binding_engine",
        payload={"candidate_id": cid, "candidate_type": inp.candidate_type, "title": inp.title},
        trace_id=inp.trace_id,
    )
    await emit_envelope(envelope)

    return {"candidate_id": cid, "status": "projected", "candidate_type": inp.candidate_type}


async def project_candidates(inputs: list[RuntimeCandidateInput]) -> dict:
    """Batch project multiple candidates."""
    results = []
    for inp in inputs:
        r = await project_candidate(inp)
        results.append(r)
    return {"projected": results, "count": len(results)}


async def log_residual(
    tenant_id: str, facility_id: str,
    source_engine: str, source_ref_id: str,
    candidate_type: str, reason: str, raw_data: dict = None,
) -> None:
    sb = get_supabase()
    try:
        sb.table("runtime_candidate_residual").insert({
            "tenant_id": tenant_id,
            "facility_id": facility_id,
            "source_engine": source_engine,
            "source_ref_id": source_ref_id,
            "candidate_type": candidate_type,
            "reason": reason,
            "raw_data": raw_data or {},
        }).execute()
    except Exception:
        logger.warning("candidate residual log failed", exc_info=True)
