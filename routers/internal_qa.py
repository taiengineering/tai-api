"""Internal QA Result Callback — WO-QA-CONTROL-PHASE2B-001.

/internal/qa/runs/{run_id}/results   POST — 실행 결과 수신 + lifecycle 전이

인증: X-Internal-Secret 헤더 (INTERNAL_API_SECRET env).
GitHub dispatch = 0. Slack = 0. DB schema mutation = 0.

Idempotency:
  - 동일 (run_id, qa_item_id, attempt) + 동일 result_status → OK (skipped 카운트)
  - 동일 key + 다른 result_status → 409

Lifecycle:
  QUEUED → RUNNING → COMPLETED / ERROR / CANCELED (단방향, final 재진입 불가)
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
    qa_item_id:    str
    result_status: str
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
    run_status:          Optional[str]       = None
    github_run_id:       Optional[int]       = None
    github_run_attempt:  Optional[int]       = None
    results:             List[ResultItem]    = []


@router.post("/runs/{run_id}/results")
def post_run_results(
    run_id:  str,
    body:    RunResultsPayload,
    x_internal_secret: Optional[str] = Header(None, alias="X-Internal-Secret"),
):
    """QA 실행 결과 수신 + lifecycle 전이.

    멱등성 보장: 동일 key 동일 payload → skip. 다른 payload → 409.
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
        results=results_dicts,
    )
    return {"status": "success", "data": data}
