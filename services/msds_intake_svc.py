"""MSDS Document Intake Service — WO-MSDS-04A-IMPLEMENTATION-001."""
from __future__ import annotations

import hashlib
import uuid
from typing import Any, Dict, List, Optional, Tuple

from services.document_svc import BUCKET
from services.msds_product_svc import (
    MsdsProductError,
    _require_factory_scope,
    normalize_identifier,
    normalize_manufacturer,
    normalize_product_name,
)
from services.msds_version_svc import validate_pdf, create_version
from services import msds_fact_extractor as extractor
from services import msds_reference_svc as ref_svc

# Fixed snapshot for OBJ-04A — WO-MSDS-04A-IMPLEMENTATION-001
_REFERENCE_SNAPSHOT_ID = "0ad73e46-d61b-474d-a90e-5b5ab8080d80"

_INTAKE_BUCKET = BUCKET  # reuse company-docs


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _temp_storage_path(company_id: str, intake_id: str, ext: str) -> str:
    file_uuid = str(uuid.uuid4())
    suffix = f".{ext}" if ext else ""
    return f"{company_id}/msds-intake/{intake_id}/{file_uuid}{suffix}"


def _get_company_id(sb, factory_id: str) -> str:
    res = sb.table("factories").select("company_id").eq("id", factory_id).limit(1).execute()
    if not res.data:
        raise MsdsProductError(404, "FACTORY_NOT_FOUND", "공장을 찾을 수 없습니다.")
    return res.data[0]["company_id"]


# ─── Create Intake ─────────────────────────────────────────────────────────────

def create_intake(
    sb,
    current_user: Dict,
    factory_id: str,
    file_bytes: bytes,
    file_name: str,
    mime_type: str,
) -> Dict[str, Any]:
    """Create a new MSDS Intake with temporary PDF artifact. Returns intake row."""
    _require_factory_scope(sb, current_user, factory_id)
    validate_pdf(file_bytes, file_name, mime_type)

    sha = _sha256(file_bytes)
    company_id = _get_company_id(sb, factory_id)

    # Check for duplicate SHA already FINALIZED in this factory
    dup = (
        sb.table("msds_intakes")
        .select("id,status,final_msds_version_id")
        .eq("factory_id", factory_id)
        .eq("status", "FINALIZED")
        .execute()
    )
    for row in (dup.data or []):
        # check artifact SHA
        art = (
            sb.table("msds_intake_artifacts")
            .select("content_sha256")
            .eq("intake_id", row["id"])
            .limit(1)
            .execute()
        )
        if art.data and art.data[0]["content_sha256"] == sha:
            return {"intake": row, "duplicate": True}

    # Create intake row
    intake_res = sb.table("msds_intakes").insert({
        "factory_id": factory_id,
        "source_type": "PDF",
        "status": "RECEIVED",
        "reference_snapshot_id": _REFERENCE_SNAPSHOT_ID,
        "created_by": current_user.get("id"),
    }).execute()
    if not intake_res.data:
        raise MsdsProductError(500, "INTAKE_CREATE_FAILED", "Intake 생성에 실패했습니다.")
    intake = intake_res.data[0]
    intake_id = intake["id"]

    # Upload temp PDF
    ext = "pdf"
    storage_path = _temp_storage_path(company_id, intake_id, ext)
    try:
        sb.storage.from_(_INTAKE_BUCKET).upload(
            path=storage_path,
            file=file_bytes,
            file_options={"content-type": mime_type},
        )
    except Exception as e:
        # Clean up intake row on upload failure
        sb.table("msds_intakes").update({"status": "FAILED", "error_code": "STORAGE_UPLOAD_FAILED", "error_detail": str(e)}).eq("id", intake_id).execute()
        raise MsdsProductError(500, "STORAGE_UPLOAD_FAILED", "파일 업로드에 실패했습니다.")

    # Create artifact row
    art_res = sb.table("msds_intake_artifacts").insert({
        "intake_id": intake_id,
        "artifact_type": "PDF",
        "bucket_id": _INTAKE_BUCKET,
        "storage_path": storage_path,
        "file_name": file_name,
        "mime_type": mime_type,
        "file_size": len(file_bytes),
        "content_sha256": sha,
    }).execute()
    if not art_res.data:
        # best-effort cleanup
        try:
            sb.storage.from_(_INTAKE_BUCKET).remove([storage_path])
        except Exception:
            pass
        raise MsdsProductError(500, "ARTIFACT_CREATE_FAILED", "Artifact 생성에 실패했습니다.")

    return {"intake": intake, "artifact": art_res.data[0], "duplicate": False}


# ─── Process Intake ────────────────────────────────────────────────────────────

def process_intake(sb, current_user: Dict, factory_id: str, intake_id: str) -> Dict[str, Any]:
    """Extract facts and generate candidates. Transitions: RECEIVED → PROCESSING → REVIEW_REQUIRED / OCR_REQUIRED / FAILED."""
    _require_factory_scope(sb, current_user, factory_id)

    intake = _get_intake(sb, factory_id, intake_id)
    if intake["status"] not in ("RECEIVED", "FAILED"):
        raise MsdsProductError(409, "INTAKE_ALREADY_PROCESSED", "이미 처리된 Intake입니다.")

    # Mark PROCESSING
    sb.table("msds_intakes").update({"status": "PROCESSING"}).eq("id", intake_id).execute()

    # Load artifact
    art_res = (
        sb.table("msds_intake_artifacts")
        .select("*")
        .eq("intake_id", intake_id)
        .eq("artifact_type", "PDF")
        .limit(1)
        .execute()
    )
    if not art_res.data:
        _fail_intake(sb, intake_id, "NO_ARTIFACT", "PDF artifact 없음")
        raise MsdsProductError(500, "NO_ARTIFACT", "PDF artifact를 찾을 수 없습니다.")

    artifact = art_res.data[0]

    # Download PDF bytes from storage
    try:
        pdf_bytes = sb.storage.from_(_INTAKE_BUCKET).download(artifact["storage_path"])
    except Exception as e:
        _fail_intake(sb, intake_id, "STORAGE_READ_FAILED", str(e))
        raise MsdsProductError(500, "STORAGE_READ_FAILED", "PDF 파일 읽기에 실패했습니다.")

    # Native extraction
    result = extractor.extract_facts(pdf_bytes)

    if result.error:
        _fail_intake(sb, intake_id, "EXTRACTION_FAILED", result.error)
        raise MsdsProductError(500, "EXTRACTION_FAILED", f"PDF 파싱 오류: {result.error}")

    # Update page_count on artifact
    if result.page_count:
        sb.table("msds_intake_artifacts").update({"page_count": result.page_count}).eq("id", artifact["id"]).execute()

    if result.ocr_required or not result.facts:
        sb.table("msds_intakes").update({"status": "OCR_REQUIRED", "processed_at": "now()"}).eq("id", intake_id).execute()
        return {"status": "OCR_REQUIRED", "facts": [], "product_candidates": [], "reference_candidates": []}

    # Store facts
    fact_rows = []
    for f in result.facts:
        fact_res = sb.table("msds_intake_facts").insert({
            "intake_id": intake_id,
            "fact_type": f["fact_type"],
            "raw_value": f["raw_value"],
            "normalized_value": f["normalized_value"],
            "extraction_method": "PDF_NATIVE",
            "source_artifact_id": artifact["id"],
            "source_page": f.get("source_page"),
            "evidence_json": f.get("evidence_json", {}),
        }).execute()
        if fact_res.data:
            fact_rows.append(fact_res.data[0])

    # Generate candidates
    snapshot_id = intake.get("reference_snapshot_id") or _REFERENCE_SNAPSHOT_ID
    product_candidates = _find_product_candidates(sb, factory_id, result.facts)
    reference_candidates = _find_reference_candidates(result.facts, snapshot_id)

    # Store candidates
    for c in product_candidates + reference_candidates:
        sb.table("msds_match_candidates").insert({
            "intake_id": intake_id,
            **c,
        }).execute()

    sb.table("msds_intakes").update({
        "status": "REVIEW_REQUIRED",
        "processed_at": "now()",
    }).eq("id", intake_id).execute()

    return {
        "status": "REVIEW_REQUIRED",
        "facts": fact_rows,
        "product_candidates": product_candidates,
        "reference_candidates": reference_candidates,
    }


def _find_product_candidates(sb, factory_id: str, facts: List[Dict]) -> List[Dict]:
    """Find matching chemical products in the same factory."""
    candidates = []
    seen_ids: set = set()

    cas_values = [f["normalized_value"] for f in facts if f["fact_type"] == "CAS"]
    product_names = [f["normalized_value"] for f in facts if f["fact_type"] == "PRODUCT_NAME"]
    mfr_names = [f["normalized_value"] for f in facts if f["fact_type"] == "MANUFACTURER_NAME"]

    # EXACT_IDENTIFIER: CAS as BARCODE or other identifier type
    for cas in cas_values:
        res = (
            sb.table("chemical_product_identifiers")
            .select("chemical_product_id")
            .eq("factory_id", factory_id)
            .eq("identifier_normalized", cas)
            .eq("is_active", True)
            .execute()
        )
        for row in (res.data or []):
            pid = row["chemical_product_id"]
            if pid not in seen_ids:
                seen_ids.add(pid)
                candidates.append({
                    "candidate_type": "CUSTOMER_PRODUCT",
                    "candidate_product_id": pid,
                    "match_reason": "EXACT_IDENTIFIER",
                    "rank_no": 1,
                    "evidence_json": {"identifier_normalized": cas},
                })

    # EXACT_NAME_MANUFACTURER / EXACT_NAME
    for pname in product_names:
        for mname in (mfr_names or [None]):
            query = (
                sb.table("chemical_products")
                .select("id")
                .eq("factory_id", factory_id)
                .eq("product_name_normalized", pname)
                .eq("status_code", "ACTIVE")
            )
            if mname:
                query = query.eq("manufacturer_normalized", mname)
            res = query.execute()
            for row in (res.data or []):
                pid = row["id"]
                if pid not in seen_ids:
                    seen_ids.add(pid)
                    reason = "EXACT_NAME_MANUFACTURER" if mname else "EXACT_NAME"
                    candidates.append({
                        "candidate_type": "CUSTOMER_PRODUCT",
                        "candidate_product_id": pid,
                        "match_reason": reason,
                        "rank_no": 2 if mname else 3,
                        "evidence_json": {"product_name_normalized": pname, "manufacturer_normalized": mname},
                    })

    return candidates


def _find_reference_candidates(facts: List[Dict], snapshot_id: str) -> List[Dict]:
    """Find KOSHA reference candidates."""
    cas_list = [f["normalized_value"] for f in facts if f["fact_type"] == "CAS"]
    product_names = [f["normalized_value"] for f in facts if f["fact_type"] == "PRODUCT_NAME"]
    pname = product_names[0] if product_names else None

    try:
        ref_hits = ref_svc.find_reference_candidates(
            snapshot_id=snapshot_id,
            cas_list=cas_list,
            product_name_normalized=pname,
            substance_name_normalized=pname,  # same field for v1
            alias_normalized=pname,
        )
    except Exception:
        return []  # reference lookup failure is non-fatal; human can still confirm

    return [
        {
            "candidate_type": "REFERENCE",
            "reference_content_id": r["reference_content_id"],
            "reference_chem_id": r["reference_chem_id"],
            "reference_snapshot_id": r["reference_snapshot_id"],
            "match_reason": r["match_reason"],
            "rank_no": r["rank_no"],
            "evidence_json": r.get("evidence_json", {}),
        }
        for r in ref_hits
    ]


def _get_intake(sb, factory_id: str, intake_id: str) -> Dict:
    res = (
        sb.table("msds_intakes")
        .select("*")
        .eq("id", intake_id)
        .eq("factory_id", factory_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise MsdsProductError(404, "INTAKE_NOT_FOUND", "Intake를 찾을 수 없습니다.")
    return res.data[0]


def _fail_intake(sb, intake_id: str, error_code: str, error_detail: str):
    sb.table("msds_intakes").update({
        "status": "FAILED",
        "error_code": error_code,
        "error_detail": error_detail[:500],
    }).eq("id", intake_id).execute()


# ─── Get Intake ────────────────────────────────────────────────────────────────

def get_intake(sb, current_user: Dict, factory_id: str, intake_id: str) -> Dict:
    _require_factory_scope(sb, current_user, factory_id)
    return _get_intake(sb, factory_id, intake_id)


# ─── List Facts ────────────────────────────────────────────────────────────────

def list_facts(sb, current_user: Dict, factory_id: str, intake_id: str) -> List[Dict]:
    _require_factory_scope(sb, current_user, factory_id)
    _get_intake(sb, factory_id, intake_id)
    res = sb.table("msds_intake_facts").select("*").eq("intake_id", intake_id).execute()
    return res.data or []


# ─── List Candidates ──────────────────────────────────────────────────────────

def list_candidates(sb, current_user: Dict, factory_id: str, intake_id: str) -> Dict:
    _require_factory_scope(sb, current_user, factory_id)
    _get_intake(sb, factory_id, intake_id)
    res = sb.table("msds_match_candidates").select("*").eq("intake_id", intake_id).order("rank_no").execute()
    rows = res.data or []
    product = [r for r in rows if r["candidate_type"] == "CUSTOMER_PRODUCT"]
    reference = [r for r in rows if r["candidate_type"] == "REFERENCE"]
    return {"product_candidates": product, "reference_candidates": reference}


# ─── Confirm ──────────────────────────────────────────────────────────────────

def confirm_intake(
    sb,
    current_user: Dict,
    factory_id: str,
    intake_id: str,
    existing_product_id: Optional[str],
    new_product: Optional[Dict],
    selected_reference_candidate_ids: List[str],
) -> Dict:
    """Human confirmation: select product + reference candidates → CONFIRMED."""
    _require_factory_scope(sb, current_user, factory_id)
    intake = _get_intake(sb, factory_id, intake_id)

    if intake["status"] not in ("REVIEW_REQUIRED", "CONFIRMED"):
        raise MsdsProductError(409, "INTAKE_NOT_REVIEW_REQUIRED", "확인 가능한 상태가 아닙니다.")

    if existing_product_id and new_product:
        raise MsdsProductError(422, "CONFIRM_PRODUCT_CONFLICT", "기존 Product 선택과 신규 Product 생성을 동시에 할 수 없습니다.")

    if not existing_product_id and not new_product:
        raise MsdsProductError(422, "CONFIRM_NO_PRODUCT", "Product를 선택하거나 신규 생성 정보를 제공해야 합니다.")

    # Validate existing product belongs to factory
    if existing_product_id:
        prod_res = sb.table("chemical_products").select("id").eq("id", existing_product_id).eq("factory_id", factory_id).limit(1).execute()
        if not prod_res.data:
            raise MsdsProductError(404, "PRODUCT_NOT_FOUND", "선택한 Product를 찾을 수 없습니다.")

    # Mark selected reference candidates
    for cid in selected_reference_candidate_ids:
        sb.table("msds_match_candidates").update({
            "decision_status": "SELECTED",
            "decided_by": current_user.get("id"),
            "decided_at": "now()",
        }).eq("id", cid).eq("intake_id", intake_id).execute()

    # Store confirmation
    sb.table("msds_intakes").update({
        "status": "CONFIRMED",
        "selected_product_id": existing_product_id,
        "confirmed_at": "now()",
        "updated_at": "now()",
    }).eq("id", intake_id).execute()

    return {
        "status": "CONFIRMED",
        "existing_product_id": existing_product_id,
        "new_product": new_product,
        "selected_reference_candidate_ids": selected_reference_candidate_ids,
    }


# ─── Finalize ─────────────────────────────────────────────────────────────────

async def finalize_intake(
    sb,
    current_user: Dict,
    factory_id: str,
    intake_id: str,
    source_revision_date: Optional[str] = None,
    source_revision_no: Optional[str] = None,
    supplier_name: Optional[str] = None,
) -> Dict:
    """Finalize: use confirmed Product → create MSDS Version → create Reference Links → cleanup temp."""
    _require_factory_scope(sb, current_user, factory_id)
    intake = _get_intake(sb, factory_id, intake_id)

    if intake["status"] not in ("CONFIRMED", "FINALIZED"):
        raise MsdsProductError(409, "INTAKE_NOT_CONFIRMED", "확인된 Intake만 완료할 수 있습니다.")

    if intake["status"] == "FINALIZED":
        return {"status": "ALREADY_FINALIZED", "intake": intake}

    selected_product_id = intake.get("selected_product_id")
    if not selected_product_id:
        raise MsdsProductError(409, "NO_PRODUCT_SELECTED", "Confirm 단계에서 Product가 선택되지 않았습니다.")

    # Get artifact
    art_res = sb.table("msds_intake_artifacts").select("*").eq("intake_id", intake_id).eq("artifact_type", "PDF").limit(1).execute()
    if not art_res.data:
        raise MsdsProductError(500, "NO_ARTIFACT", "PDF artifact 없음")
    artifact = art_res.data[0]

    # Download PDF
    try:
        pdf_bytes = sb.storage.from_(_INTAKE_BUCKET).download(artifact["storage_path"])
    except Exception as e:
        raise MsdsProductError(500, "STORAGE_READ_FAILED", str(e))

    # Create MSDS Version via OBJ-MSDS-03
    version, rpc_status = await create_version(
        sb=sb,
        current_user=current_user,
        factory_id=factory_id,
        product_id=selected_product_id,
        file_bytes=pdf_bytes,
        file_name=artifact["file_name"],
        mime_type=artifact["mime_type"],
        source_revision_date=source_revision_date,
        source_revision_no=source_revision_no,
        supplier_name=supplier_name,
    )
    version_id = version["id"]

    # Create Reference Links
    selected_candidates_res = (
        sb.table("msds_match_candidates")
        .select("*")
        .eq("intake_id", intake_id)
        .eq("candidate_type", "REFERENCE")
        .eq("decision_status", "SELECTED")
        .execute()
    )
    snapshot_id = intake.get("reference_snapshot_id") or _REFERENCE_SNAPSHOT_ID

    for cand in (selected_candidates_res.data or []):
        content_id = cand.get("reference_content_id")
        if not content_id:
            continue
        # Fail-closed verification
        if not ref_svc.verify_reference_exists(snapshot_id, content_id):
            continue
        # Upsert reference link
        sb.table("msds_reference_links").upsert({
            "customer_msds_version_id": version_id,
            "reference_content_id": content_id,
            "reference_chem_id": cand.get("reference_chem_id", ""),
            "reference_snapshot_id": snapshot_id,
            "cas_no": cand.get("evidence_json", {}).get("cas"),
            "match_reason": cand["match_reason"],
            "confirmed_by": current_user.get("id"),
        }, on_conflict="customer_msds_version_id,reference_content_id").execute()

    # Update intake
    sb.table("msds_intakes").update({
        "status": "FINALIZED",
        "final_msds_version_id": version_id,
        "finalized_at": "now()",
        "updated_at": "now()",
    }).eq("id", intake_id).execute()

    # Cleanup temp artifact (only after successful finalization)
    try:
        sb.storage.from_(_INTAKE_BUCKET).remove([artifact["storage_path"]])
    except Exception:
        pass  # best-effort; do not fail finalization on cleanup error

    return {"status": "FINALIZED", "version_id": version_id, "rpc_status": rpc_status}
