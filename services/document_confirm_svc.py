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
from datetime import date as _date
from typing import Any, Dict, Optional

from services.document_confirm_authz import authorize_confirm
from services.document_attachment_svc import (
    AttachmentError,
    ALLOWED_IMAGE_MIME_TYPES,
    resolve_attachment_images_for_render,
    verify_file_snapshot_for_evidence,
)
from services.document_schema_renderer import (
    build_render_artifacts,
    SchemaRenderError,
)
from services.document_signature_svc import (
    SignatureError,
    resolve_signature_images_for_render,
    validate_required_signatures,
)
from services.document_snapshot_integrity import (
    compute_confirmed_snapshot_hash,
    SnapshotCanonicalizationError,
)


# ── 도메인 예외 (라우터가 HTTP 로 변환) ─────────────────────────────
class ConfirmError(Exception):
    """confirm 실패 도메인 예외. http_status 로 라우터가 매핑한다."""

    def __init__(self, http_status: int, detail: str):
        super().__init__(detail)
        self.http_status = http_status
        self.detail = detail


# ── APPROVE 대상 전이 ────────────────────────────────────────
_TARGET_STATUS = "APPROVED_BY_HUMAN"
_REQUIRED_FROM = "REVIEW_PENDING"
_SNAPSHOT_SCHEMA_VERSION = 1
_SCHEMA_STATUS_APPROVED = "APPROVED_FOR_RUNTIME_USE"
# Evidence 후보·필드 허용 상태 — DB CHECK 계약 (최신 main d219a3463855)
_ALLOWED_EVIDENCE_CANDIDATE_STATUSES: frozenset = frozenset({"APPROVED_BY_HUMAN"})
_ALLOWED_EVIDENCE_FIELD_STATUSES: frozenset = frozenset({"APPROVED_BY_HUMAN"})
# Evidence family 허용 목록 (SIGNATURE 추가 — WO-DOC260-OBJ10-G6-SIGNATURE-BATCH-001)
_ALLOWED_EVIDENCE_FAMILIES: frozenset = frozenset({"ATTACHMENT", "DATE", "REPORT_NUMBER", "MEASUREMENT", "PHOTO", "SIGNATURE"})
# family 식별자
_FILE_EVIDENCE_FAMILIES: frozenset = frozenset({"ATTACHMENT"})
_DATE_EVIDENCE_FAMILIES: frozenset = frozenset({"DATE"})
_REPORT_NUMBER_FAMILIES: frozenset = frozenset({"REPORT_NUMBER"})
_MEASUREMENT_FAMILIES: frozenset = frozenset({"MEASUREMENT"})
_PHOTO_FAMILIES: frozenset = frozenset({"PHOTO"})
_SIGNATURE_FAMILIES: frozenset = frozenset({"SIGNATURE"})
# upload_type 계약 — family별 독립 (E-01: 교차 조합 422 차단)
_ALLOWED_UPLOAD_TYPES: frozenset = frozenset({"attachment"})               # ATTACHMENT 전용
_DATE_UPLOAD_TYPES: frozenset = frozenset({"timestamp_auto"})              # DATE 전용
_REPORT_NUMBER_UPLOAD_TYPES: frozenset = frozenset({"inspector_identity"}) # REPORT_NUMBER 전용
_MEASUREMENT_UPLOAD_TYPES: frozenset = frozenset({"measurement_input"})    # MEASUREMENT 전용
_PHOTO_UPLOAD_TYPES: frozenset = frozenset({"image_upload"})               # PHOTO 전용
_SIGNATURE_UPLOAD_TYPES: frozenset = frozenset({"signature"})              # SIGNATURE 전용
# input_type 계약 — family별 독립 (E-01)
_FILE_EVIDENCE_INPUT_TYPES: frozenset = frozenset({"file"})
_DATE_EVIDENCE_INPUT_TYPES: frozenset = frozenset({"date"})
_REPORT_NUMBER_INPUT_TYPES: frozenset = frozenset({"text"})
_MEASUREMENT_INPUT_TYPES: frozenset = frozenset({"measurement", "date"})
_PHOTO_INPUT_TYPES: frozenset = frozenset({"image"})
_SIGNATURE_INPUT_TYPES: frozenset = frozenset({"signature"})
_MEASUREMENT_OPTIONAL_STATUS: str = "NOT_REQUIRED"   # runtime_field.required_status — 선택 입력
_PHOTO_OPTIONAL_STATUS: str = "NOT_REQUIRED"         # PHOTO 선택 필드 동일 계약
_SIGNATURE_OPTIONAL_STATUS: str = "NOT_REQUIRED"     # SIGNATURE 선택 필드 동일 계약


def _verify_date_evidence_value(
    *,
    date_value: Any,
    ev_field_id: str,
    field_key: str,
) -> None:
    """DATE 증적 필드 값 검증. FAIL-CLOSED.

    YYYY-MM-DD 형식 + 실달력 유효성 검증.
    fromisoformat()은 Python 3.11+ 에서 "20261015" (YYYYMMDD) 도 허용하므로
    형식 사전 검증을 먼저 수행한다 (R2-03 / R3-04).
    """
    if date_value is None:
        raise ConfirmError(
            422,
            f"evidence field {ev_field_id!r}: "
            f"date value missing in runtime_data_json[{field_key!r}]",
        )
    if not isinstance(date_value, str):
        raise ConfirmError(
            422,
            f"evidence field {ev_field_id!r}: "
            f"date value must be str, got {type(date_value).__name__!r}",
        )
    if len(date_value) != 10 or date_value[4] != "-" or date_value[7] != "-":
        raise ConfirmError(
            422,
            f"evidence field {ev_field_id!r}: "
            f"date value {date_value!r} must be strictly YYYY-MM-DD format",
        )
    try:
        _date.fromisoformat(date_value)
    except ValueError:
        raise ConfirmError(
            422,
            f"evidence field {ev_field_id!r}: "
            f"date value {date_value!r} is not a valid calendar date",
        )


def _verify_measurement_value(
    *,
    measurement_value: Any,
    ev_field_id: str,
    field_key: str,
) -> None:
    """MEASUREMENT 증적 필드 값 검증 (measurement input_type 전용). FAIL-CLOSED.

    비어있지 않은 문자열(str) 타입 검증.
    수치·텍스트 모두 str로 저장되므로 Number 강제 변환 없음 (WO-DOC260-P0E-MEASUREMENT-001 계약).
    """
    if measurement_value is None:
        raise ConfirmError(
            422,
            f"evidence field {ev_field_id!r}: "
            f"MEASUREMENT value missing in runtime_data_json[{field_key!r}]",
        )
    if not isinstance(measurement_value, str):
        raise ConfirmError(
            422,
            f"evidence field {ev_field_id!r}: "
            f"MEASUREMENT value must be str, got {type(measurement_value).__name__!r}",
        )
    if not measurement_value.strip():
        raise ConfirmError(
            422,
            f"evidence field {ev_field_id!r}: "
            f"MEASUREMENT value in runtime_data_json[{field_key!r}] is blank",
        )


def _verify_image_snapshot_for_evidence(
    *,
    snapshot: Any,
    field_id: str,
    field_key: str,
    ev_field_id: str,
    attachment_images: Dict[str, str],
) -> None:
    """PHOTO 증적 image snapshot 경량 검증. FAIL-CLOSED.

    Step 14a-1 (resolve_attachment_images_for_render strict=True) 검증 결과를 신뢰.
    Storage 재다운로드·SHA256 재계산 없음.
    추가로 확인: _type·field binding·MIME 4종·step 14a-1 통과 여부.
    """
    if not isinstance(snapshot, dict) or snapshot.get("_type") != "file_snapshot":
        raise ConfirmError(
            422,
            f"evidence field {ev_field_id!r}: PHOTO snapshot malformed "
            f"in runtime_data_json[{field_key!r}]",
        )
    if snapshot.get("field_key") != field_key:
        raise ConfirmError(
            422,
            f"evidence field {ev_field_id!r}: PHOTO snapshot field_key mismatch "
            f"snap={snapshot.get('field_key')!r} expected={field_key!r}",
        )
    snap_field_id = str(snapshot.get("field_id") or "")
    if snap_field_id != field_id:
        raise ConfirmError(
            422,
            f"evidence field {ev_field_id!r}: PHOTO snapshot field_id mismatch "
            f"snap={snap_field_id!r} expected={field_id!r}",
        )
    mime_type = str(snapshot.get("mime_type") or "")
    if mime_type not in ALLOWED_IMAGE_MIME_TYPES:
        raise ConfirmError(
            422,
            f"evidence field {ev_field_id!r}: PHOTO snapshot mime_type={mime_type!r} "
            f"not in image allowlist (JPEG/PNG/GIF/WebP only)",
        )
    # Step 14a-1이 해당 필드를 검증·해석했어야 함 — 결과에 없으면 차단
    if field_key not in attachment_images:
        raise ConfirmError(
            422,
            f"evidence field {ev_field_id!r}: PHOTO snapshot field_key={field_key!r} "
            f"not verified by image resolver (step 14a-1) — confirm blocked",
        )


def _verify_signature_snapshot_for_evidence(
    *,
    snapshot: Any,
    field_id: str,
    field_key: str,
    ev_field_id: str,
    signature_images: Dict[str, str],
) -> None:
    """SIGNATURE 증적 signature_snapshot 경량 검증. FAIL-CLOSED.

    Step 14a (resolve_signature_images_for_render) 검증 결과를 신뢰.
    Storage 재다운로드·SHA256 재계산·PNG 재검증 없음.
    추가로 확인: _type·field binding·step 14a 통과 여부.
    """
    if not isinstance(snapshot, dict) or snapshot.get("_type") != "signature_snapshot":
        raise ConfirmError(
            422,
            f"evidence field {ev_field_id!r}: SIGNATURE snapshot malformed "
            f"in runtime_data_json[{field_key!r}]",
        )
    if snapshot.get("field_key") != field_key:
        raise ConfirmError(
            422,
            f"evidence field {ev_field_id!r}: SIGNATURE snapshot field_key mismatch "
            f"snap={snapshot.get('field_key')!r} expected={field_key!r}",
        )
    snap_field_id = str(snapshot.get("field_id") or "")
    if snap_field_id != field_id:
        raise ConfirmError(
            422,
            f"evidence field {ev_field_id!r}: SIGNATURE snapshot field_id mismatch "
            f"snap={snap_field_id!r} expected={field_id!r}",
        )
    # Step 14a가 해당 필드를 검증·해석했어야 함 — 결과에 없으면 차단
    if field_key not in signature_images:
        raise ConfirmError(
            422,
            f"evidence field {ev_field_id!r}: SIGNATURE field_key={field_key!r} "
            f"not verified by signature resolver (step 14a) — confirm blocked",
        )


def _verify_report_number_value(
    *,
    text_value: Any,
    ev_field_id: str,
    field_key: str,
) -> None:
    """REPORT_NUMBER 증적 필드 값 검증. FAIL-CLOSED.

    실제 문자열(str) 타입 + 비어있지 않음 검증.
    숫자·배열·객체·None·공백 전용 문자열 모두 차단 (R1-03-D).
    """
    if text_value is None:
        raise ConfirmError(
            422,
            f"evidence field {ev_field_id!r}: "
            f"REPORT_NUMBER value missing in runtime_data_json[{field_key!r}]",
        )
    if not isinstance(text_value, str):
        raise ConfirmError(
            422,
            f"evidence field {ev_field_id!r}: "
            f"REPORT_NUMBER value must be str, got {type(text_value).__name__!r}",
        )
    if not text_value.strip():
        raise ConfirmError(
            422,
            f"evidence field {ev_field_id!r}: "
            f"REPORT_NUMBER value must not be empty or whitespace-only "
            f"in runtime_data_json[{field_key!r}]",
        )


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


def _resolve_evidence_connections(cur, evidence_fields, fields, schema_id, schema_candidate_id: str = ""):
    """FK-based Evidence↔Field resolution (WO-024 C1 contract).

    For each runtime_evidence_field row:
      evidence_candidate_id → evidence_field_candidate.id
      evidence_field_candidate.field_candidate_id → runtime_field.field_candidate_id
    Validates:
      - runtime_evidence_field.status allowlist (R2-01)
      - evidence_family / upload_type allowlist (R2-03)
      - evidence_field_candidate.schema_candidate_id == schema_candidate_id (R2-C2)
      - exactly 1 matching runtime_field per evidence_field
      - form_schema_id consistency
      - evidence_field_candidate.status (CANDIDATE → LEGAL_REQUIREDNESS=UNKNOWN)
    Returns list of dicts: {evidence_field, runtime_field, ev_candidate_status}
    Raises ConfirmError(422) on any FK or cardinality failure.
    """
    if not evidence_fields:
        return []
    field_by_candidate = {
        str(f.get("field_candidate_id") or ""): f
        for f in fields
        if f.get("field_candidate_id")
    }
    connections = []
    for ev in evidence_fields:
        ev_id = str(ev.get("id") or "")
        ev_status = str(ev.get("status") or "UNKNOWN")
        if ev_status not in _ALLOWED_EVIDENCE_FIELD_STATUSES:
            raise ConfirmError(
                422,
                f"evidence field {ev_id!r}: runtime_evidence_field.status={ev_status!r} "
                f"not approved — only {sorted(_ALLOWED_EVIDENCE_FIELD_STATUSES)} allowed",
            )
        ev_family = str(ev.get("evidence_family") or "")
        if ev_family not in _ALLOWED_EVIDENCE_FAMILIES:
            raise ConfirmError(
                422,
                f"evidence field {ev_id!r}: evidence_family={ev_family!r} not supported "
                f"(allowed: {sorted(_ALLOWED_EVIDENCE_FAMILIES)})",
            )
        # upload_type — family별 독립 검증 (E-01: 교차 조합 422 차단)
        ev_upload_type = str(ev.get("upload_type") or "")
        if ev_family in _FILE_EVIDENCE_FAMILIES:
            if ev_upload_type not in _ALLOWED_UPLOAD_TYPES:
                raise ConfirmError(
                    422,
                    f"evidence field {ev_id!r}: upload_type={ev_upload_type!r} not supported "
                    f"for ATTACHMENT family (allowed: {sorted(_ALLOWED_UPLOAD_TYPES)})",
                )
        elif ev_family in _DATE_EVIDENCE_FAMILIES:
            if ev_upload_type not in _DATE_UPLOAD_TYPES:
                raise ConfirmError(
                    422,
                    f"evidence field {ev_id!r}: upload_type={ev_upload_type!r} not supported "
                    f"for DATE family (allowed: {sorted(_DATE_UPLOAD_TYPES)})",
                )
        elif ev_family in _REPORT_NUMBER_FAMILIES:
            if ev_upload_type not in _REPORT_NUMBER_UPLOAD_TYPES:
                raise ConfirmError(
                    422,
                    f"evidence field {ev_id!r}: upload_type={ev_upload_type!r} not supported "
                    f"for REPORT_NUMBER family (allowed: {sorted(_REPORT_NUMBER_UPLOAD_TYPES)})",
                )
        elif ev_family in _MEASUREMENT_FAMILIES:
            if ev_upload_type not in _MEASUREMENT_UPLOAD_TYPES:
                raise ConfirmError(
                    422,
                    f"evidence field {ev_id!r}: upload_type={ev_upload_type!r} not supported "
                    f"for MEASUREMENT family (allowed: {sorted(_MEASUREMENT_UPLOAD_TYPES)})",
                )
        elif ev_family in _PHOTO_FAMILIES:
            if ev_upload_type not in _PHOTO_UPLOAD_TYPES:
                raise ConfirmError(
                    422,
                    f"evidence field {ev_id!r}: upload_type={ev_upload_type!r} not supported "
                    f"for PHOTO family (allowed: {sorted(_PHOTO_UPLOAD_TYPES)})",
                )
        elif ev_family in _SIGNATURE_FAMILIES:
            if ev_upload_type not in _SIGNATURE_UPLOAD_TYPES:
                raise ConfirmError(
                    422,
                    f"evidence field {ev_id!r}: upload_type={ev_upload_type!r} not supported "
                    f"for SIGNATURE family (allowed: {sorted(_SIGNATURE_UPLOAD_TYPES)})",
                )
        evidence_candidate_id = str(ev.get("evidence_candidate_id") or "")
        if not evidence_candidate_id:
            raise ConfirmError(
                422,
                f"evidence field {ev_id!r}: evidence_candidate_id missing — FK path broken",
            )
        cur.execute(
            "SELECT id, field_candidate_id, status, schema_candidate_id "
            "FROM evidence_field_candidate WHERE id = %s LIMIT 1",
            (evidence_candidate_id,),
        )
        efc_row = cur.fetchone()
        if not efc_row:
            raise ConfirmError(
                422,
                f"evidence field {ev_id!r}: evidence_field_candidate "
                f"{evidence_candidate_id!r} not found",
            )
        efc = dict(efc_row)
        # R2-C2: evidence_field_candidate.schema_candidate_id must match runtime_form_schema
        if schema_candidate_id:
            efc_sc_id = str(efc.get("schema_candidate_id") or "")
            if efc_sc_id != schema_candidate_id:
                raise ConfirmError(
                    422,
                    f"evidence field {ev_id!r}: schema candidate mismatch — "
                    f"evidence_field_candidate.schema_candidate_id={efc_sc_id!r} != "
                    f"runtime_form_schema.schema_candidate_id={schema_candidate_id!r}",
                )
        field_candidate_id = str(efc.get("field_candidate_id") or "")
        if not field_candidate_id:
            raise ConfirmError(
                422,
                f"evidence field {ev_id!r}: field_candidate_id missing in "
                f"evidence_field_candidate {evidence_candidate_id!r}",
            )
        matched = field_by_candidate.get(field_candidate_id)
        if matched is None:
            raise ConfirmError(
                422,
                f"evidence field {ev_id!r}: no runtime_field with "
                f"field_candidate_id={field_candidate_id!r} in schema {schema_id!r}",
            )
        # Cardinality: detect ambiguity (should be caught by DB UNIQUE, but guard anyway)
        ambiguous = [
            f for f in fields
            if str(f.get("field_candidate_id") or "") == field_candidate_id
        ]
        if len(ambiguous) > 1:
            raise ConfirmError(
                422,
                f"evidence field {ev_id!r}: ambiguous — "
                f"{len(ambiguous)} fields share field_candidate_id={field_candidate_id!r}",
            )
        connections.append({
            "evidence_field": ev,
            "runtime_field": matched,
            "ev_candidate_status": str(efc.get("status") or "UNKNOWN"),
            "ev_family": ev_family,
        })
    return connections


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
            # R1-03-A: Runtime Schema 반드시 APPROVED_FOR_RUNTIME_USE (봉인 경로)
            if schema_row.get("status") != _SCHEMA_STATUS_APPROVED:
                raise ConfirmError(
                    422,
                    f"runtime schema not approved for sealing "
                    f"(schema_id={schema_id!r}, status={schema_row.get('status')!r})"
                )
            cur.execute(
                "SELECT * FROM runtime_field WHERE form_schema_id = %s", (schema_id,)
            )
            fields = [dict(r) for r in (cur.fetchall() or [])]
            # R1-03-B: CANDIDATE_ONLY 필드 있으면 봉인 차단 (LEG 미승인)
            candidate_only = [f for f in fields if f.get("required_status") == "CANDIDATE_ONLY"]
            if candidate_only:
                keys = ", ".join(f.get("field_key") or f.get("id", "?") for f in candidate_only[:3])
                raise ConfirmError(
                    422,
                    f"form schema has {len(candidate_only)} CANDIDATE_ONLY field(s): {keys} "
                    f"— confirm blocked until fields are promoted"
                )
            cur.execute(
                "SELECT * FROM runtime_checklist_item WHERE form_schema_id = %s",
                (schema_id,),
            )
            checklists = [dict(r) for r in (cur.fetchall() or [])]

            # 13.5. runtime_evidence_field 조회 + FK 연결 검증
            cur.execute(
                "SELECT * FROM runtime_evidence_field WHERE form_schema_id = %s",
                (schema_id,),
            )
            evidence_fields = [dict(r) for r in (cur.fetchall() or [])]

            # runtime_data_json / evidence_links 정규화 (락 이후 값)
            runtime_values = _normalize_values(locked.get("runtime_data_json"))
            evidence_links = _normalize_evidence(locked.get("evidence_links"))

            # 14a. Signature resolution — downloads immutable document snapshots from Storage
            #       Runs inside transaction to use lock-verified runtime_values.
            #       I/O is Supabase Storage (HTTP), separate from psycopg2 connection.

            # 14a-pre. CORR-05: required signature pre-check (before Storage I/O)
            try:
                validate_required_signatures(runtime_values, fields)
            except SignatureError as e:
                raise ConfirmError(422, "required signature missing: %s" % e)

            try:
                sig_result = resolve_signature_images_for_render(
                    runtime_data_json=runtime_values,
                    fields=fields,
                    document_id=str(locked["id"]),
                )
            except SignatureError as e:
                raise ConfirmError(422, "signature resolution failed: %s" % e)

            # 14a-1. Attachment image resolution — strict=True (fail-close for sealing)
            try:
                attachment_images = resolve_attachment_images_for_render(
                    runtime_data_json=runtime_values,
                    fields=fields,
                    document_id=str(locked["id"]),
                    strict=True,
                )
            except AttachmentError as e:
                raise ConfirmError(422, "attachment image resolution failed: %s" % e)

            # 14a-2. Evidence FK 연결 + 검증 (OD-C023-01/02/05 / Gate A)
            schema_candidate_id = str(schema_row.get("schema_candidate_id") or "")
            ev_connections = _resolve_evidence_connections(
                cur, evidence_fields, fields, schema_id, schema_candidate_id
            )
            attachment_evidence_manifest: list = []
            date_evidence_manifest: list = []
            report_number_evidence_manifest: list = []
            measurement_evidence_manifest: list = []
            photo_evidence_manifest: list = []
            signature_evidence_manifest: list = []
            # R2-01: step 14a 기검증 manifest 항목 조회 — 출처(type/source) 보존용
            _sig_manifest_by_key: Dict[str, Dict] = {
                e.get("field_key", ""): e
                for e in (sig_result.get("manifest") or [])
                if e.get("field_key")
            }
            for ev_conn in ev_connections:
                ev_field = ev_conn["evidence_field"]
                rf = ev_conn["runtime_field"]
                ev_candidate_status = ev_conn["ev_candidate_status"]
                ev_family = ev_conn["ev_family"]
                # R1-02: candidate status — family 공통
                if ev_candidate_status not in _ALLOWED_EVIDENCE_CANDIDATE_STATUSES:
                    raise ConfirmError(
                        422,
                        f"evidence legal status not approved "
                        f"(evidence_field={str(ev_field.get('id'))!r}, "
                        f"evidence_candidate_status={ev_candidate_status!r}) — "
                        f"only {sorted(_ALLOWED_EVIDENCE_CANDIDATE_STATUSES)} allowed; "
                        "confirm blocked until evidence approval gate passes",
                    )
                field_id = str(rf.get("id") or "")
                field_key = str(rf.get("field_key") or "")
                input_type = str(rf.get("input_type") or "")

                if ev_family in _FILE_EVIDENCE_FAMILIES:
                    # E-01: ATTACHMENT — input_type must be file
                    if input_type not in _FILE_EVIDENCE_INPUT_TYPES:
                        raise ConfirmError(
                            422,
                            f"evidence field {str(ev_field.get('id'))!r}: "
                            f"connected field input_type={input_type!r} not valid "
                            f"for ATTACHMENT family (expected: file)",
                        )
                    snap = runtime_values.get(field_key)
                    if snap is None:
                        raise ConfirmError(
                            422,
                            f"evidence field {str(ev_field.get('id'))!r}: "
                            f"FileSnapshot missing in runtime_data_json[{field_key!r}]",
                        )
                    try:
                        manifest_entry = verify_file_snapshot_for_evidence(
                            snapshot=snap,
                            document_id=str(locked["id"]),
                            field_id=field_id,
                            field_key=field_key,
                        )
                    except AttachmentError as e:
                        raise ConfirmError(422, f"evidence verification failed: {e}")
                    manifest_entry["evidence_field_id"] = str(ev_field.get("id") or "")
                    attachment_evidence_manifest.append(manifest_entry)

                elif ev_family in _DATE_EVIDENCE_FAMILIES:
                    # E-01: DATE — input_type must be date
                    if input_type not in _DATE_EVIDENCE_INPUT_TYPES:
                        raise ConfirmError(
                            422,
                            f"evidence field {str(ev_field.get('id'))!r}: "
                            f"connected field input_type={input_type!r} not valid "
                            f"for DATE family (expected: date)",
                        )
                    date_value = runtime_values.get(field_key)
                    _verify_date_evidence_value(
                        date_value=date_value,
                        ev_field_id=str(ev_field.get("id") or ""),
                        field_key=field_key,
                    )
                    date_evidence_manifest.append({
                        "evidence_field_id":    str(ev_field.get("id") or ""),
                        "field_id":             field_id,
                        "field_key":            field_key,
                        "date_value":           str(date_value),
                        "value_source":         "USER_INPUT",
                        "value_semantic_class": "PENDING_CLASSIFICATION",
                        "evidence_family":      "DATE",
                        "input_type":           "date",
                    })

                elif ev_family in _REPORT_NUMBER_FAMILIES:
                    # E-01: REPORT_NUMBER — input_type must be text
                    if input_type not in _REPORT_NUMBER_INPUT_TYPES:
                        raise ConfirmError(
                            422,
                            f"evidence field {str(ev_field.get('id'))!r}: "
                            f"connected field input_type={input_type!r} not valid "
                            f"for REPORT_NUMBER family (expected: text)",
                        )
                    text_value = runtime_values.get(field_key)
                    _verify_report_number_value(
                        text_value=text_value,
                        ev_field_id=str(ev_field.get("id") or ""),
                        field_key=field_key,
                    )
                    report_number_evidence_manifest.append({
                        "evidence_field_id":    str(ev_field.get("id") or ""),
                        "field_id":             field_id,
                        "field_key":            field_key,
                        "text_value":           str(text_value),
                        "value_source":         "USER_INPUT",
                        "value_semantic_class": "REPORT_NUMBER",
                        "evidence_family":      "REPORT_NUMBER",
                        "input_type":           "text",
                    })

                elif ev_family in _MEASUREMENT_FAMILIES:
                    # E-01: MEASUREMENT — input_type must be measurement or date
                    if input_type not in _MEASUREMENT_INPUT_TYPES:
                        raise ConfirmError(
                            422,
                            f"evidence field {str(ev_field.get('id'))!r}: "
                            f"connected field input_type={input_type!r} not valid "
                            f"for MEASUREMENT family (expected: measurement or date)",
                        )
                    ev_id_str = str(ev_field.get("id") or "")
                    # R1: runtime_field.required_status 반영 — NOT_REQUIRED 선택 필드는 빈 값 허용
                    req_status = str(rf.get("required_status") or "")
                    is_optional = req_status == _MEASUREMENT_OPTIONAL_STATUS
                    if input_type == "date":
                        date_value = runtime_values.get(field_key)
                        if is_optional and (date_value is None or str(date_value).strip() == ""):
                            pass  # NOT_REQUIRED — 값 없으면 manifest 제외
                        else:
                            _verify_date_evidence_value(
                                date_value=date_value,
                                ev_field_id=ev_id_str,
                                field_key=field_key,
                            )
                            measurement_evidence_manifest.append({
                                "evidence_field_id":    ev_id_str,
                                "field_id":             field_id,
                                "field_key":            field_key,
                                "date_value":           str(date_value),
                                "value_source":         "USER_INPUT",
                                "value_semantic_class": "PENDING_CLASSIFICATION",
                                "evidence_family":      "MEASUREMENT",
                                "input_type":           "date",
                            })
                    else:
                        measurement_value = runtime_values.get(field_key)
                        if is_optional and (
                            measurement_value is None
                            or (isinstance(measurement_value, str) and not measurement_value.strip())
                        ):
                            pass  # NOT_REQUIRED — 값 없으면 manifest 제외
                        else:
                            _verify_measurement_value(
                                measurement_value=measurement_value,
                                ev_field_id=ev_id_str,
                                field_key=field_key,
                            )
                            measurement_evidence_manifest.append({
                                "evidence_field_id":    ev_id_str,
                                "field_id":             field_id,
                                "field_key":            field_key,
                                "text_value":           str(measurement_value),
                                "value_source":         "USER_INPUT",
                                "value_semantic_class": "MEASUREMENT",
                                "evidence_family":      "MEASUREMENT",
                                "input_type":           "measurement",
                            })

                elif ev_family in _PHOTO_FAMILIES:
                    # E-01: PHOTO — input_type must be image
                    if input_type not in _PHOTO_INPUT_TYPES:
                        raise ConfirmError(
                            422,
                            f"evidence field {str(ev_field.get('id'))!r}: "
                            f"connected field input_type={input_type!r} not valid "
                            f"for PHOTO family (expected: image)",
                        )
                    ev_id_str = str(ev_field.get("id") or "")
                    req_status = str(rf.get("required_status") or "")
                    is_optional = req_status == _PHOTO_OPTIONAL_STATUS
                    snap = runtime_values.get(field_key)
                    if is_optional and snap is None:
                        pass  # NOT_REQUIRED — 이미지 없으면 manifest 제외
                    else:
                        if snap is None:
                            raise ConfirmError(
                                422,
                                f"evidence field {ev_id_str!r}: PHOTO value missing "
                                f"in runtime_data_json[{field_key!r}]",
                            )
                        _verify_image_snapshot_for_evidence(
                            snapshot=snap,
                            field_id=field_id,
                            field_key=field_key,
                            ev_field_id=ev_id_str,
                            attachment_images=attachment_images,
                        )
                        photo_evidence_manifest.append({
                            "evidence_field_id":    ev_id_str,
                            "field_id":             field_id,
                            "field_key":            field_key,
                            "storage_ref":          str(snap.get("storage_ref") or ""),
                            "sha256":               str(snap.get("sha256") or ""),
                            "mime_type":            str(snap.get("mime_type") or ""),
                            "byte_size":            snap.get("byte_size"),
                            "value_source":         "USER_INPUT",
                            "value_semantic_class": "PHOTO",
                            "evidence_family":      "PHOTO",
                            "input_type":           "image",
                        })

                elif ev_family in _SIGNATURE_FAMILIES:
                    # E-01: SIGNATURE — input_type must be signature
                    if input_type not in _SIGNATURE_INPUT_TYPES:
                        raise ConfirmError(
                            422,
                            f"evidence field {str(ev_field.get('id'))!r}: "
                            f"connected field input_type={input_type!r} not valid "
                            f"for SIGNATURE family (expected: signature)",
                        )
                    ev_id_str = str(ev_field.get("id") or "")
                    req_status = str(rf.get("required_status") or "")
                    is_optional = req_status == _SIGNATURE_OPTIONAL_STATUS
                    snap = runtime_values.get(field_key)
                    if is_optional and snap is None:
                        pass  # NOT_REQUIRED — 서명 없으면 manifest 제외
                    else:
                        if snap is None:
                            raise ConfirmError(
                                422,
                                f"evidence field {ev_id_str!r}: SIGNATURE value missing "
                                f"in runtime_data_json[{field_key!r}]",
                            )
                        _verify_signature_snapshot_for_evidence(
                            snapshot=snap,
                            field_id=field_id,
                            field_key=field_key,
                            ev_field_id=ev_id_str,
                            signature_images=sig_result.get("images") or {},
                        )
                        # R2-01: step 14a 기검증 manifest 항목 재사용 — type·source 보존
                        # _verify_signature_snapshot_for_evidence() 통과 = field_key가 sig_result["images"]에 존재
                        # → _sig_manifest_by_key[field_key]도 반드시 존재 (resolve_signature_images_for_render 계약)
                        _base_sig = dict(_sig_manifest_by_key.get(field_key) or {})
                        signature_evidence_manifest.append({
                            **_base_sig,                        # type, source, signer_user_id, signed_at, storage_ref, sha256, mime_type, byte_size 보존
                            "field_id":             field_id,   # _base_sig 없을 때도 보장
                            "field_key":            field_key,  # _base_sig 없을 때도 보장 (_sig_ev_keys 계산에 필요)
                            "evidence_field_id":    ev_id_str,
                            "evidence_family":      "SIGNATURE",
                            "value_semantic_class": "SIGNATURE",
                            "input_type":           "signature",
                        })

            # 14a-3. manifest 병합 (clock_timestamp() 호출 전 — Step 순서 보존)
            combined_evidence_manifest = (
                attachment_evidence_manifest
                + date_evidence_manifest
                + report_number_evidence_manifest
                + measurement_evidence_manifest
                + photo_evidence_manifest
                + signature_evidence_manifest
            )

            # 14a-4. Signature manifest 중복 제거 (R1 — WO-DOC260-OBJ10-G6-SIGNATURE-BATCH-001)
            # build_render_artifacts는 signature_manifest + attachment_evidence_manifest를
            # evidence_manifest로 합산한다. SIGNATURE evidence가 있는 field_key는
            # combined_evidence_manifest 경로로 이미 기록되므로 render 경로(sig_result["manifest"])
            # 에서 제외해 이중 기록을 막는다.
            _sig_ev_keys = frozenset(e["field_key"] for e in signature_evidence_manifest)
            filtered_sig_manifest = [
                entry for entry in (sig_result.get("manifest") or [])
                if entry.get("field_key") not in _sig_ev_keys
            ]

            # 14b. 렌더 (05A) — 락 이후 값으로만, 서명 + 첨부 이미지 inline 포함
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
                    signature_images=sig_result.get("images"),
                    signature_manifest=filtered_sig_manifest,
                    attachment_images=attachment_images,
                    attachment_evidence_manifest=combined_evidence_manifest,
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
            if not sealed:
                # FOR UPDATE 로 잠근 행이 seal UPDATE 에서 사라졌다면 무결성 위반.
                # 조용히 빈 커밋하지 않고 롤백(아래 except 에서 500).
                raise RuntimeError("seal update returned no row")
            sealed = dict(sealed)

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
