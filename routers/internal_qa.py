"""Internal QA Result Callback + Catalog Sync — WO-QA-CONTROL-PHASE2B-001 PATCH-1 / WO-QA-ADMIN-EXISTING-CONSOLE-AUTOSYNC-001 STEP C.

/internal/qa/runs/{run_id}/results   POST — 실행 결과 수신 + lifecycle 전이
/internal/qa/catalog/sync            POST — tai-qa Scenario → qa_items 동기화

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
from services import qa_notify_svc as notify
from services.slack_dispatcher import send_slack

log = logging.getLogger("internal_qa")

router = APIRouter(prefix="/internal/qa", tags=["internal-qa"])


def _check_secret(x_internal_secret: Optional[str]) -> None:
    expected = os.environ.get("INTERNAL_API_SECRET")
    if not expected or x_internal_secret != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="invalid internal secret",
        )


# ── Catalog Sync models ───────────────────────────────────────────────────────

class ScenarioItem(BaseModel):
    scenario_id:      str
    name:             str
    description:      Optional[str] = None
    expected_summary: Optional[str] = None
    site_code:        str
    category:         str
    priority:         str
    runner_type:      str
    service_code:     str
    area_code:        str
    qa_type:          str


class CatalogSyncRequest(BaseModel):
    dry_run:   bool           = True
    scenarios: List[ScenarioItem]


# ── Result callback models ────────────────────────────────────────────────────

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


@router.post("/catalog/sync")
def catalog_sync(
    body: CatalogSyncRequest,
    x_internal_secret: Optional[str] = Header(None, alias="X-Internal-Secret"),
):
    """tai-qa Scenario → qa_items 동기화.

    dry_run=True: DB 변경 없음. would_create / would_update 분류만 반환.
    dry_run=False: INSERT (새 항목 + MANUAL 스케줄) + UPDATE (변경 필드).
    DELETE 없음 — 제거된 scenario는 DB 유지.
    """
    _check_secret(x_internal_secret)
    supabase = get_supabase()
    from services import qa_catalog_sync_svc as sync_svc
    data = sync_svc.sync_catalog(
        supabase,
        [s.model_dump() for s in body.scenarios],
        body.dry_run,
    )
    return {"status": "success", "data": data}


@router.post("/runs/{run_id}/results")
async def post_run_results(
    run_id: str,
    body:   RunResultsPayload,
    x_internal_secret: Optional[str] = Header(None, alias="X-Internal-Secret"),
):
    """QA 실행 결과 수신 + lifecycle 전이 + Slack 알림.

    scenario_id → qa_item_id resolve. canonical evidence 전체 비교 idempotency.
    Slack 실패는 callback 결과에 영향 없음 (fail-safe).
    """
    _check_secret(x_internal_secret)
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

    # Slack dispatch — fail-safe: Slack failure ≠ callback failure
    slack_attempted = 0
    slack_sent = 0

    for notif in data.get("notifications", []):
        payload = notify.build_qa_slack_payload(notif)
        slack_attempted += 1
        try:
            sent = await send_slack(**payload)
            if sent:
                slack_sent += 1
            else:
                log.warning("[qa_notify] Slack not sent: %s run=%s item=%s",
                            notif["event_type"], run_id, notif.get("qa_item_id"))
        except Exception as exc:
            log.warning("[qa_notify] Slack exception: %s", exc)

    run_notif = data.get("run_notification")
    if run_notif:
        payload = notify.build_qa_slack_payload(run_notif, is_run=True)
        slack_attempted += 1
        try:
            sent = await send_slack(**payload)
            if sent:
                slack_sent += 1
            else:
                log.warning("[qa_notify] Slack not sent: %s run=%s",
                            run_notif["event_type"], run_id)
        except Exception as exc:
            log.warning("[qa_notify] Slack exception: %s", exc)

    return {
        "status": "success",
        "data":   data,
        "slack":  {
            "attempted": slack_attempted,
            "sent":      slack_sent,
            "failed":    slack_attempted - slack_sent,
        },
    }
