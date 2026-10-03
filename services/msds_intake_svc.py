"""MSDS Document Intake Service — WO-MSDS-04B-IMPLEMENTATION-001."""
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
from services import msds_ocr_fact_parser as ocr_parser
from services.msds_ocr_provider import (
    OcrCredentialError, OcrProviderError, clova_available, run_clova_ocr_range,
)
from services.msds_vision_provider import VisionCredentialError, rasterize_pdf_page, run_vision_ocr

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
            "is_primary": True,
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
    Reset happens BEFORE PROCESSING so a reset failure leaves status RECEIVED/FAILED (retryable).
    """
    _require_factory_scope(sb, current_user, factory_id)

    intake = _get_intake(sb, factory_id, intake_id)
    if intake["status"] not in ("RECEIVED", "FAILED"):
        raise MsdsProductError(409, "INTAKE_ALREADY_PROCESSED", "이미 처리된 Intake입니다.")

    # Reset BEFORE PROCESSING — failure keeps status RECEIVED/FAILED so caller can retry
    try:
        _reset_process_data(sb, intake_id)
    except Exception:
        raise MsdsProductError(500, "PROCESS_RESET_FAILED", "이전 처리 데이터 초기화에 실패했습니다.")

    sb.table("msds_intakes").update({"status": "PROCESSING"}).eq("id", intake_id).execute()

    try:
        return _do_process(sb, current_user, factory_id, intake_id, intake)
    except MsdsProductError:
        # _do_process already called _fail_intake with the correct error_code
        # clean up partial writes; if cleanup itself fails, override to PROCESS_CLEANUP_FAILED
        try:
            _reset_process_data(sb, intake_id)
        except Exception:
            _fail_intake(sb, intake_id, "PROCESS_CLEANUP_FAILED", "처리 후 데이터 정리에 실패했습니다.")
            raise MsdsProductError(500, "PROCESS_CLEANUP_FAILED", "처리 후 정리 중 오류가 발생했습니다.")
        raise
    except Exception as e:
        try:
            _reset_process_data(sb, intake_id)
        except Exception:
            _fail_intake(sb, intake_id, "PROCESS_CLEANUP_FAILED", "처리 후 데이터 정리에 실패했습니다.")
            raise MsdsProductError(500, "PROCESS_CLEANUP_FAILED", "처리 후 정리 중 오류가 발생했습니다.")
        _fail_intake(sb, intake_id, "PROCESS_UNEXPECTED_FAILURE", str(e)[:500])
        raise MsdsProductError(500, "PROCESS_UNEXPECTED_FAILURE", "처리 중 예기치 않은 오류가 발생했습니다.")


def _do_process(sb, current_user, factory_id, intake_id, intake) -> Dict[str, Any]:
    """Inner process logic — any exception becomes FAILED via outer handler."""
    artifact = _get_primary_pdf_artifact(sb, intake_id)
    if artifact is None:
        _fail_intake(sb, intake_id, "NO_ARTIFACT", "Primary artifact 없음")
        raise MsdsProductError(500, "NO_ARTIFACT", "PDF artifact를 찾을 수 없습니다.")

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


def _get_primary_pdf_artifact(sb, intake_id: str) -> Optional[Dict]:
    """Return is_primary=True artifact, falling back to artifact_type='PDF' for legacy rows."""
    res = (
        sb.table("msds_intake_artifacts")
        .select("*")
        .eq("intake_id", intake_id)
        .eq("is_primary", True)
        .limit(1)
        .execute()
    )
    if res.data:
        return res.data[0]
    res = (
        sb.table("msds_intake_artifacts")
        .select("*")
        .eq("intake_id", intake_id)
        .eq("artifact_type", "PDF")
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


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
            created_source=intake.get("source_type", "PDF"),
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

    artifact = _get_primary_pdf_artifact(sb, intake_id)
    if artifact is None:
        raise MsdsProductError(500, "NO_ARTIFACT", "PDF artifact 없음")

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
        created_source=intake.get("source_type", "PDF"),
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


# ─── Photo Intake ──────────────────────────────────────────────────────────────

_PHOTO_MAX_COUNT = 20
_PHOTO_MAX_SINGLE_BYTES = 10 * 1024 * 1024   # 10 MiB
_PHOTO_MAX_TOTAL_BYTES = 100 * 1024 * 1024   # 100 MiB
_PHOTO_LONG_EDGE_MAX = 2560


def _normalize_photo(photo_bytes: bytes) -> bytes:
    """Apply EXIF orientation correction and resize so long-edge ≤ 2560. Returns JPEG bytes."""
    import io as _io
    try:
        from PIL import Image, ImageOps
    except ImportError as e:
        raise MsdsProductError(500, "PHOTO_PDF_BUILD_FAILED", f"Pillow 없음: {e}")
    img = Image.open(_io.BytesIO(photo_bytes))
    img = ImageOps.exif_transpose(img)
    w, h = img.size
    long_edge = max(w, h)
    if long_edge > _PHOTO_LONG_EDGE_MAX:
        scale = _PHOTO_LONG_EDGE_MAX / long_edge
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    if img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")
    buf = _io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def _build_derived_pdf(photo_records: List[Dict]) -> bytes:
    """Build a derived PDF from ordered JPEG photo records using reportlab canvas."""
    import io as _io
    try:
        from reportlab.pdfgen import canvas as rl_canvas
        from reportlab.lib.pagesizes import A4
        from PIL import Image
    except ImportError as e:
        raise MsdsProductError(500, "PHOTO_PDF_BUILD_FAILED", f"PDF 빌드 라이브러리 없음: {e}")

    page_w, page_h = A4
    pad = 4

    buf = _io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)

    for rec in sorted(photo_records, key=lambda r: r["sequence_no"]):
        img_path = rec["tmp_path"]
        try:
            img = Image.open(img_path)
            iw, ih = img.size
            scale = min((page_w - pad * 2) / iw, (page_h - pad * 2) / ih)
            draw_w = iw * scale
            draw_h = ih * scale
            x = (page_w - draw_w) / 2
            y = (page_h - draw_h) / 2
            c.drawImage(img_path, x, y, width=draw_w, height=draw_h, preserveAspectRatio=True)
            c.showPage()
        except Exception as e:
            raise MsdsProductError(500, "PHOTO_PDF_BUILD_FAILED", f"이미지 처리 실패 (seq={rec['sequence_no']}): {e}")

    c.save()
    return buf.getvalue()


def create_photo_intake(
    sb,
    current_user: Dict,
    factory_id: str,
    photos: List[Dict],
) -> Dict[str, Any]:
    """Create MSDS Intake from ordered JPEG/PNG photo set.

    photos: list of {"bytes": bytes, "file_name": str, "sequence_no": int, "mime_type": str}
    Each photo stored as PHOTO artifact (is_primary=False).
    Derived PDF stored as artifact_type='PDF' / is_primary=True / sequence_no=NULL.
    Returns intake dict.
    """
    import tempfile
    import os as _os

    _require_factory_scope(sb, current_user, factory_id)

    if not photos:
        raise MsdsProductError(422, "PHOTO_REQUIRED", "사진이 없습니다.")
    if len(photos) > _PHOTO_MAX_COUNT:
        raise MsdsProductError(422, "PHOTO_TOO_MANY", f"사진은 최대 {_PHOTO_MAX_COUNT}장까지 허용됩니다.")

    _JPEG_MAGIC = b"\xff\xd8"
    _PNG_MAGIC = b"\x89PNG"
    total_bytes = 0
    for p in photos:
        raw = p.get("bytes", b"")
        if len(raw) > _PHOTO_MAX_SINGLE_BYTES:
            raise MsdsProductError(
                422, "PHOTO_TOO_LARGE",
                f"사진 1장 최대 10MiB 초과: {p.get('file_name','')} ({len(raw)} bytes)"
            )
        total_bytes += len(raw)
        if not (raw.startswith(_JPEG_MAGIC) or raw.startswith(_PNG_MAGIC)):
            raise MsdsProductError(
                422, "INVALID_PHOTO_FORMAT",
                f"JPEG 또는 PNG 파일이 아닙니다: {p.get('file_name','')}"
            )
    if total_bytes > _PHOTO_MAX_TOTAL_BYTES:
        raise MsdsProductError(422, "PHOTO_TOTAL_TOO_LARGE", f"전체 사진 용량이 100MiB를 초과합니다.")

    company_id = _get_company_id(sb, factory_id)

    # Create intake row
    intake_res = sb.table("msds_intakes").insert({
        "factory_id": factory_id,
        "source_type": "PHOTO",
        "status": "RECEIVED",
        "reference_snapshot_id": _REFERENCE_SNAPSHOT_ID,
        "created_by": current_user.get("id"),
    }).execute()
    if not intake_res.data:
        raise MsdsProductError(500, "INTAKE_CREATE_FAILED", "Intake 생성에 실패했습니다.")
    intake = intake_res.data[0]
    intake_id = intake["id"]

    # Track which storage paths have been committed to DB (artifact row exists)
    # Only delete uncommitted paths on failure
    committed_paths: set = set()
    all_storage_paths: List[str] = []
    tmp_files: List[str] = []

    try:
        photo_records: List[Dict] = []
        for p in photos:
            normalized = _normalize_photo(p["bytes"])
            sha = _sha256(normalized)
            storage_path = _temp_storage_path(company_id, intake_id, "jpg")
            sb.storage.from_(_INTAKE_BUCKET).upload(
                path=storage_path,
                file=normalized,
                file_options={"content-type": "image/jpeg"},
            )
            all_storage_paths.append(storage_path)

            art_res = sb.table("msds_intake_artifacts").insert({
                "intake_id": intake_id,
                "artifact_type": "PHOTO",
                "bucket_id": _INTAKE_BUCKET,
                "storage_path": storage_path,
                "file_name": p.get("file_name", f"photo_{p['sequence_no']:03d}.jpg"),
                "mime_type": "image/jpeg",
                "file_size": len(normalized),
                "content_sha256": sha,
                "sequence_no": p["sequence_no"],
                "is_primary": False,
            }).execute()
            if not art_res.data:
                raise MsdsProductError(500, "ARTIFACT_CREATE_FAILED", "Photo artifact 생성 실패")
            committed_paths.add(storage_path)

            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                tmp.write(normalized)
                tmp_path = tmp.name
            tmp_files.append(tmp_path)
            photo_records.append({"sequence_no": p["sequence_no"], "tmp_path": tmp_path})

        # Build derived PDF
        pdf_bytes = _build_derived_pdf(photo_records)
        pdf_sha = _sha256(pdf_bytes)
        pdf_storage_path = _temp_storage_path(company_id, intake_id, "pdf")
        sb.storage.from_(_INTAKE_BUCKET).upload(
            path=pdf_storage_path,
            file=pdf_bytes,
            file_options={"content-type": "application/pdf"},
        )
        all_storage_paths.append(pdf_storage_path)

        pdf_art_res = sb.table("msds_intake_artifacts").insert({
            "intake_id": intake_id,
            "artifact_type": "PDF",
            "bucket_id": _INTAKE_BUCKET,
            "storage_path": pdf_storage_path,
            "file_name": f"derived_{intake_id[:8]}.pdf",
            "mime_type": "application/pdf",
            "file_size": len(pdf_bytes),
            "content_sha256": pdf_sha,
            "is_primary": True,
        }).execute()
        if not pdf_art_res.data:
            raise MsdsProductError(500, "ARTIFACT_CREATE_FAILED", "Derived PDF artifact 생성 실패")
        committed_paths.add(pdf_storage_path)

    except MsdsProductError:
        # Only remove storage objects without a committed artifact row
        for sp in all_storage_paths:
            if sp not in committed_paths:
                try:
                    sb.storage.from_(_INTAKE_BUCKET).remove([sp])
                except Exception:
                    pass
        sb.table("msds_intakes").update({
            "status": "FAILED",
            "error_code": "PHOTO_INTAKE_FAILED",
            "error_detail": "사진 처리 중 오류 발생",
        }).eq("id", intake_id).execute()
        raise
    finally:
        for tf in tmp_files:
            try:
                _os.unlink(tf)
            except Exception:
                pass

    return {"intake": intake, "photo_count": len(photos), "duplicate": False}


# ─── OCR Trigger ───────────────────────────────────────────────────────────────

def run_ocr(sb, current_user: Dict, factory_id: str, intake_id: str) -> Dict[str, Any]:
    """Run OCR on an OCR_REQUIRED intake.

    Flow:
      1. CLOVA pass1 (pages 1-5) → parse facts
      2. CLOVA pass2 (pages 6-10) if pass1 insufficient → merge facts
      3. Vision fallback (page 1 rasterized) if still insufficient
      4. Store facts → generate candidates → transition to REVIEW_REQUIRED

    Transitions: OCR_REQUIRED → PROCESSING → REVIEW_REQUIRED / FAILED
    """
    _require_factory_scope(sb, current_user, factory_id)

    intake = _get_intake(sb, factory_id, intake_id)
    if intake["status"] != "OCR_REQUIRED":
        raise MsdsProductError(409, "INTAKE_NOT_OCR_REQUIRED", "OCR 처리 가능한 상태가 아닙니다.")

    try:
        _reset_process_data(sb, intake_id)
    except Exception:
        raise MsdsProductError(500, "PROCESS_RESET_FAILED", "이전 처리 데이터 초기화 실패")

    sb.table("msds_intakes").update({"status": "PROCESSING"}).eq("id", intake_id).execute()

    try:
        return _do_ocr_process(sb, current_user, factory_id, intake_id, intake)
    except MsdsProductError:
        try:
            _reset_process_data(sb, intake_id)
        except Exception:
            _fail_intake(sb, intake_id, "PROCESS_CLEANUP_FAILED", "OCR 처리 후 데이터 정리 실패")
            raise MsdsProductError(500, "PROCESS_CLEANUP_FAILED", "OCR 처리 후 정리 오류")
        raise
    except Exception as e:
        try:
            _reset_process_data(sb, intake_id)
        except Exception:
            pass
        _fail_intake(sb, intake_id, "OCR_UNEXPECTED_FAILURE", str(e)[:500])
        raise MsdsProductError(500, "OCR_UNEXPECTED_FAILURE", "OCR 처리 중 예기치 않은 오류")


def _do_ocr_process(sb, current_user, factory_id, intake_id, intake) -> Dict[str, Any]:
    """Inner OCR logic. Exceptions propagate to outer handler."""
    import os as _os

    artifact = _get_primary_pdf_artifact(sb, intake_id)
    if artifact is None:
        _fail_intake(sb, intake_id, "NO_ARTIFACT", "Primary artifact 없음")
        raise MsdsProductError(500, "NO_ARTIFACT", "처리할 artifact를 찾을 수 없습니다.")

    try:
        pdf_bytes = sb.storage.from_(_INTAKE_BUCKET).download(artifact["storage_path"])
    except Exception as e:
        _fail_intake(sb, intake_id, "STORAGE_READ_FAILED", str(e))
        raise MsdsProductError(500, "STORAGE_READ_FAILED", "파일 읽기 실패")

    facts: List[Dict] = []
    ocr_method = "OCR"

    # CLOVA pass1/pass2 — credentials required
    if not clova_available():
        _fail_intake(sb, intake_id, "OCR_PROVIDER_NOT_CONFIGURED", "CLOVA 자격증명 없음")
        raise MsdsProductError(500, "OCR_PROVIDER_NOT_CONFIGURED", "CLOVA OCR 자격증명이 설정되지 않았습니다.")

    try:
        # Pass 1: pages 1-5 (0-indexed: [0, 5))
        p1 = run_clova_ocr_range(pdf_bytes, start_page=0, end_page=5)
        facts = ocr_parser.parse_ocr_facts(p1.full_text, extraction_method="OCR") if p1.full_text.strip() else []
        _add_provenance(facts, provider="CLOVA", request_id=p1.request_id)

        # Pass 2: pages 6-10 only when pass1 is insufficient
        if not ocr_parser.is_sufficient(facts):
            p2 = run_clova_ocr_range(pdf_bytes, start_page=5, end_page=10)
            if p2.full_text.strip():
                p2_facts = ocr_parser.parse_ocr_facts(p2.full_text, extraction_method="OCR")
                _add_provenance(p2_facts, provider="CLOVA", request_id=p2.request_id)
                existing_keys = {(f["fact_type"], f["normalized_value"]) for f in facts}
                for f in p2_facts:
                    key = (f["fact_type"], f["normalized_value"])
                    if key not in existing_keys:
                        facts.append(f)
                        existing_keys.add(key)

    except OcrCredentialError:
        _fail_intake(sb, intake_id, "OCR_PROVIDER_NOT_CONFIGURED", "CLOVA 자격증명 없음")
        raise MsdsProductError(500, "OCR_PROVIDER_NOT_CONFIGURED", "CLOVA OCR 자격증명이 설정되지 않았습니다.")
    except OcrProviderError as e:
        _fail_intake(sb, intake_id, "OCR_PROVIDER_FAILED", str(e)[:500])
        raise MsdsProductError(500, "OCR_PROVIDER_FAILED", f"CLOVA OCR 실패: {str(e)[:200]}")

    # Vision fallback if still insufficient
    if not ocr_parser.is_sufficient(facts):
        img_path = rasterize_pdf_page(pdf_bytes, page_no=1)
        if img_path:
            try:
                vision_result = run_vision_ocr(img_path)
                if not vision_result.error and vision_result.full_text.strip():
                    vision_facts = ocr_parser.parse_ocr_facts(
                        vision_result.full_text, extraction_method="VISION"
                    )
                    _add_provenance(vision_facts, provider="GPT_VISION")
                    existing_keys = {(f["fact_type"], f["normalized_value"]) for f in facts}
                    for vf in vision_facts:
                        key = (vf["fact_type"], vf["normalized_value"])
                        if key not in existing_keys:
                            facts.append(vf)
                            existing_keys.add(key)
                    ocr_method = "VISION"
            except VisionCredentialError:
                pass
            finally:
                try:
                    _os.unlink(img_path)
                except Exception:
                    pass

    if not facts:
        _fail_intake(sb, intake_id, "OCR_NO_FACTS", "OCR로 사실을 추출할 수 없습니다.")
        raise MsdsProductError(422, "OCR_NO_FACTS", "OCR로 사실을 추출할 수 없습니다.")

    # Reference lookup before any DB writes
    snapshot_id = intake.get("reference_snapshot_id") or _REFERENCE_SNAPSHOT_ID
    product_candidates = _find_product_candidates(sb, factory_id, facts)

    try:
        reference_candidates = _find_reference_candidates(facts, snapshot_id)
    except Exception as e:
        _fail_intake(sb, intake_id, "REFERENCE_LOOKUP_FAILED", str(e)[:500])
        raise MsdsProductError(500, "REFERENCE_LOOKUP_FAILED", "참조 DB 조회 실패")

    fact_rows = []
    for f in facts:
        fact_res = sb.table("msds_intake_facts").insert({
            "intake_id": intake_id,
            "fact_type": f["fact_type"],
            "raw_value": f["raw_value"],
            "normalized_value": f["normalized_value"],
            "extraction_method": f.get("extraction_method", ocr_method),
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
        "ocr_method": ocr_method,
    }


def _add_provenance(facts: List[Dict], provider: str, request_id: str = "") -> None:
    """Mutate facts in-place to add provider/request_id to evidence_json."""
    for f in facts:
        ev = f.setdefault("evidence_json", {})
        ev["provider"] = provider
        if request_id:
            ev["request_id"] = request_id
