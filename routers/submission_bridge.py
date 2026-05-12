"""TAI Submission Runtime Bridge v1.0.0
Phase 7: Operational Document → Immutable Filing Asset.

금지: unapproved submission, hidden retry, fake success,
      mutable submitted document, approval bypass filing
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import hashlib, logging

router = APIRouter(prefix="/bridge", tags=["제출 브릿지"])
logger = logging.getLogger("submission_bridge")


def _audit(action, entity, entity_id, user_id="system"):
    logger.info(f"SUBMISSION_BRIDGE_AUDIT | action={action} entity={entity} id={entity_id} by={user_id}")


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


@router.get("/submissions")
def bridge_list_submissions(
    submission_status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    sb = _sb()
    q = sb.table("runtime_submission").select("*, runtime_filing_registry(filing_name, filing_target)")
    if submission_status:
        q = q.eq("submission_status", submission_status)
    offset = (page - 1) * page_size
    q = q.order("created_at", desc=True).range(offset, offset + page_size - 1)
    r = q.execute()
    return {"status": "success", "source": "runtime", "data": r.data or [], "page": page}


@router.get("/submissions/{submission_id}")
def bridge_get_submission(submission_id: str):
    sb = _sb()
    r = sb.table("runtime_submission").select("*, runtime_filing_registry(*)").eq("id", submission_id).execute()
    if not r.data:
        raise HTTPException(404, "Submission not found")
    return {"status": "success", "source": "runtime", "data": r.data[0]}


@router.get("/filing-registry")
def bridge_list_filings(
    filing_type: Optional[str] = Query(None),
):
    sb = _sb()
    q = sb.table("runtime_filing_registry").select("*")
    if filing_type:
        q = q.eq("filing_type", filing_type)
    q = q.order("filing_code").limit(50)
    r = q.execute()
    return {"status": "success", "source": "runtime", "data": r.data or []}


@router.post("/submit-document")
def bridge_submit_document(
    filing_code: str = Query(...),
    submitted_by: str = Query(...),
    submission_channel: str = Query('MANUAL_UPLOAD'),
    generated_document_id: Optional[str] = Query(None),
):
    if submission_channel not in ('API', 'MANUAL_UPLOAD', 'EMAIL', 'GOV_PORTAL'):
        raise HTTPException(400, "Invalid submission_channel")

    sb = _sb()

    # filing registry 확인
    fr = sb.table("runtime_filing_registry").select("id, filing_name").eq("filing_code", filing_code).execute()
    if not fr.data:
        raise HTTPException(404, f"Filing registry not found: {filing_code}")

    # immutable hash
    hash_input = f"{filing_code}:{submitted_by}:{generated_document_id}"
    immutable_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:32]

    row = {
        "filing_registry_id": fr.data[0]["id"],
        "generated_document_id": generated_document_id,
        "submission_status": "READY",
        "submitted_by": submitted_by,
        "submission_channel": submission_channel,
        "immutable_hash": immutable_hash,
        "source_trace": "RUNTIME_SUBMISSION",
    }
    r = sb.table("runtime_submission").insert(row).execute()

    # audit
    sb.table("runtime_submission_audit").insert({
        "submission_id": r.data[0]["id"],
        "audit_action": "SUBMISSION_CREATED",
        "audit_by": submitted_by,
        "source_trace": "RUNTIME_AUDIT",
    }).execute()

    _audit("CREATE_SUBMISSION", "submission", r.data[0]["id"], submitted_by)
    return {"status": "success", "source": "runtime", "data": r.data[0]}


@router.get("/submission-failures")
def bridge_list_failures(
    submission_id: Optional[str] = Query(None),
):
    sb = _sb()
    q = sb.table("runtime_submission_failure").select("*")
    if submission_id:
        q = q.eq("submission_id", submission_id)
    q = q.order("created_at", desc=True).limit(50)
    r = q.execute()
    return {"status": "success", "source": "runtime", "data": r.data or []}


@router.get("/resubmissions")
def bridge_list_resubmissions(
    submission_id: Optional[str] = Query(None),
):
    sb = _sb()
    q = sb.table("runtime_resubmission_request").select("*")
    if submission_id:
        q = q.eq("submission_id", submission_id)
    q = q.order("created_at", desc=True).limit(50)
    r = q.execute()
    return {"status": "success", "source": "runtime", "data": r.data or []}


@router.post("/retry-submission")
def bridge_retry_submission(
    submission_id: str = Query(...),
    requested_by: str = Query(...),
    resubmission_reason: str = Query(...),
):
    sb = _sb()
    sub = sb.table("runtime_submission").select("submission_status").eq("id", submission_id).execute()
    if not sub.data:
        raise HTTPException(404, "Submission not found")
    if sub.data[0]["submission_status"] not in ('FAILED', 'REJECTED', 'RESUBMISSION_REQUIRED'):
        raise HTTPException(400, f"Cannot retry: status is {sub.data[0]['submission_status']}")

    sb.table("runtime_resubmission_request").insert({
        "submission_id": submission_id,
        "requested_by": requested_by,
        "resubmission_reason": resubmission_reason,
        "source_trace": "MANUAL_REQUEST",
    }).execute()

    sb.table("runtime_submission").update({
        "submission_status": "READY",
    }).eq("id", submission_id).execute()

    _audit("RETRY_SUBMISSION", "submission", submission_id, requested_by)
    return {"status": "success", "retried": True}


@router.get("/submission-status")
def bridge_submission_status():
    return {
        "status": "active",
        "phase": "Phase 7 \u2014 Runtime Filing Governance",
        "bridge_routes": [
            "/bridge/submissions",
            "/bridge/submissions/{id}",
            "/bridge/filing-registry",
            "/bridge/submit-document",
            "/bridge/submission-failures",
            "/bridge/resubmissions",
            "/bridge/retry-submission",
        ],
    }
