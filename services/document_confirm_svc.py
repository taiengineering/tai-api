"""
WP-DOCUMENT-ARCH-05B-B1 — Atomic confirm transaction (psycopg2 direct).

confirm(REVIEW_PENDING → APPROVED_BY_HUMAN)을 단일 psycopg2 트랜잭션으로 수행한다.
락 이후 값으로만 render/hash/archive 를 만들고, archive + approval + status seal 을
한 번에 커밋한다. 어느 단계든 실패하면 전부 롤백한다(partial state 0).

경계:
  - FastAPI 를 import 하지 않는다. 도메인 예외를 raise 하고, 라우터가 HTTPException 으로 변환한다.
  - APPROVE 경로는 기존 change_status()/_approval() 을 통과하지 않는다.
    _audit() 만 COMMIT 성공 후 best-effort 로 1회 호출한다(트랜잭션 밖).
  - body.actor_id 는 신뢰하지 않는다. 저장 SoT = 인증된 current_user.id.

계약 정본: docs/docs/DOCUMENT_ENGINE_05B_CONFIRM_TRANSACTION_v1.md
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from services.document_confirm_authz import authorize_confirm
from services.document_schema_renderer import (
    build_render_artifacts,
    SchemaRenderError,
)
from services.document_snapshot_integrity import (
    compute_confirmed_snapshot_hash,
    SnapshotCanonicalizationError,
)


# ── 도메인 예외 (라우터가 HTTP 로 변환) ──────────────────────────────────────
class ConfirmError(Exception):
    """confirm 실패 도메인 예외. http_status 로 라우터가 매핑한다."""

    def __init__(self, http_status: int, detail: str):
        super().__init__(detail)
        self.http_status = http_status
        self.detail = detail


# ── APPROVE 대상 전이 ───────────────────────────────────────────────────────
_TARGET_STATUS = "APPROVED_BY_HUMAN"
_REQUIRED_FROM = "REVIEW_PENDING"
_SNAPSHOT_SCHEMA_VERSION = 1


def _dict_cursor(conn):
    import psycopg2.extras
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def _normalize_values(raw: Any) -> Dict[str, Any]:
    """runtime_data_json 을 정규화. NULL → {}. 잘못된 타입은 숨기지 않고 실패시킨다."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    # dict 도 None 도 아닌 값을 {} 로 숨기면 봉인이 원본과 달라진다 → FAIL.
    raise ConfirmError(422, "runtime_data_json must be an object or null")


def _normalize_evidence(raw: Any) -> Any:
    """evidence_links 를 정규화. NULL → []. 그 외는 원본 유지(렌더러 범위 밖)."""
    if raw is None:
        return []
    return raw


def confirm_document_atomic(
    doc_id: str,
    *,
    actor_id: Optional[str],
    comment: Optional[str],
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    """confirm 을 단일 원자 트랜잭션으로 수행하고 봉인된 rdd row 를 반환한다.

    실패 시 ConfirmError(http_status, detail) 를 raise 한다. DB 는 전부 롤백된다.
    """
    import psycopg2
    from psycopg2 import errors as pg_errors
    from db.direct_sql import _connect

    if not isinstance(current_user, dict):
        raise ConfirmError(401, "authentication required")

    try:
        conn = _connect()
    except Exception:
        # DATABASE_URL 미설정 / 연결 불가
        raise ConfirmError(503, "database unavailable")

    try:
        conn.autocommit = False
        with _dict_cursor(conn) as cur:
            # 1. 대상 행 잠금 (없으면 404)
            cur.execute(
                "SELECT * FROM runtime_document_data WHERE id = %s FOR UPDATE",
                (doc_id,),
            )
            locked = cur.fetchone()
            if not locked:
                raise ConfirmError(404, "document not found")
            locked = dict(locked)

            # 3. (B1-CORR-01) role_data_scope 조회 제거.
            #     Confirm 권한은 role tier 가 아니라 제출자 identity 로 판정한다.
            #     submitted_by 는 위 FOR UPDATE 로 잠근 locked row 에서만 사용한다
            #     (재조회·pre-lock 조회 금지).

            # 4. doc.factory_id → factories.company_id (같은 TX)
            factory_company_id = None
            if locked.get("factory_id"):
                cur.execute(
                    "SELECT company_id FROM factories WHERE id = %s LIMIT 1",
                    (locked["factory_id"],),
                )
                fc = cur.fetchone()
                if fc:
                    factory_company_id = fc.get("company_id")

            # 5~6. 인가 (DENY → 롤백 + HTTP status)
            #      submitter-as-confirmer: locked.submitted_by == current_user.id.
            auth = authorize_confirm(
                current_user=current_user,
                document=locked,
                actor_id=actor_id,
                factory_company_id=factory_company_id,
            )
            if not auth.allowed:
                raise ConfirmError(auth.http_status or 403, auth.reason or "forbidden")
            confirmed_by = auth.confirmed_by  # = 인증 current_user.id

            # 7~8. 전이 규칙 + 상태 확인 (락 이후 값 기준)
            if locked.get("status") != _REQUIRED_FROM:
                # 이미 승인됐거나 다른 상태 — 존재는 확인됐으므로 409.
                raise ConfirmError(
                    409,
                    "document is not in %s (current=%s)"
                    % (_REQUIRED_FROM, locked.get("status")),
                )
            cur.execute(
                "SELECT requires_reviewer, requires_comment "
                "FROM runtime_state_transition_rule "
                "WHERE from_status = %s AND to_status = %s LIMIT 1",
                (_REQUIRED_FROM, _TARGET_STATUS),
            )
            rule = cur.fetchone()
            if not rule:
                raise ConfirmError(409, "transition rule not allowed")

            # 9. reviewer / comment 검증
            if rule.get("requires_reviewer") and not confirmed_by:
                raise ConfirmError(403, "reviewer required")
            if rule.get("requires_comment") and not (comment and str(comment).strip()):
                raise ConfirmError(422, "review_comment required")

            # 10. version 검증 (archive.document_version = int >= 1 계약)
            version = locked.get("version")
            if not isinstance(version, int) or isinstance(version, bool) or version < 1:
                raise ConfirmError(422, "document.version must be int >= 1")

            # 11~13. schema / field / checklist (같은 TX, 락 이후)
            schema_id = locked.get("form_schema_id")
            if not schema_id:
                raise ConfirmError(422, "document has no form_schema_id")
            cur.execute(
                "SELECT * FROM runtime_form_schema WHERE id = %s LIMIT 1", (schema_id,)
            )
            schema_row = cur.fetchone()
            if not schema_row:
                raise ConfirmError(422, "form schema not found")
            schema_row = dict(schema_row)
            cur.execute(
                "SELECT * FROM runtime_field WHERE form_schema_id = %s", (schema_id,)
            )
            fields = [dict(r) for r in (cur.fetchall() or [])]
            cur.execute(
                "SELECT * FROM runtime_checklist_item WHERE form_schema_id = %s",
                (schema_id,),
            )
            checklists = [dict(r) for r in (cur.fetchall() or [])]

            # runtime_data_json / evidence_links 정규화 (락 이후 값)
            runtime_values = _normalize_values(locked.get("runtime_data_json"))
            evidence_links = _normalize_evidence(locked.get("evidence_links"))

            # 14. 렌더 (05A) — 락 이후 값으로만
            render_doc = {
                "id": locked["id"],
                "form_schema_id": schema_id,
                "version": version,
                "runtime_data_json": runtime_values,
            }
            try:
                artifacts = build_render_artifacts(
                    document=render_doc,
                    schema=schema_row,
                    fields=fields,
                    checklists=checklists,
                )
            except SchemaRenderError as e:
                raise ConfirmError(422, "render failed: %s" % e)

            # 15. clock_timestamp() — 딱 1회. aware datetime 으로 반환됨.
            cur.execute("SELECT clock_timestamp() AS ts")
            confirmed_at = cur.fetchone()["ts"]

            # 16. Q4 hash — 같은 confirmed_at 사용
            try:
                snapshot_hash = compute_confirmed_snapshot_hash(
                    runtime_document_id=str(locked["id"]),
                    document_version=version,
                    snapshot_schema_version=_SNAPSHOT_SCHEMA_VERSION,
                    runtime_values_snapshot=runtime_values,
                    source_trace_snapshot=artifacts["source_trace_snapshot"],
                    template_identity=artifacts["template_identity"],
                    confirmed_at=confirmed_at,
                    confirmed_by=str(confirmed_by),
                    evidence_manifest=artifacts["evidence_manifest"],
                    rendered_body=artifacts["rendered_body"],
                )
            except SnapshotCanonicalizationError as e:
                raise ConfirmError(422, "snapshot hash failed: %s" % e)

            # 17. archive INSERT RETURNING id
            #     jsonb 컬럼은 명시적으로 json.dumps 하여 넘긴다(dict/list 직렬화 보장).
            cur.execute(
                """
                INSERT INTO runtime_document_archive (
                    runtime_document_id, runtime_values_snapshot, evidence_links_snapshot,
                    confirmed_at, confirmed_by, document_version, snapshot_schema_version,
                    source_trace_snapshot, rendered_body, evidence_manifest,
                    snapshot_hash, template_identity
                ) VALUES (
                    %s, %s::jsonb, %s::jsonb,
                    %s, %s, %s, %s,
                    %s::jsonb, %s, %s::jsonb,
                    %s, %s
                ) RETURNING id
                """,
                (
                    locked["id"],
                    json.dumps(runtime_values, ensure_ascii=False),
                    json.dumps(evidence_links, ensure_ascii=False),
                    confirmed_at,
                    confirmed_by,
                    version,
                    _SNAPSHOT_SCHEMA_VERSION,
                    json.dumps(artifacts["source_trace_snapshot"], ensure_ascii=False),
                    artifacts["rendered_body"],
                    json.dumps(artifacts["evidence_manifest"], ensure_ascii=False),
                    snapshot_hash,
                    artifacts["template_identity"],
                ),
            )
            archive_id = cur.fetchone()["id"]

            # 18. approval INSERT (snapshot_id = archive.id). snapshot_hash 중복 없음.
            cur.execute(
                """
                INSERT INTO runtime_document_approval (
                    runtime_document_id, reviewer_id, reviewed_at, review_action,
                    review_comment, snapshot_id, runtime_snapshot, evidence_snapshot,
                    source_trace_snapshot, rollback_available
                ) VALUES (
                    %s, %s, %s, 'APPROVE',
                    %s, %s, %s::jsonb, %s::jsonb,
                    %s::jsonb, true
                )
                """,
                (
                    locked["id"],
                    confirmed_by,
                    confirmed_at,
                    comment,
                    archive_id,
                    json.dumps(runtime_values, ensure_ascii=False),
                    json.dumps(evidence_links, ensure_ascii=False),
                    json.dumps(artifacts["source_trace_snapshot"], ensure_ascii=False),
                ),
            )

            # 19. status seal — 트랜잭션의 마지막 DML.
            #     trg_rdd_seal_guard: OLD.status=APPROVED_BY_HUMAN 이면 거부.
            #     현재 OLD.status=REVIEW_PENDING 이므로 통과, 이후 재-UPDATE 차단.
            cur.execute(
                """
                UPDATE runtime_document_data
                   SET status = %s, reviewed_by = %s, reviewed_at = %s,
                       review_comment = %s, updated_at = %s
                 WHERE id = %s
                RETURNING *
                """,
                (
                    _TARGET_STATUS, confirmed_by, confirmed_at,
                    comment, confirmed_at, locked["id"],
                ),
            )
            sealed = cur.fetchone()
            sealed = dict(sealed) if sealed else {}

        # 20. COMMIT
        conn.commit()

    except ConfirmError:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        # unique_violation = 중복 (runtime_document_id, document_version) → 409
        name = type(e).__name__
        if isinstance(e, pg_errors.UniqueViolation) or name == "UniqueViolation":
            raise ConfirmError(409, "duplicate confirmed snapshot version")
        # 락/문장 타임아웃, 교착, 일시적 DB 오류 → 503
        if isinstance(e, (pg_errors.LockNotAvailable, pg_errors.DeadlockDetected,
                          pg_errors.QueryCanceled, psycopg2.OperationalError)):
            raise ConfirmError(503, "database transient error")
        # 그 외 = 분류되지 않은 오류 → 500 (라우터가 매핑)
        raise ConfirmError(500, "unexpected error during confirm")
    finally:
        conn.close()

    # 21. COMMIT 성공 후 best-effort audit (트랜잭션 밖). 실패해도 confirm 유지.
    _best_effort_audit(doc_id, confirmed_by, locked, sealed)

    return sealed


def _best_effort_audit(doc_id, actor_id, before, after):
    """COMMIT 이후 감사 로그 1회. 실패는 무시(봉인은 이미 확정)."""
    try:
        from db.supabase_client import get_supabase
        from services.document_engine_svc import _audit
        _audit(get_supabase(), doc_id, "STATUS_CHANGE", actor_id, before, after)
    except Exception:
        pass
