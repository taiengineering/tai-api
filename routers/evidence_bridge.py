"""TAI Compliance Evidence Runtime Bridge v1.0.0
Phase 6: Operational Evidence → Immutable Compliance Asset.

금지: orphan evidence, fake upload, inferred evidence,
      mutable legal evidence, silent replacement, approval bypass
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import hashlib, logging

router = APIRouter(prefix="/bridge", tags=["증빙 브릿지"])
logger = logging.getLogger("evidence_bridge")


def _audit(action, entity, entity_id, user_id="system"):
    logger.info(f"EVIDENCE_BRIDGE_AUDIT | action={action} entity={entity} id={entity_id} by={user_id}")


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


@router.get("/compliance-evidence")
def bridge_list_evidence(
    evidence_type: Optional[str] = Query(None),
    evidence_status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    sb = _sb()
    q = sb.table("runtime_compliance_evidence").select("*")
    if evidence_type:
        q = q.eq("evidence_type", evidence_type)
    if evidence_status:
        q = q.eq("evidence_status", evidence_status)
    offset = (page - 1) * page_size
    q = q.order("created_at", desc=True).range(offset, offset + page_size - 1)
    r = q.execute()
    return {"status": "success", "source": "runtime", "data": r.data or [], "page": page}


@router.post("/upload-evidence")
def bridge_upload_evidence(
    evidence_type: str = Query(...),
    source_domain: str = Query(...),
    source_entity_id: str = Query(...),
    uploaded_by: str = Query(...),
    file_name: Optional[str] = Query(None),
):
    valid_types = ['PHOTO','SIGNATURE','REPORT','CERTIFICATE','INSPECTION_RESULT','TRAINING_RECORD','MEASUREMENT','DOCUMENT_ATTACHMENT']
    if evidence_type not in valid_types:
        raise HTTPException(400, f"Invalid evidence_type: {valid_types}")

    sb = _sb()
    # immutable hash
    hash_input = f"{source_entity_id}:{evidence_type}:{uploaded_by}:{file_name}"
    immutable_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:32]

    # duplicate check
    existing = sb.table("runtime_compliance_evidence").select("id").eq("immutable_hash", immutable_hash).execute()
    if existing.data:
        raise HTTPException(409, f"Duplicate evidence: hash={immutable_hash}")

    row = {
        "evidence_type": evidence_type,
        "source_domain": source_domain,
        "source_entity_id": source_entity_id,
        "uploaded_by": uploaded_by,
        "immutable_hash": immutable_hash,
        "source_trace": "WORKER_UPLOAD",
    }
    r = sb.table("runtime_compliance_evidence").insert(row).execute()
    _audit("UPLOAD", "compliance_evidence", r.data[0]["id"], uploaded_by)
    return {"status": "success", "source": "runtime", "data": r.data[0]}


@router.get("/evidence-trace")
def bridge_list_traces(
    compliance_evidence_id: Optional[str] = Query(None),
    obligation_id: Optional[str] = Query(None),
):
    sb = _sb()
    q = sb.table("runtime_evidence_trace").select("*")
    if compliance_evidence_id:
        q = q.eq("compliance_evidence_id", compliance_evidence_id)
    if obligation_id:
        q = q.eq("obligation_id", obligation_id)
    q = q.order("created_at", desc=True).limit(50)
    r = q.execute()
    return {"status": "success", "source": "runtime", "data": r.data or []}


@router.post("/verify-evidence")
def bridge_verify_evidence(
    compliance_evidence_id: str = Query(...),
    verifier_id: str = Query(...),
    verification_result: str = Query(...),
    verification_reason: Optional[str] = Query(None),
):
    if verification_result not in ('VERIFIED', 'REJECTED', 'NEEDS_REUPLOAD'):
        raise HTTPException(400, "Invalid verification_result")

    sb = _sb()
    ev = sb.table("runtime_compliance_evidence").select("evidence_status").eq("id", compliance_evidence_id).execute()
    if not ev.data:
        raise HTTPException(404, "Evidence not found")

    sb.table("runtime_evidence_verification").insert({
        "compliance_evidence_id": compliance_evidence_id,
        "verifier_id": verifier_id,
        "verification_result": verification_result,
        "verification_reason": verification_reason,
        "source_trace": "MANUAL_VERIFICATION",
    }).execute()

    new_status = {'VERIFIED': 'VERIFIED', 'REJECTED': 'REJECTED', 'NEEDS_REUPLOAD': 'UPLOADED'}[verification_result]
    sb.table("runtime_compliance_evidence").update({
        "evidence_status": new_status,
    }).eq("id", compliance_evidence_id).execute()

    _audit(f"VERIFY_{verification_result}", "compliance_evidence", compliance_evidence_id, verifier_id)
    return {"status": "success", "verified": True}


@router.get("/evidence-verification")
def bridge_list_verifications(
    compliance_evidence_id: Optional[str] = Query(None),
):
    sb = _sb()
    q = sb.table("runtime_evidence_verification").select("*")
    if compliance_evidence_id:
        q = q.eq("compliance_evidence_id", compliance_evidence_id)
    q = q.order("created_at", desc=True).limit(50)
    r = q.execute()
    return {"status": "success", "source": "runtime", "data": r.data or []}


@router.get("/evidence-retention")
def bridge_list_retention():
    sb = _sb()
    r = sb.table("runtime_evidence_retention_policy").select("*").order("evidence_type").execute()
    return {"status": "success", "source": "runtime", "data": r.data or []}


@router.get("/evidence-snapshots")
def bridge_list_snapshots(
    compliance_evidence_id: Optional[str] = Query(None),
):
    sb = _sb()
    q = sb.table("runtime_evidence_snapshot").select("*")
    if compliance_evidence_id:
        q = q.eq("compliance_evidence_id", compliance_evidence_id)
    q = q.order("created_at", desc=True).limit(50)
    r = q.execute()
    return {"status": "success", "source": "runtime", "data": r.data or []}


@router.get("/evidence-status")
def bridge_evidence_status():
    return {
        "status": "active",
        "phase": "Phase 6 \u2014 Runtime Compliance Evidence",
        "bridge_routes": [
            "/bridge/compliance-evidence",
            "/bridge/upload-evidence",
            "/bridge/evidence-trace",
            "/bridge/verify-evidence",
            "/bridge/evidence-verification",
            "/bridge/evidence-retention",
            "/bridge/evidence-snapshots",
        ],
    }
