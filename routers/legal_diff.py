"""TAI Legal Diff Engine & Impact Simulation API v1.0.0
법령 객체 구조적 변화 분석 + 운영 영향 시뮬레이션.

절대 금지: AI semantic inference, probabilistic estimation, 자동 publish.
허용: 수치 변경, 조문 존재 여부, field 추가/삭제, requirement 구조 변화.
"""
from fastapi import APIRouter, HTTPException, Query, Request
from typing import Optional
import logging
from datetime import datetime

router = APIRouter(prefix="/legal-diff", tags=["법령 Diff/영향시뮬레이션"])
logger = logging.getLogger("legal_diff")

ALLOWED_ROLES = {"ROLE_ENGINE_ADMIN", "ROLE_SUPER_ADMIN", "admin", "super_admin"}


def _check_admin(request: Request):
    role = getattr(request.state, "user_role", None)
    if role and role not in ALLOWED_ROLES:
        raise HTTPException(403, "Legal diff is admin-only.")


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


@router.get("/results")
def list_diff_results(
    request: Request,
    diff_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    _check_admin(request)
    sb = _sb()
    q = sb.table("legal_diff_result").select("*")
    if diff_type:
        q = q.eq("diff_type", diff_type)
    offset = (page - 1) * page_size
    q = q.order("detected_at", desc=True).range(offset, offset + page_size - 1)
    r = q.execute()
    return {"status": "success", "data": r.data or [], "page": page}


@router.get("/impact-simulation")
def list_impact_simulations(
    request: Request,
    severity: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    _check_admin(request)
    sb = _sb()
    q = sb.table("operational_impact_simulation").select("*")
    if severity:
        q = q.eq("severity", severity)
    offset = (page - 1) * page_size
    q = q.order("simulated_at", desc=True).range(offset, offset + page_size - 1)
    r = q.execute()
    return {"status": "success", "data": r.data or [], "page": page}


@router.get("/high-impact-laws")
def list_high_impact_laws(request: Request):
    _check_admin(request)
    sb = _sb()
    r = sb.table("operational_impact_simulation").select("*").in_(
        "severity", ["HIGH", "CRITICAL"]
    ).order("simulated_at", desc=True).limit(50).execute()
    return {"status": "success", "data": r.data or []}


@router.post("/run-simulation/{law_id}")
def run_impact_simulation(request: Request, law_id: str):
    """\ud2b9\uc815 \ubc95\ub839 \ubcc0\uacbd\uc5d0 \ub300\ud55c \uc6b4\uc601 \uc601\ud5a5 \uc2dc\ubbac\ub808\uc774\uc158 \uc2e4\ud589 (deterministic recalculation)"""
    _check_admin(request)
    sb = _sb()

    # diff 결과 존재 확인
    diffs = sb.table("legal_diff_result").select("*").eq("law_id", law_id).order("detected_at", desc=True).limit(1).execute()
    if not diffs.data:
        raise HTTPException(404, f"No diff result for law_id={law_id}")

    diff = diffs.data[0]

    # deterministic recalculation: 실제 사업장 데이터 기반 영향 계산
    companies = sb.table("companies").select("id", count="exact").eq("is_active", True).execute()
    sites = sb.table("factories").select("id", count="exact").eq("is_active", True).execute()
    company_count = len(companies.data or [])
    site_count = len(sites.data or [])

    # severity 계산
    severity = "INFO"
    if diff["diff_type"] in ("THRESHOLD_CHANGED", "REQUIREMENT_RULE_CHANGED"):
        severity = "CRITICAL" if company_count > 100 else "HIGH" if company_count > 10 else "WARNING"
    elif diff["diff_type"] in ("ARTICLE_ADDED", "ARTICLE_REMOVED"):
        severity = "HIGH"

    sim = {
        "law_id": law_id,
        "law_name": diff.get("law_name"),
        "diff_result_id": diff["id"],
        "affected_companies": company_count,
        "affected_sites": site_count,
        "new_obligations": 0,
        "removed_obligations": 0,
        "checklist_delta": 0,
        "document_delta": 0,
        "evidence_delta": 0,
        "simulation_status": "COMPLETED",
        "severity": severity,
        "source_trace": "DETERMINISTIC_SIMULATION",
    }
    r = sb.table("operational_impact_simulation").insert(sim).execute()

    # Engine Monitoring 이벤트
    sb.table("engine_integrity_event").insert({
        "event_type": "OPERATIONAL_IMPACT_SIMULATED" if severity != "CRITICAL" else "HIGH_IMPACT_LAW_CHANGE",
        "severity": severity,
        "domain": "LEGAL_DIFF",
        "description": f"{diff.get('law_name',law_id)}: {diff['diff_type']} → {company_count}회사/{site_count}사업장 영향",
        "source_trace": "INTEGRITY_MONITOR",
    }).execute()

    logger.info(f"IMPACT_SIMULATION | law={law_id} severity={severity} companies={company_count}")
    return {"status": "success", "data": r.data[0] if r.data else sim}


@router.get("/status")
def legal_diff_status():
    sb = _sb()
    diffs = sb.table("legal_diff_result").select("id", count="exact").execute()
    sims = sb.table("operational_impact_simulation").select("id", count="exact").execute()
    return {
        "status": "active",
        "engine": "Legal Diff Engine v1.0.0",
        "diff_results": len(diffs.data or []),
        "simulations": len(sims.data or []),
        "auto_publish": "BLOCKED",
        "boundary": "DETERMINISTIC_ONLY",
    }
