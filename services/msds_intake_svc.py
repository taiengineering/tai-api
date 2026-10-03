"""MSDS Document Intake Service — WO-MSDS-04A-PATCH-003."""
from __future__ import annotations

import hashlib
import uuid
from typing import Any, Dict, List, Optional, Tuple

from services.document_svc import BUCKET
from services.msds_product_svc import (
    MsdsProductError,
    _require_factory_scope,
    create_product,
    normalize_identifier,
    normalize_manufacturer,
    normalize_product_name,
    update_product,
)
from services.msds_version_svc import validate_pdf, create_version
from services import msds_fact_extractor as extractor
from services import msds_reference_svc as ref_svc

# Fixed snapshot for OBJ-04A — WO-MSDS-04A-IMPLEMENTATION-001
_REFERENCE_SNAPSHOT_ID = "0ad73e46-d61b-474d-a90e-5b5ab8080d80"

_INTAKE_BUCKET = BUCKET  # reuse company-docs

# Identifier types valid for EXACT_IDENTIFIER product candidate matching (OBJ-04C)
_TYPED_IDENTIFIER_TYPES = {"GTIN", "EAN", "UPC", "BARCODE", "QR_ALIAS"}


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
    storage_path = _temp_storage_path(company_id, intake_id, "pdf")
    try:
        sb.storage.from_(_INTAKE_BUCKET).upload(
            path=storage_path,
            file=file_bytes,
            file_options={"content-type": mime_type},
        )
    except Exception as e:
        sb.table("msds_intakes").update({
            "status": "FAILED",
            "error_code": "STORAGE_UPLOAD_FAILED",
            "error_detail": str(e)[:500],
        }).eq("id", intake_id).execute()
        raise MsdsProductError(500, "STORAGE_UPLOAD_FAILED", "파일 업로드에 실패했습니다.")

    # Create artifact row — storage orphan compensation on failure
    try:
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
    except Exception as e:
        try:
            sb.storage.from_(_INTAKE_BUCKET).remove([storage_path])
        except Exception:
            pass
        sb.table("msds_intakes").update({
            "status": "FAILED",
            "error_code": "ARTIFACT_CREATE_FAILED",
            "error_detail": str(e)[:500],
        }).eq("id", intake_id).execute()
        raise MsdsProductError(500, "ARTIFACT_CREATE_FAILED", "Artifact 생성에 실패했습니다.")

    if not art_res.data:
        try:
            sb.storage.from_(_INTAKE_BUCKET).remove([storage_path])
        except Exception:
            pass
        sb.table("msds_intakes").update({
            "status": "FAILED",
            "error_code": "ARTIFACT_CREATE_FAILED",
            "error_detail": "INSERT returned no data",
        }).eq("id", intake_id).execute()
        raise MsdsProductError(500, "ARTIFACT_CREATE_FAILED", "Artifact 생성에 실패했습니다.")

    return {"intake": intake, "artifact": art_res.data[0], "duplicate": False}


# ─── Process Intake ────────────────────────────────────────────────────────────

def process_intake(sb, current_user: Dict, factory_id: str, intake_id: str) -> Dict[str, Any]:
    """Extract facts and generate candidates.

    Transitions: RECEIVED → PROCESSING → REVIEW_REQUIRED / OCR_REQUIRED / FAILED.
    Reference lookup failure → FAILED (REFERENCE_LOOKUP_FAILED).
    """
    _require_factory_scope(sb, current_user, factory_id)

    intake = _get_intake(sb, factory_id, intake_id)
    if intake["status"] not in ("RECEIVED", "FAILED"):
        raise MsdsProductError(409, "INTAKE_ALREADY_PROCESSED", "이미 처리된 Intake입니다.")

    # Mark PROCESSING
    sb.table("msds_intakes").update({"status": "PROCESSING"}).eq("id", intake_id).execute()

    # Remove stale transient data from any previous failed attempt before this one starts
    _reset_process_data(sb, intake_id)

    try:
        return _do_process(sb, current_user, factory_id, intake_id, intake)
    except MsdsProductError:
        _reset_process_data(sb, intake_id)  # clean up any partial writes from this attempt
        raise
    except Exception as e:
        _reset_process_data(sb, intake_id)
        _fail_intake(sb, intake_id, "PROCESS_UNEXPECTED_FAILURE", str(e)[:500])
        raise MsdsProductError(500, "PROCESS_UNEXPECTED_FAILURE", "처리 중 예기치 않은 오류가 발생했습니다.")


def _do_process(sb, current_user, factory_id, intake_id, intake) -> Dict[str, Any]:
    """Inner process logic — any exception becomes FAILED via outer handler."""
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

    if result.page_count:
        sb.table("msds_intake_artifacts").update({"page_count": result.page_count}).eq("id", artifact["id"]).execute()

    if result.ocr_required or not result.facts:
        sb.table("msds_intakes").update({"status": "OCR_REQUIRED", "processed_at": "now()"}).eq("id", intake_id).execute()
        return {"status": "OCR_REQUIRED", "facts": [], "product_candidates": [], "reference_candidates": []}

    # Compute candidates in memory — all DB writes come AFTER reference lookup succeeds
    snapshot_id = intake.get("reference_snapshot_id") or _REFERENCE_SNAPSHOT_ID
    product_candidates = _find_product_candidates(sb, factory_id, result.facts)

    # Reference lookup — failure → FAILED (no facts/candidates in DB yet)
    try:
        reference_candidates = _find_reference_candidates(result.facts, snapshot_id)
    except Exception as e:
        _fail_intake(sb, intake_id, "REFERENCE_LOOKUP_FAILED", str(e)[:500])
        raise MsdsProductError(500, "REFERENCE_LOOKUP_FAILED", "참조 DB 조회에 실패했습니다.")

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

    for c in product_candidates + reference_candidates:
        sb.table("msds_match_candidates").insert({"intake_id": intake_id, **c}).execute()

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


def _reset_process_data(sb, intake_id: str):
    sb.table("msds_match_candidates").delete().eq("intake_id", intake_id).execute()
    sb.table("msds_intake_facts").delete().eq("intake_id", intake_id).execute()


def _find_product_candidates(sb, factory_id: str, facts: List[Dict]) -> List[Dict]:
    """Find matching chemical products in the same factory.

    CAS is NOT a product identifier — it is for Reference matching only.
    EXACT_IDENTIFIER requires a typed identifier (GTIN/EAN/UPC/BARCODE/QR_ALIAS)
    that matches both identifier_normalized AND identifier_type.
    """
    candidates = []
    seen_ids: set = set()

    # EXACT_IDENTIFIER: typed identifiers only (not CAS)
    for f in facts:
        if f["fact_type"] not in _TYPED_IDENTIFIER_TYPES:
            continue
        res = (
            sb.table("chemical_product_identifiers")
            .select("chemical_product_id")
            .eq("factory_id", factory_id)
            .eq("identifier_type", f["fact_type"])
            .eq("identifier_normalized", f["normalized_value"])
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
                    "evidence_json": {"identifier_type": f["fact_type"], "identifier_normalized": f["normalized_value"]},
                })

    # EXACT_NAME_MANUFACTURER / EXACT_NAME
    product_names = [f["normalized_value"] for f in facts if f["fact_type"] == "PRODUCT_NAME"]
    mfr_names = [f["normalized_value"] for f in facts if f["fact_type"] == "MANUFACTURER_NAME"]

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
    """Find KOSHA reference candidates. Exceptions propagate to caller."""
    cas_list = [f["normalized_value"] for f in facts if f["fact_type"] == "CAS"]
    product_names = [f["normalized_value"] for f in facts if f["fact_type"] == "PRODUCT_NAME"]
    pname = product_names[0] if product_names else None

    ref_hits = ref_svc.find_reference_candidates(
        snapshot_id=snapshot_id,
        cas_list=cas_list,
        product_name_normalized=pname,
        substance_name_normalized=pname,
        alias_normalized=pname,
    )

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
    """Human confirmation: select product + reference candidates → CONFIRMED.

    Validates ALL reference candidates before any product side effects.
    Idempotent: CONFIRMED + selected_product_id already set → NO_CHANGE.
    """
    _require_factory_scope(sb, current_user, factory_id)
    intake = _get_intake(sb, factory_id, intake_id)

    if intake["status"] not in ("REVIEW_REQUIRED", "CONFIRMED"):
        raise MsdsProductError(409, "INTAKE_NOT_REVIEW_REQUIRED", "확인 가능한 상태가 아닙니다.")

    # Idempotent: already confirmed with a product selected → no-op
    if intake["status"] == "CONFIRMED" and intake.get("selected_product_id"):
        return {
            "status": "CONFIRMED",
            "selected_product_id": intake["selected_product_id"],
            "existing_product_id": None,
            "new_product_created": None,
            "no_change": True,
        }

    if existing_product_id and new_product:
        raise MsdsProductError(422, "CONFIRM_PRODUCT_CONFLICT", "기존 Product 선택과 신규 Product 생성을 동시에 할 수 없습니다.")

    if not existing_product_id and not new_product:
        raise MsdsProductError(422, "CONFIRM_NO_PRODUCT", "Product를 선택하거나 신규 생성 정보를 제공해야 합니다.")

    # Validate ALL selected reference candidates BEFORE any product side effects
    for cid in selected_reference_candidate_ids:
        cand_res = (
            sb.table("msds_match_candidates")
            .select("id,candidate_type,decision_status")
            .eq("id", cid)
            .eq("intake_id", intake_id)
            .limit(1)
            .execute()
        )
        if not cand_res.data:
            raise MsdsProductError(422, "REFERENCE_CANDIDATE_INVALID", f"candidate {cid}를 찾을 수 없습니다.")
        cand = cand_res.data[0]
        if cand.get("candidate_type") != "REFERENCE":
            raise MsdsProductError(422, "REFERENCE_CANDIDATE_INVALID", f"candidate {cid}는 REFERENCE 타입이 아닙니다.")
        if cand.get("decision_status") != "PENDING":
            raise MsdsProductError(422, "REFERENCE_CANDIDATE_INVALID", f"candidate {cid}는 이미 처리되었습니다.")

    # All validation passed — now safe to create/select product
    if existing_product_id:
        prod_res = (
            sb.table("chemical_products")
            .select("id")
            .eq("id", existing_product_id)
            .eq("factory_id", factory_id)
            .limit(1)
            .execute()
        )
        if not prod_res.data:
            raise MsdsProductError(404, "PRODUCT_NOT_FOUND", "선택한 Product를 찾을 수 없습니다.")
        selected_product_id = existing_product_id

    else:
        # Create new product via OBJ-02 contract
        product_name = new_product.get("product_name", "").strip()
        if not product_name:
            raise MsdsProductError(422, "NEW_PRODUCT_NAME_REQUIRED", "신규 Product 이름이 필요합니다.")
        manufacturer_name = new_product.get("manufacturer_name")

        new_prod_row, _ = create_product(
            sb=sb,
            current_user=current_user,
            factory_id=factory_id,
            product_name=product_name,
            manufacturer_name=manufacturer_name,
            identifiers=None,
            created_source="PDF",
        )
        # Set identity_status = CONFIRMED
        update_product(
            sb=sb,
            current_user=current_user,
            factory_id=factory_id,
            product_id=new_prod_row["id"],
            patch={"identity_status": "CONFIRMED"},
        )
        selected_product_id = new_prod_row["id"]

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
        "selected_product_id": selected_product_id,
        "confirmed_at": "now()",
        "updated_at": "now()",
    }).eq("id", intake_id).execute()

    return {
        "status": "CONFIRMED",
        "selected_product_id": selected_product_id,
        "existing_product_id": existing_product_id,
        "new_product_created": selected_product_id if not existing_product_id else None,
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
    """Finalize: confirmed Product → create MSDS Version → verify + create Reference Links → cleanup temp.

    Pre-finalize: all selected reference candidates are verified against leg-prod.
    Any verification failure → REFERENCE_VERIFY_FAILED (no version created, temp preserved).
    """
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
    art_res = (
        sb.table("msds_intake_artifacts")
        .select("*")
        .eq("intake_id", intake_id)
        .eq("artifact_type", "PDF")
        .limit(1)
        .execute()
    )
    if not art_res.data:
        raise MsdsProductError(500, "NO_ARTIFACT", "PDF artifact 없음")
    artifact = art_res.data[0]

    # Get selected reference candidates
    selected_candidates_res = (
        sb.table("msds_match_candidates")
        .select("*")
        .eq("intake_id", intake_id)
        .eq("candidate_type", "REFERENCE")
        .eq("decision_status", "SELECTED")
        .execute()
    )
    selected_candidates = selected_candidates_res.data or []

    # Pre-finalize: verify all selected references exist in leg-prod (fail-closed)
    snapshot_id = intake.get("reference_snapshot_id") or _REFERENCE_SNAPSHOT_ID
    for cand in selected_candidates:
        content_id = cand.get("reference_content_id")
        if not content_id:
            raise MsdsProductError(422, "REFERENCE_CANDIDATE_INVALID", "reference_content_id가 없습니다.")
        try:
            exists = ref_svc.verify_reference_exists(snapshot_id, content_id)
        except Exception as e:
            raise MsdsProductError(500, "REFERENCE_VERIFY_FAILED", f"참조 검증 실패 (leg-prod): {str(e)[:200]}")
        if not exists:
            raise MsdsProductError(422, "REFERENCE_VERIFY_FAILED",
                                   f"reference {content_id}가 snapshot {snapshot_id}에 존재하지 않습니다.")

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

    # Create Reference Links (all pre-verified above)
    for cand in selected_candidates:
        content_id = cand.get("reference_content_id")
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

    # Cleanup temp artifact (only after successful finalization, best-effort)
    try:
        sb.storage.from_(_INTAKE_BUCKET).remove([artifact["storage_path"]])
    except Exception:
        pass

    return {"status": "FINALIZED", "version_id": version_id, "rpc_status": rpc_status}
