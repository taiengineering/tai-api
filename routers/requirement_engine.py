"""TAI Document Completeness Engine v1.0.0
Deterministic requirement completeness evaluator.

역할: 현재 데이터 상태 → requirement completeness 평가
절대 금지: inferred/guessed/semantic/AI requirement 판단
"""
from fastapi import APIRouter, HTTPException, Query
import logging

router = APIRouter(prefix="/requirement", tags=["요구사항 평가"])
logger = logging.getLogger("requirement_engine")


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


@router.get("/document-completeness")
def evaluate_document_completeness(
    factory_id: str = Query(...),
    form_code: str = Query(...),
):
    """deterministic: 문서 생성 가능 여부 평가"""
    sb = _sb()

    # 1. obligation_form_mapping에서 form 확인
    ofm = sb.table("obligation_form_mapping").select("*").eq("form_code", form_code).execute()
    if not ofm.data:
        raise HTTPException(404, f"Form not found: {form_code}")

    form = ofm.data[0]
    missing = []

    # 2. factory 존재 확인
    fac = sb.table("factories").select("id, company_id, factory_name").eq("id", factory_id).execute()
    if not fac.data:
        missing.append({"field": "factory", "reason": "사업장 정보 없음"})

    # 3. field_rule_mapping 기반 필수필드 확인
    frm = sb.table("field_rule_mapping").select("field_code, field_name, is_required").limit(50).execute()
    required_fields = [f for f in (frm.data or []) if f.get("is_required")]

    # 4. doc_rule_mapping 기반 문서 요구사항
    drm = sb.table("doc_rule_mapping").select("doc_id, source_field_names").limit(50).execute()

    # 5. 평가 결과
    creatable = len(missing) == 0

    return {
        "status": "success",
        "form_code": form_code,
        "form_name": form["form_name"],
        "factory_id": factory_id,
        "creatable": creatable,
        "missing": missing,
        "required_field_count": len(required_fields),
        "doc_mapping_count": len(drm.data or []),
        "source": "DETERMINISTIC",
    }


@router.get("/checklist-candidates")
def list_checklist_candidates(
    is_mandatory: bool = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """체크리스트 후보 목록 — 안전관리자 선택용"""
    sb = _sb()
    q = sb.table("checklist_item_candidate").select("*, document_schema_candidate(doc_name, category)")
    if is_mandatory is not None:
        q = q.eq("is_mandatory", is_mandatory)
    offset = (page - 1) * page_size
    q = q.order("item_no").range(offset, offset + page_size - 1)
    r = q.execute()
    return {"status": "success", "data": r.data or [], "page": page, "source": "DETERMINISTIC"}


@router.post("/activate-checklist")
def activate_checklist_items(
    inspection_set_id: str = Query(...),
    candidate_ids: str = Query(..., description="comma-separated checklist_item_candidate IDs"),
):
    """안전관리자가 후보에서 선택하여 inspection_set_items 생성"""
    sb = _sb()

    # inspection_set 확인
    iset = sb.table("inspection_sets").select("id, company_id").eq("id", inspection_set_id).execute()
    if not iset.data:
        raise HTTPException(404, "Inspection set not found")

    ids = [cid.strip() for cid in candidate_ids.split(",") if cid.strip()]
    if not ids:
        raise HTTPException(400, "No candidate IDs provided")

    # candidate 조회
    candidates = sb.table("checklist_item_candidate").select("*").in_("id", ids).execute()
    if not candidates.data:
        raise HTTPException(404, "No candidates found")

    # 기존 items 수 확인 (seq 번호용)
    existing = sb.table("inspection_set_items").select("id").eq("inspection_set_id", inspection_set_id).execute()
    start_seq = len(existing.data or []) + 1

    created = []
    for i, c in enumerate(candidates.data):
        item = {
            "inspection_set_id": inspection_set_id,
            "item_seq": start_seq + i,
            "item_name": c["item_name"],
            "is_required": c["is_mandatory"],
            "source": "CANDIDATE_ACTIVATION",
            "description": c.get("law_ref", ""),
        }
        r = sb.table("inspection_set_items").insert(item).execute()
        if r.data:
            created.append(r.data[0])

    logger.info(f"CHECKLIST_ACTIVATED | set={inspection_set_id} items={len(created)}")
    return {
        "status": "success",
        "inspection_set_id": inspection_set_id,
        "activated_count": len(created),
        "data": created,
        "source": "DETERMINISTIC_MANUAL_ACTIVATION",
    }


@router.get("/obligation-graph")
def get_obligation_graph(
    factory_id: str = Query(...),
):
    """deterministic: 사업장별 obligation → document → checklist 그래프"""
    sb = _sb()

    # obligation_form_mapping
    ofm = sb.table("obligation_form_mapping").select("*").execute()

    # inspection_sets for this factory
    isets = sb.table("inspection_sets").select(
        "id, inspection_set_name, obligation_type, legal_rule_id, law_name"
    ).eq("factory_id", factory_id).eq("is_active", True).execute()

    # inspection_set_items count per set
    items_count = {}
    if isets.data:
        set_ids = [s["id"] for s in isets.data]
        for sid in set_ids[:20]:  # limit
            ic = sb.table("inspection_set_items").select("id").eq("inspection_set_id", sid).execute()
            items_count[sid] = len(ic.data or [])

    graph = {
        "factory_id": factory_id,
        "obligations": ofm.data or [],
        "inspection_sets": [
            {**s, "item_count": items_count.get(s["id"], 0)}
            for s in (isets.data or [])
        ],
        "source": "DETERMINISTIC",
    }
    return {"status": "success", "data": graph}


@router.get("/status")
def requirement_engine_status():
    return {
        "status": "active",
        "engine": "Document Completeness Engine v1.0.0",
        "routes": [
            "/requirement/document-completeness",
            "/requirement/checklist-candidates",
            "/requirement/activate-checklist",
            "/requirement/obligation-graph",
        ],
        "boundary": "DETERMINISTIC_ONLY",
    }
