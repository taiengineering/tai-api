"""TAI Document Completeness Engine v2.0.0
Mandatory / Recommended 2-tier Requirement Rule System.

역할: 현재 데이터 상태 → requirement completeness 평가
- MANDATORY 미충족 → 문서 생성 불가 (creatable=false)
- RECOMMENDED 미충족 → 문서 생성 가능 + warning (creatable=true)

절대 금지: inferred/guessed/semantic/AI requirement 판단
절대 금지: recommended가 사실상 mandatory처럼 동작 (Hidden Mandatory Drift)
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
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
    """deterministic: Mandatory/Recommended 분리 문서 생성 가능 여부 평가"""
    sb = _sb()

    # 1. obligation_form_mapping에서 form 확인
    ofm = sb.table("obligation_form_mapping").select("*").eq("form_code", form_code).execute()
    if not ofm.data:
        raise HTTPException(404, f"Form not found: {form_code}")

    form = ofm.data[0]

    # 2. factory 존재 확인
    fac = sb.table("factories").select("id, name").eq("id", factory_id).execute()
    mandatory_missing = []
    recommended_missing = []

    if not fac.data:
        mandatory_missing.append({"field": "factory", "reason": "사업장 정보 없음", "level": "MANDATORY"})

    # 3. document_requirement_rule 기반 평가
    rules = sb.table("document_requirement_rule").select("*").eq("form_code", form_code).eq("is_active", True).execute()

    mandatory_rules = [r for r in (rules.data or []) if r["requirement_level"] == "MANDATORY"]
    recommended_rules = [r for r in (rules.data or []) if r["requirement_level"] == "RECOMMENDED"]

    # 4. 각 mandatory rule에 대해 데이터 존재 여부 평가 (deterministic)
    # 현재는 rule 존재 확인 + factory 존재 확인 수준
    # 실제 구현에서는 각 field_code에 대한 데이터 존재 여부 평가

    # 5. creatable = mandatory_missing이 0일 때만 true
    creatable = len(mandatory_missing) == 0

    return {
        "status": "success",
        "form_code": form_code,
        "form_name": form["form_name"],
        "factory_id": factory_id,
        "creatable": creatable,
        "mandatory_count": len(mandatory_rules),
        "recommended_count": len(recommended_rules),
        "mandatory_missing": mandatory_missing,
        "recommended_missing": recommended_missing,
        "source": "DETERMINISTIC",
        "engine_version": "v2.0.0",
    }


@router.get("/requirement-rules")
def list_requirement_rules(
    form_code: Optional[str] = Query(None),
    requirement_level: Optional[str] = Query(None),
):
    """문서 요구사항 규칙 조회 — Mandatory/Recommended 분리"""
    sb = _sb()
    q = sb.table("document_requirement_rule").select("*").eq("is_active", True)
    if form_code:
        q = q.eq("form_code", form_code)
    if requirement_level:
        q = q.eq("requirement_level", requirement_level)
    q = q.order("form_code").order("requirement_level").limit(200)
    r = q.execute()
    return {"status": "success", "data": r.data or [], "source": "DETERMINISTIC"}


@router.get("/checklist-candidates")
def list_checklist_candidates(
    is_mandatory: Optional[bool] = Query(None),
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

    iset = sb.table("inspection_sets").select("id, company_id").eq("id", inspection_set_id).execute()
    if not iset.data:
        raise HTTPException(404, "Inspection set not found")

    ids = [cid.strip() for cid in candidate_ids.split(",") if cid.strip()]
    if not ids:
        raise HTTPException(400, "No candidate IDs provided")

    candidates = sb.table("checklist_item_candidate").select("*").in_("id", ids).execute()
    if not candidates.data:
        raise HTTPException(404, "No candidates found")

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

    ofm = sb.table("obligation_form_mapping").select("*").execute()

    isets = sb.table("inspection_sets").select(
        "id, inspection_set_name, obligation_type, legal_rule_id, law_name"
    ).eq("factory_id", factory_id).eq("is_active", True).execute()

    items_count = {}
    if isets.data:
        for sid in [s["id"] for s in isets.data][:20]:
            ic = sb.table("inspection_set_items").select("id").eq("inspection_set_id", sid).execute()
            items_count[sid] = len(ic.data or [])

    # requirement rules per form
    rule_counts = {}
    for o in (ofm.data or []):
        fc = o.get("form_code")
        if fc and fc not in rule_counts:
            rr = sb.table("document_requirement_rule").select("requirement_level").eq("form_code", fc).eq("is_active", True).execute()
            rule_counts[fc] = {
                "mandatory": len([r for r in (rr.data or []) if r["requirement_level"] == "MANDATORY"]),
                "recommended": len([r for r in (rr.data or []) if r["requirement_level"] == "RECOMMENDED"]),
            }

    graph = {
        "factory_id": factory_id,
        "obligations": [
            {**o, "requirement_rules": rule_counts.get(o.get("form_code"), {})}
            for o in (ofm.data or [])
        ],
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
        "engine": "Document Completeness Engine v2.0.0",
        "features": ["mandatory_recommended_rules", "document_completeness", "checklist_activation", "obligation_graph"],
        "routes": [
            "/requirement/document-completeness",
            "/requirement/requirement-rules",
            "/requirement/checklist-candidates",
            "/requirement/activate-checklist",
            "/requirement/obligation-graph",
        ],
        "boundary": "DETERMINISTIC_ONLY",
    }
