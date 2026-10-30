"""TAI Review Queue Runtime Bridge v1.0.0
Phase 5: Operational Authority → Runtime Governance.

금지: reviewer bypass, hidden approval, auto approval,
      silent rejection, duplicate review, legacy mutation
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Any, Dict, Optional
import logging

from routers.auth import get_current_user

router = APIRouter(prefix="/bridge", tags=["검토 브릿지"])
logger = logging.getLogger("review_bridge")

# Evidence 승인 가능 role_code — legal_engine_patch.SAFETY_MANAGER_ROLES 정본 (003, 012 = 안전관리자)
# public.roles 기준: 002=관리자, 003=안전관리자, 012=안전관리자
_EVIDENCE_APPROVE_ROLE_CODES: frozenset = frozenset({"003", "012"})


def _audit(action: str, entity: str, entity_id: str, user_id: str = "system"):
    logger.info(f"REVIEW_BRIDGE_AUDIT | action={action} entity={entity} id={entity_id} by={user_id}")


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


# ═══ Review Queue ═══

@router.get("/review-queue")
def bridge_review_queue(
    review_domain: Optional[str] = Query(None),
    review_status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """검토 대기 목록"""
    sb = _sb()
    q = sb.table("runtime_review_decision").select("*")
    if review_domain:
        q = q.eq("review_domain", review_domain)
    if review_status:
        q = q.eq("review_status", review_status)
    offset = (page - 1) * page_size
    q = q.order("created_at", desc=True).range(offset, offset + page_size - 1)
    r = q.execute()
    return {"status": "success", "source": "runtime", "data": r.data or [], "page": page}


@router.get("/review-queue/{decision_id}")
def bridge_get_review(decision_id: str):
    """검토 단건 조회"""
    sb = _sb()
    r = sb.table("runtime_review_decision").select("*").eq("id", decision_id).execute()
    if not r.data:
        raise HTTPException(404, "Review decision not found")
    return {"status": "success", "source": "runtime", "data": r.data[0]}


# ═══ Review Decisions ═══

@router.post("/review-decisions")
def bridge_create_review(
    review_domain: str = Query(...),
    source_entity_id: str = Query(...),
    reviewer_id: str = Query(...),
    review_action: str = Query(...),
    review_reason: Optional[str] = Query(None),
):
    """검토 결정 생성. authority 검증 트리거 적용."""
    valid_actions = ['APPROVE', 'REJECT', 'RETURN_FOR_EDIT', 'ESCALATE', 'REOPEN']
    if review_action not in valid_actions:
        raise HTTPException(400, f"Invalid action. Must be: {valid_actions}")
    if review_action == 'REJECT' and not review_reason:
        raise HTTPException(400, "REJECT requires review_reason")

    sb = _sb()
    row = {
        "review_domain": review_domain,
        "source_entity_id": source_entity_id,
        "reviewer_id": reviewer_id,
        "review_action": review_action,
        "review_reason": review_reason,
        "review_started_at": "now()",
        "source_trace": "MANUAL_REVIEW",
    }
    try:
        r = sb.table("runtime_review_decision").insert(row).execute()
    except Exception as e:
        raise HTTPException(400, str(e))

    _audit(f"REVIEW_{review_action}", "review_decision", r.data[0]["id"], reviewer_id)
    return {"status": "success", "source": "runtime", "data": r.data[0]}


# ═══ Shortcuts: Approve / Reject / Reopen ═══

@router.post("/approve")
def bridge_approve(
    review_domain: str = Query(...),
    source_entity_id: str = Query(...),
    reviewer_id: str = Query(...),
    review_reason: Optional[str] = Query(None),
):
    """승인 실행"""
    return bridge_create_review(
        review_domain=review_domain,
        source_entity_id=source_entity_id,
        reviewer_id=reviewer_id,
        review_action='APPROVE',
        review_reason=review_reason,
    )


@router.post("/reject")
def bridge_reject(
    review_domain: str = Query(...),
    source_entity_id: str = Query(...),
    reviewer_id: str = Query(...),
    review_reason: str = Query(...),
):
    """반려 실행. reason 필수."""
    return bridge_create_review(
        review_domain=review_domain,
        source_entity_id=source_entity_id,
        reviewer_id=reviewer_id,
        review_action='REJECT',
        review_reason=review_reason,
    )


@router.post("/reopen")
def bridge_reopen(
    review_domain: str = Query(...),
    source_entity_id: str = Query(...),
    reviewer_id: str = Query(...),
    review_reason: str = Query(...),
):
    """재오픈"""
    return bridge_create_review(
        review_domain=review_domain,
        source_entity_id=source_entity_id,
        reviewer_id=reviewer_id,
        review_action='REOPEN',
        review_reason=review_reason,
    )


# ═══ Review Authority ═══

@router.get("/review-authority")
def bridge_list_authority(
    review_domain: Optional[str] = Query(None),
):
    """검토 권한 목록"""
    sb = _sb()
    q = sb.table("runtime_review_authority").select("*")
    if review_domain:
        q = q.eq("review_domain", review_domain)
    q = q.eq("authority_status", "ACTIVE").order("approval_level").limit(50)
    r = q.execute()
    return {"status": "success", "source": "runtime", "data": r.data or []}


# ═══ Review Escalations ═══

@router.get("/review-escalations")
def bridge_list_review_escalations(
    escalation_status: Optional[str] = Query(None),
):
    """검토 에스컬레이션 목록"""
    sb = _sb()
    q = sb.table("runtime_review_escalation").select(
        "*, runtime_review_decision(review_domain, review_action)"
    )
    if escalation_status:
        q = q.eq("escalation_status", escalation_status)
    q = q.order("created_at", desc=True).limit(50)
    r = q.execute()
    return {"status": "success", "source": "runtime", "data": r.data or []}


# ═══ Evidence Candidate 승인 (C3-04 / C2-FINAL §2) ═══════════════

@router.post("/evidence-approve")
def bridge_evidence_approve(
    evidence_field_candidate_id: str = Query(...),
    review_reason: str = Query(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Evidence Candidate 승인 (runtime_review_decision INSERT + status UPDATE 원자 처리).

    C2-FINAL §2-3 계약:
      - 선제 역할 검증: current_user.role_code ∈ _EVIDENCE_APPROVE_ROLE_CODES (DB 이전)
      - AND 조건 권한 검증: approver_user_id AND approver_role AND approval_scope
      - review_reason 필수 (빈 문자열·공백 불허)
      - 원자 트랜잭션: review_decision INSERT + evidence_field_candidate.status UPDATE
      - 중복·부정 전이 차단
    """
    import psycopg2
    from db.direct_sql import _connect

    reviewer_id = str(current_user.get("id") or "")
    if not reviewer_id:
        raise HTTPException(401, "authentication required")

    # [선제 역할 검증] 인증된 사용자의 role_code가 SAFETY_MANAGER에 해당하는지 확인
    # DB authority 조회 이전에 Fail-Closed 차단 (P0-2)
    if str(current_user.get("role_code", "")) not in _EVIDENCE_APPROVE_ROLE_CODES:
        raise HTTPException(
            403,
            "reviewer role is not authorized for EVIDENCE approval",
        )

    if not review_reason or not str(review_reason).strip():
        raise HTTPException(400, "review_reason is required and must not be blank")

    try:
        conn = _connect()
    except Exception:
        raise HTTPException(503, "database unavailable")

    try:
        conn.autocommit = False
        import psycopg2.extras
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:

            # [단계 1] 권한 검증 — AND 조건 (C2-FINAL §2-3, OR 금지)
            # 실제 DB 컬럼: approver_user_id, approver_role, approval_scope
            cur.execute(
                """
                SELECT 1 FROM runtime_review_authority
                WHERE review_domain = 'EVIDENCE'
                  AND authority_status = 'ACTIVE'
                  AND approver_user_id = %s
                  AND approver_role = 'SAFETY_MANAGER'
                  AND approval_scope LIKE '%%증빙%%'
                LIMIT 1
                """,
                (reviewer_id,),
            )
            if not cur.fetchone():
                raise HTTPException(
                    403,
                    "reviewer is not authorized for EVIDENCE approval "
                    "(requires SAFETY_MANAGER role with 증빙 scope)",
                )

            # [단계 2] 대상 행 잠금 + 현재 상태 확인
            cur.execute(
                "SELECT id, status FROM evidence_field_candidate WHERE id = %s FOR UPDATE",
                (evidence_field_candidate_id,),
            )
            target = cur.fetchone()
            if not target:
                raise HTTPException(404, f"evidence_field_candidate {evidence_field_candidate_id!r} not found")
            target = dict(target)

            current_status = target["status"]
            if current_status not in ("CANDIDATE", "NEEDS_HUMAN_REVIEW"):
                raise HTTPException(
                    409,
                    f"evidence_field_candidate already processed "
                    f"(status={current_status!r}). Cannot re-approve.",
                )

            # 중복 APPROVE decision 차단
            cur.execute(
                """
                SELECT 1 FROM runtime_review_decision
                WHERE review_domain = 'EVIDENCE'
                  AND source_entity_id = %s
                  AND review_action = 'APPROVE'
                LIMIT 1
                """,
                (evidence_field_candidate_id,),
            )
            if cur.fetchone():
                raise HTTPException(
                    409,
                    f"APPROVE decision already exists for evidence_field_candidate "
                    f"{evidence_field_candidate_id!r}",
                )

            # [단계 3] review_decision INSERT
            cur.execute(
                """
                INSERT INTO runtime_review_decision
                  (review_domain, source_entity_id, reviewer_id,
                   review_action, review_reason, review_started_at, source_trace)
                VALUES (%s, %s, %s, 'APPROVE', %s, now(), 'MANUAL_REVIEW')
                RETURNING id
                """,
                ("EVIDENCE", evidence_field_candidate_id, reviewer_id, review_reason),
            )
            decision_row = dict(cur.fetchone())
            decision_id = decision_row["id"]

            # [단계 4] evidence_field_candidate.status → APPROVED_BY_HUMAN (동일 TX)
            cur.execute(
                """
                UPDATE evidence_field_candidate
                SET status = 'APPROVED_BY_HUMAN'
                WHERE id = %s AND status IN ('CANDIDATE', 'NEEDS_HUMAN_REVIEW')
                """,
                (evidence_field_candidate_id,),
            )
            if cur.rowcount != 1:
                raise HTTPException(
                    409,
                    "evidence_field_candidate status update failed — concurrent modification",
                )

        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        logger.exception("evidence approval failed")
        raise HTTPException(500, "evidence approval failed")
    finally:
        conn.close()

    _audit("EVIDENCE_APPROVE", "evidence_field_candidate", evidence_field_candidate_id, reviewer_id)
    return {
        "status": "success",
        "source": "runtime",
        "data": {
            "evidence_field_candidate_id": evidence_field_candidate_id,
            "review_decision_id": str(decision_id),
            "new_status": "APPROVED_BY_HUMAN",
            "reviewer_id": reviewer_id,
        },
    }


# ═══ Runtime Evidence Field 사용 승인 (WO-DOC260-POSTACT-P0E-B2-RUNTIME-APPROVAL-003) ═══

# Owner Gate로 허용된 증적 ID 화이트리스트 (WO-DOC260-POSTACT-P0E-B2-002 범위)
# 확대는 별도 Owner Gate 필수
_RUNTIME_EV_ALLOWLIST: frozenset = frozenset({
    "fd3f3c99-62cd-4336-bf23-dda92a4b2a43",  # DOC-CHEM-001 설계 및 배치도 첨부
    "e1793f5c-aba8-4700-9dce-2ae2b449117b",  # DOC-FAC-022 첨부서류
})


@router.post("/evidence-runtime-approve")
def bridge_evidence_runtime_approve(
    runtime_evidence_field_id: str = Query(...),
    review_reason: str = Query(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Runtime Evidence Field 사용 승인.

    선행 후보 승인(evidence-approve)과 독립된 별도 경로 — C2-FINAL 설계 정합.

    선행 조건:
      1. 인증된 사용자 + role_code ∈ _EVIDENCE_APPROVE_ROLE_CODES
      1b. runtime_evidence_field_id ∈ _RUNTIME_EV_ALLOWLIST (Owner Gate 범위 제한)
      2. runtime_review_authority 권한 검증 (AND 조건)
      3. runtime_evidence_field.status = CANDIDATE
      4. evidence_family/upload_type 정합 (G-B01):
           ATTACHMENT: upload_type = attachment, input_type = file
           DATE:       upload_type = timestamp_auto, input_type = date
           교차 조합 → 422
      5. evidence_field_candidate.status = APPROVED_BY_HUMAN (선행 후보 승인 완료)
      6. EVIDENCE APPROVE decision 존재 (efc_id 기준, review_status=APPROVED)
      7. runtime_form_schema.status = APPROVED_FOR_RUNTIME_USE
      8. field connection: 정확히 1건, input_type family 일치
      9. 중복 RUNTIME_EVIDENCE_APPROVE decision 차단

    처리: runtime_review_decision INSERT + runtime_evidence_field.status 전이 (원자 TX)
    감사: review_domain='EVIDENCE', source_trace='RUNTIME_EVIDENCE_APPROVE'
    """
    import psycopg2
    from db.direct_sql import _connect

    reviewer_id = str(current_user.get("id") or "")
    if not reviewer_id:
        raise HTTPException(401, "authentication required")

    if str(current_user.get("role_code", "")) not in _EVIDENCE_APPROVE_ROLE_CODES:
        raise HTTPException(403, "reviewer role is not authorized for EVIDENCE_RUNTIME approval")

    if runtime_evidence_field_id not in _RUNTIME_EV_ALLOWLIST:
        raise HTTPException(
            403,
            f"runtime_evidence_field {runtime_evidence_field_id!r} is not in the "
            "approved allowlist for this Owner Gate. "
            "Scope expansion requires a separate Owner Gate.",
        )

    if not review_reason or not str(review_reason).strip():
        raise HTTPException(400, "review_reason is required and must not be blank")

    try:
        conn = _connect()
    except Exception:
        raise HTTPException(503, "database unavailable")

    try:
        conn.autocommit = False
        import psycopg2.extras
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:

            # [1] 권한 검증 — AND 조건
            cur.execute(
                """
                SELECT 1 FROM runtime_review_authority
                WHERE review_domain = 'EVIDENCE'
                  AND authority_status = 'ACTIVE'
                  AND approver_user_id = %s
                  AND approver_role = 'SAFETY_MANAGER'
                  AND approval_scope LIKE '%%증빙%%'
                LIMIT 1
                """,
                (reviewer_id,),
            )
            if not cur.fetchone():
                raise HTTPException(
                    403,
                    "reviewer is not authorized for EVIDENCE_RUNTIME approval "
                    "(requires SAFETY_MANAGER role with 증빙 scope)",
                )

            # [2] runtime_evidence_field 잠금 + 상태 확인
            cur.execute(
                """
                SELECT id, status, evidence_family, upload_type,
                       evidence_candidate_id, form_schema_id
                FROM runtime_evidence_field
                WHERE id = %s
                FOR UPDATE
                """,
                (runtime_evidence_field_id,),
            )
            ev = cur.fetchone()
            if not ev:
                raise HTTPException(404, f"runtime_evidence_field {runtime_evidence_field_id!r} not found")
            ev = dict(ev)

            if ev["status"] != "CANDIDATE":
                raise HTTPException(
                    409,
                    f"runtime_evidence_field already processed (status={ev['status']!r}). "
                    "Cannot re-approve.",
                )

            # [3] evidence_family / upload_type 정합 검증 (G-B01: DATE 지원 추가)
            ev_family = ev["evidence_family"]
            if ev_family == "ATTACHMENT":
                if ev["upload_type"] != "attachment":
                    raise HTTPException(
                        422,
                        f"upload_type={ev['upload_type']!r} not valid for ATTACHMENT family "
                        "(expected attachment)",
                    )
            elif ev_family == "DATE":
                if ev["upload_type"] != "timestamp_auto":
                    raise HTTPException(
                        422,
                        f"upload_type={ev['upload_type']!r} not valid for DATE family "
                        "(expected timestamp_auto)",
                    )
            else:
                raise HTTPException(
                    422,
                    f"evidence_family={ev_family!r} not supported "
                    "(supported: ATTACHMENT, DATE)",
                )

            evidence_candidate_id = str(ev.get("evidence_candidate_id") or "")
            if not evidence_candidate_id:
                raise HTTPException(422, "evidence_candidate_id missing — FK path broken")

            # [4] evidence_field_candidate 상태 확인 — 선행 후보 승인 필수
            cur.execute(
                "SELECT id, status, field_candidate_id FROM evidence_field_candidate WHERE id = %s LIMIT 1",
                (evidence_candidate_id,),
            )
            efc = cur.fetchone()
            if not efc:
                raise HTTPException(404, f"evidence_field_candidate {evidence_candidate_id!r} not found")
            efc = dict(efc)

            if efc["status"] != "APPROVED_BY_HUMAN":
                raise HTTPException(
                    409,
                    f"evidence_field_candidate not yet approved (status={efc['status']!r}). "
                    "Run /bridge/evidence-approve first.",
                )

            # [5] 선행 EVIDENCE APPROVE decision 존재 확인 (action + status 이중 확인)
            cur.execute(
                """
                SELECT 1 FROM runtime_review_decision
                WHERE review_domain = 'EVIDENCE'
                  AND source_entity_id = %s
                  AND review_action = 'APPROVE'
                  AND review_status = 'APPROVED'
                LIMIT 1
                """,
                (evidence_candidate_id,),
            )
            if not cur.fetchone():
                raise HTTPException(
                    409,
                    f"No finalized EVIDENCE APPROVE decision (review_status=APPROVED) found "
                    f"for evidence_field_candidate {evidence_candidate_id!r}. Audit trail missing.",
                )

            # [6] runtime_form_schema 상태 확인
            form_schema_id = str(ev.get("form_schema_id") or "")
            cur.execute(
                "SELECT id, status FROM runtime_form_schema WHERE id = %s LIMIT 1",
                (form_schema_id,),
            )
            rfs = cur.fetchone()
            if not rfs:
                raise HTTPException(404, f"runtime_form_schema {form_schema_id!r} not found")
            rfs = dict(rfs)
            if rfs["status"] != "APPROVED_FOR_RUNTIME_USE":
                raise HTTPException(
                    409,
                    f"runtime_form_schema not approved for runtime use "
                    f"(status={rfs['status']!r})",
                )

            # [7] field connection 검증 — 정확히 1건, input_type family 일치
            field_candidate_id = str(efc.get("field_candidate_id") or "")
            if not field_candidate_id:
                raise HTTPException(422, "field_candidate_id missing in evidence_field_candidate")

            cur.execute(
                """
                SELECT id, input_type FROM runtime_field
                WHERE field_candidate_id = %s
                  AND form_schema_id = %s
                """,
                (field_candidate_id, form_schema_id),
            )
            matched_fields = cur.fetchall()
            if len(matched_fields) == 0:
                raise HTTPException(422, "no runtime_field matched — connection broken")
            if len(matched_fields) > 1:
                raise HTTPException(422, "ambiguous connection — multiple runtime_fields matched")

            rf = dict(matched_fields[0])
            expected_input_type = "file" if ev_family == "ATTACHMENT" else "date"
            if rf["input_type"] != expected_input_type:
                raise HTTPException(
                    422,
                    f"connected runtime_field.input_type={rf['input_type']!r} not valid "
                    f"for {ev_family} family (expected {expected_input_type!r})",
                )

            # [8] 중복 RUNTIME_EVIDENCE_APPROVE decision 차단
            cur.execute(
                """
                SELECT 1 FROM runtime_review_decision
                WHERE review_domain = 'EVIDENCE'
                  AND source_entity_id = %s
                  AND source_trace = 'RUNTIME_EVIDENCE_APPROVE'
                  AND review_action = 'APPROVE'
                LIMIT 1
                """,
                (runtime_evidence_field_id,),
            )
            if cur.fetchone():
                raise HTTPException(
                    409,
                    f"RUNTIME_EVIDENCE_APPROVE decision already exists for "
                    f"runtime_evidence_field {runtime_evidence_field_id!r}",
                )

            # [9] runtime_review_decision INSERT
            cur.execute(
                """
                INSERT INTO runtime_review_decision
                  (review_domain, source_entity_id, reviewer_id,
                   review_action, review_reason, review_started_at, source_trace)
                VALUES (%s, %s, %s, 'APPROVE', %s, now(), 'RUNTIME_EVIDENCE_APPROVE')
                RETURNING id
                """,
                ("EVIDENCE", runtime_evidence_field_id, reviewer_id, review_reason),
            )
            decision_row = dict(cur.fetchone())
            decision_id = decision_row["id"]

            # [10] runtime_evidence_field.status → APPROVED_BY_HUMAN
            cur.execute(
                """
                UPDATE runtime_evidence_field
                SET status = 'APPROVED_BY_HUMAN'
                WHERE id = %s AND status = 'CANDIDATE'
                """,
                (runtime_evidence_field_id,),
            )
            if cur.rowcount != 1:
                raise HTTPException(
                    409,
                    "runtime_evidence_field status update failed — concurrent modification",
                )

        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        logger.exception("evidence runtime approval failed")
        raise HTTPException(500, "evidence runtime approval failed")
    finally:
        conn.close()

    _audit("EVIDENCE_RUNTIME_APPROVE", "runtime_evidence_field", runtime_evidence_field_id, reviewer_id)
    return {
        "status": "success",
        "source": "runtime",
        "data": {
            "runtime_evidence_field_id": runtime_evidence_field_id,
            "review_decision_id": str(decision_id),
            "new_status": "APPROVED_BY_HUMAN",
            "reviewer_id": reviewer_id,
        },
    }


# ═══ Status ═══

@router.get("/review-status")
def bridge_review_status():
    return {
        "status": "active",
        "phase": "Phase 5 — Runtime Review Governance",
        "bridge_routes": [
            "/bridge/review-queue",
            "/bridge/review-queue/{id}",
            "/bridge/review-decisions",
            "/bridge/review-authority",
            "/bridge/review-escalations",
            "/bridge/approve",
            "/bridge/reject",
            "/bridge/reopen",
        ],
    }
