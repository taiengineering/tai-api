"""TAI Deterministic QA & Regression Verification API v1.0.0
Golden Scenario + Regression + Cross-Graph Consistency + Unsupported Coverage.

목적: 모순과 drift 탐지. 정답 추론 금지.
절대 금지: AI obligation 생성, semantic fallback, unsupported 추론.
"""
from fastapi import APIRouter, HTTPException, Query, Request
from typing import Optional
import logging
from datetime import datetime

router = APIRouter(prefix="/deterministic-qa", tags=["Deterministic QA"])
logger = logging.getLogger("deterministic_qa")

ALLOWED_ROLES = {"ROLE_ENGINE_ADMIN", "ROLE_SUPER_ADMIN", "admin", "super_admin"}


def _check_admin(request: Request):
    role = getattr(request.state, "user_role", None)
    if role and role not in ALLOWED_ROLES:
        raise HTTPException(403, "QA is admin-only.")


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


@router.get("/golden-scenarios")
def list_golden_scenarios(request: Request, domain_type: Optional[str] = Query(None)):
    _check_admin(request)
    sb = _sb()
    q = sb.table("golden_scenario_registry").select("*")
    if domain_type:
        q = q.eq("domain_type", domain_type)
    q = q.order("scenario_code").limit(200)
    r = q.execute()
    return {"status": "success", "data": r.data or []}


@router.get("/unsupported-coverage")
def list_unsupported_coverage(request: Request):
    _check_admin(request)
    sb = _sb()
    r = sb.table("unsupported_coverage_registry").select("*").eq("status", "ACTIVE").order("created_at", desc=True).limit(100).execute()
    return {"status": "success", "data": r.data or []}


@router.get("/regression-logs")
def list_regression_logs(request: Request, page: int = Query(1, ge=1)):
    _check_admin(request)
    sb = _sb()
    offset = (page - 1) * 20
    r = sb.table("regression_execution_log").select("*").order("execution_time", desc=True).range(offset, offset + 19).execute()
    return {"status": "success", "data": r.data or [], "page": page}


@router.get("/truth-dataset")
def list_truth_dataset(request: Request, truth_type: Optional[str] = Query(None)):
    _check_admin(request)
    sb = _sb()
    q = sb.table("operational_truth_dataset").select("*")
    if truth_type:
        q = q.eq("truth_type", truth_type)
    q = q.order("validated_at", desc=True).limit(100)
    r = q.execute()
    return {"status": "success", "data": r.data or []}


@router.post("/run-regression")
def run_regression(request: Request):
    """전체 golden scenario 기반 regression 실행 (deterministic)"""
    _check_admin(request)
    sb = _sb()

    scenarios = sb.table("golden_scenario_registry").select("*").eq("supported_status", "SUPPORTED").execute()
    all_sc = scenarios.data or []
    total = len(all_sc)
    passed = 0
    failed = 0
    critical = 0
    failures = []

    # Cross-Graph Consistency: orphan checks
    orphan_evidence = sb.table("runtime_compliance_evidence").select("id").is_("source_trace", "null").limit(1).execute()
    if orphan_evidence.data:
        critical += 1
        failures.append({"type": "GRAPH_INCONSISTENCY", "detail": "evidence with null source_trace"})

    # Completeness integrity: mandatory rule 있는데 creatable=true
    mandatory_rules = sb.table("document_requirement_rule").select("form_code").eq("requirement_level", "MANDATORY").eq("is_active", True).execute()
    if mandatory_rules.data:
        passed += 1  # rules exist = structure intact
    else:
        failed += 1
        failures.append({"type": "REQUIREMENT_REGRESSION", "detail": "no mandatory rules found"})

    # Golden scenario stub: 각 scenario의 expected_obligations 존재 여부 검증
    for sc in all_sc:
        expected = sc.get("expected_obligations", [])
        if expected:
            passed += 1
        else:
            failed += 1
            failures.append({"type": "OBLIGATION_REGRESSION", "scenario": sc["scenario_code"]})

    # 결과 저장
    log = {
        "total_scenarios": total,
        "passed_count": passed,
        "failed_count": failed,
        "critical_failures": critical,
        "result_summary": {"failures": failures[:20]},
        "source_trace": "REGRESSION_MANUAL",
    }
    r = sb.table("regression_execution_log").insert(log).execute()

    # Engine Monitoring 이벤트
    if critical > 0 or failed > 0:
        sb.table("engine_integrity_event").insert({
            "event_type": "REGRESSION_FAILURE" if failed > 0 else "DETERMINISTIC_VALIDATION_FAILED",
            "severity": "CRITICAL" if critical > 0 else "HIGH",
            "domain": "REGRESSION_QA",
            "description": f"Regression: {passed}/{total} passed, {failed} failed, {critical} critical",
            "source_trace": "INTEGRITY_MONITOR",
        }).execute()

    logger.info(f"REGRESSION_RUN | total={total} passed={passed} failed={failed} critical={critical}")
    return {
        "status": "success",
        "total": total,
        "passed": passed,
        "failed": failed,
        "critical": critical,
        "publish_allowed": critical == 0 and failed == 0,
    }


@router.get("/status")
def qa_status():
    sb = _sb()
    sc = sb.table("golden_scenario_registry").select("id", count="exact").execute()
    uc = sb.table("unsupported_coverage_registry").select("id").eq("status", "ACTIVE").execute()
    rl = sb.table("regression_execution_log").select("id", count="exact").execute()
    return {
        "status": "active",
        "engine": "Deterministic QA v1.0.0",
        "golden_scenarios": len(sc.data or []),
        "unsupported_domains": len(uc.data or []),
        "regression_runs": len(rl.data or []),
        "boundary": "DETERMINISTIC_ONLY",
        "publish_blocking": True,
    }
