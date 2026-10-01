"""Internal QA Result Callback — WO-QA-CONTROL-PHASE2B-001 PATCH-1.

/internal/qa/runs/{run_id}/results   POST — 실행 결과 수신 + lifecycle 전이

인증: X-Internal-Secret 헤더 (INTERNAL_API_SECRET env).

Input: scenario_id (tai-qa SoT) → tai-api가 qa_item_id resolve.

Idempotency:
  - 동일 (run_id, qa_item_id, attempt) + 모든 canonical evidence 동일 → OK (skipped)
  - 동일 key + 어떤 evidence라도 다름 → 409 RESULT_CONFLICT

Lifecycle:
  QUEUED → RUNNING / ERROR / CANCELED
  RUNNING → COMPLETED / ERROR / CANCELED
  Final 상태 + 동일 payload replay → idempotent 200
  Final 상태 + 다른 payload/status → 409

GitHub identity:
  NULL → 최초 binding 허용
  동일 identity replay → 허용
  다른 identity → 409 GITHUB_IDENTITY_MISMATCH
  id/attempt 중 하나만 제공 → 422
"""
import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel

from db.supabase_client import get_supabase
from services import qa_control_svc as svc

log = logging.getLogger("internal_qa")

router = APIRouter(prefix="/internal/qa", tags=["internal-qa"])


class ResultItem(BaseModel):
    scenario_id:   str                  # tai-qa SoT identifier
    result_status: str                  # PASS / FAIL / BLOCKED / SKIPPED
    attempt:       int           = 1
    duration_ms:   Optional[int] = None
    http_status:   Optional[int] = None
    error_code:    Optional[str] = None
    error_summary: Optional[str] = None
    artifact_ref:  Optional[str] = None
    started_at:    Optional[str] = None
    finished_at:   Optional[str] = None
    checked_at:    Optional[str] = None


class RunResultsPayload(BaseModel):
    run_status:         Optional[str]    = None
    github_run_id:      Optional[int]    = None
    github_run_attempt: Optional[int]    = None
    head_sha:           Optional[str]    = None
    branch_name:        Optional[str]    = None
    started_at:         Optional[str]    = None
    finished_at:        Optional[str]    = None
    error_code:         Optional[str]    = None
    error_summary:      Optional[str]    = None
    results:            List[ResultItem] = []


@router.post("/runs/{run_id}/results")
def post_run_results(
    run_id: str,
    body:   RunResultsPayload,
    x_internal_secret: Optional[str] = Header(None, alias="X-Internal-Secret"),
):
    """QA 실행 결과 수신 + lifecycle 전이.

    scenario_id → qa_item_id resolve. canonical evidence 전체 비교 idempotency.
    """
    expected = os.environ.get("INTERNAL_API_SECRET")
    if not expected or x_internal_secret != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="invalid internal secret",
        )

    supabase = get_supabase()
    results_dicts: List[Dict[str, Any]] = [r.model_dump() for r in body.results]

    data = svc.apply_results(
        supabase,
        run_id=run_id,
        new_status=body.run_status,
        github_run_id=body.github_run_id,
        github_run_attempt=body.github_run_attempt,
        head_sha=body.head_sha,
        branch_name=body.branch_name,
        run_started_at=body.started_at,
        run_finished_at=body.finished_at,
        run_error_code=body.error_code,
        run_error_summary=body.error_summary,
        results=results_dicts,
    )
    return {"status": "success", "data": data}
