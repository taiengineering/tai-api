"""WO-DOC260-POSTACT-P0E-B2-RUNTIME-APPROVAL-003
Runtime Evidence Field 사용 승인 브릿지 테스트

테스트 케이스:
  RT-T01: 정상 승인 — review_decision INSERT + ev.status UPDATE 원자 커밋
  RT-T02: role_code 불일치 → 403 (선제 검증, DB 미도달)
  RT-T03: runtime_review_authority 없음 → 403
  RT-T04: ev.status 이미 APPROVED_BY_HUMAN → 409
  RT-T05: efc.status CANDIDATE (선행 후보 승인 없음) → 409
  RT-T06: 선행 EVIDENCE APPROVE decision 없음 → 409
  RT-T07: runtime_form_schema 미승인 → 409
  RT-T08: field connection 없음 → 422
  RT-T09: 중복 RUNTIME_EVIDENCE_APPROVE → 409
  RT-T10: review_reason 빈 문자열 → 400
  RT-T11: 트랜잭션 실패 시 rollback

Production DB write = 0 (mock 전용).
"""
from __future__ import annotations

from unittest.mock import patch
from fastapi import HTTPException

import pytest

# ─── DB 쿼리 실행 순서 (FakeCursor 기준) ─────────────────────────────────
# 1: authority SELECT
# 2: runtime_evidence_field SELECT FOR UPDATE
# 3: evidence_field_candidate SELECT
# 4: 선행 EVIDENCE APPROVE decision SELECT
# 5: runtime_form_schema SELECT
# 6: runtime_field SELECT (fetchall)
# 7: 중복 RUNTIME_EVIDENCE_APPROVE decision SELECT
# 8: runtime_review_decision INSERT RETURNING id
# 9: runtime_evidence_field UPDATE (rowcount 확인)

_EV_ID = "fd3f3c99-62cd-4336-bf23-dda92a4b2a43"
_EFC_ID = "987c5b1f-099e-4941-abcc-0aa5fc2cb868"
_SCHEMA_ID = "3c09d127-84df-4ba6-92ff-7b7941c2b811"
_FIELD_ID = "b986d9a5-0a0b-4d76-8a84-4803c3faba8d"
_REVIEWER_ID = "user-safety-mgr-001"
_AUTH_USER = {"id": _REVIEWER_ID, "role_code": "003"}
_REASON = "법적 증빙 요건 검토 완료 — 화학물질관리법 시행규칙"


class _FakeCursor:
    """9단계 쿼리 순서 기반 fake 커서."""

    def __init__(
        self,
        authority_ok: bool = True,
        ev_found: bool = True,
        ev_status: str = "CANDIDATE",
        ev_family: str = "ATTACHMENT",
        ev_upload_type: str = "attachment",
        ev_candidate_id: str = _EFC_ID,
        efc_found: bool = True,
        efc_status: str = "APPROVED_BY_HUMAN",
        efc_field_candidate_id: str = "fk-field-cand-001",
        prior_approve_decision: bool = True,
        schema_found: bool = True,
        schema_status: str = "APPROVED_FOR_RUNTIME_USE",
        matched_fields: list | None = None,
        duplicate_runtime_decision: bool = False,
        decision_id: str = "dec-rt-001",
        update_rowcount: int = 1,
    ):
        self._authority_ok = authority_ok
        self._ev_found = ev_found
        self._ev_status = ev_status
        self._ev_family = ev_family
        self._ev_upload_type = ev_upload_type
        self._ev_candidate_id = ev_candidate_id
        self._efc_found = efc_found
        self._efc_status = efc_status
        self._efc_field_candidate_id = efc_field_candidate_id
        self._prior_approve_decision = prior_approve_decision
        self._schema_found = schema_found
        self._schema_status = schema_status
        self._matched_fields = matched_fields if matched_fields is not None else [
            {"id": _FIELD_ID, "input_type": "file"}
        ]
        self._duplicate_runtime_decision = duplicate_runtime_decision
        self._decision_id = decision_id
        self._update_rowcount = update_rowcount
        self._call = 0
        self.rowcount = 0

    def execute(self, sql, params=None):
        self._call += 1
        if self._call == 9:
            self.rowcount = self._update_rowcount

    def fetchone(self):
        c = self._call
        if c == 1:
            return {"1": 1} if self._authority_ok else None
        if c == 2:
            if not self._ev_found:
                return None
            return {
                "id": _EV_ID,
                "status": self._ev_status,
                "evidence_family": self._ev_family,
                "upload_type": self._ev_upload_type,
                "evidence_candidate_id": self._ev_candidate_id,
                "form_schema_id": _SCHEMA_ID,
            }
        if c == 3:
            if not self._efc_found:
                return None
            return {
                "id": _EFC_ID,
                "status": self._efc_status,
                "field_candidate_id": self._efc_field_candidate_id,
            }
        if c == 4:
            return {"1": 1} if self._prior_approve_decision else None
        if c == 5:
            if not self._schema_found:
                return None
            return {"id": _SCHEMA_ID, "status": self._schema_status}
        if c == 7:
            return {"1": 1} if self._duplicate_runtime_decision else None
        if c == 8:
            return {"id": self._decision_id}
        return None

    def fetchall(self):
        if self._call == 6:
            return self._matched_fields
        return []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


class _FakeConn:
    def __init__(self, cursor: _FakeCursor):
        self._cursor = cursor
        self.autocommit = True
        self.committed = False
        self.rolled_back = False

    def cursor(self, cursor_factory=None):
        return self._cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


def _call(
    conn: _FakeConn,
    current_user: dict = _AUTH_USER,
    ev_id: str = _EV_ID,
    reason: str = _REASON,
):
    from routers.review_bridge import bridge_evidence_runtime_approve
    with patch("db.direct_sql._connect", return_value=conn):
        return bridge_evidence_runtime_approve(
            runtime_evidence_field_id=ev_id,
            review_reason=reason,
            current_user=current_user,
        )


# ─── RT-T01: 정상 승인 ────────────────────────────────────────────────────

def test_RT_T01_success_atomic_commit():
    """RT-T01: 정상 승인 — review_decision INSERT + ev.status UPDATE 원자 커밋."""
    conn = _FakeConn(_FakeCursor(decision_id="dec-rt-t01"))

    result = _call(conn)

    assert result["data"]["new_status"] == "APPROVED_BY_HUMAN"
    assert result["data"]["review_decision_id"] == "dec-rt-t01"
    assert result["data"]["runtime_evidence_field_id"] == _EV_ID
    assert conn.committed
    assert not conn.rolled_back


# ─── RT-T02: role_code 불일치 → 403 ──────────────────────────────────────

def test_RT_T02_role_code_mismatch_403():
    """RT-T02: role_code가 SAFETY_MANAGER 아님 → DB 미도달 선제 차단 403."""
    conn = _FakeConn(_FakeCursor())

    with pytest.raises(HTTPException) as exc_info:
        _call(conn, current_user={"id": _REVIEWER_ID, "role_code": "004"})

    assert exc_info.value.status_code == 403
    assert not conn.rolled_back  # DB 연결 전 차단


# ─── RT-T03: authority 없음 → 403 ────────────────────────────────────────

def test_RT_T03_authority_not_found_403():
    """RT-T03: runtime_review_authority에 해당 사용자 없음 → 403."""
    conn = _FakeConn(_FakeCursor(authority_ok=False))

    with pytest.raises(HTTPException) as exc_info:
        _call(conn)

    assert exc_info.value.status_code == 403
    assert conn.rolled_back


# ─── RT-T04: ev.status 이미 APPROVED_BY_HUMAN → 409 ─────────────────────

def test_RT_T04_ev_already_approved_409():
    """RT-T04: runtime_evidence_field.status=APPROVED_BY_HUMAN → 재승인 차단 409."""
    conn = _FakeConn(_FakeCursor(ev_status="APPROVED_BY_HUMAN"))

    with pytest.raises(HTTPException) as exc_info:
        _call(conn)

    assert exc_info.value.status_code == 409
    assert "already processed" in exc_info.value.detail.lower()
    assert conn.rolled_back


# ─── RT-T05: 선행 후보 승인 없음 (efc.status=CANDIDATE) → 409 ───────────

def test_RT_T05_efc_not_approved_409():
    """RT-T05: evidence_field_candidate.status=CANDIDATE → 선행 승인 없음 409."""
    conn = _FakeConn(_FakeCursor(efc_status="CANDIDATE"))

    with pytest.raises(HTTPException) as exc_info:
        _call(conn)

    assert exc_info.value.status_code == 409
    assert "not yet approved" in exc_info.value.detail.lower()
    assert conn.rolled_back


# ─── RT-T06: 선행 EVIDENCE APPROVE decision 없음 → 409 ──────────────────

def test_RT_T06_no_prior_approve_decision_409():
    """RT-T06: 선행 EVIDENCE APPROVE decision 미존재 → 감사 이력 누락 409."""
    conn = _FakeConn(_FakeCursor(prior_approve_decision=False))

    with pytest.raises(HTTPException) as exc_info:
        _call(conn)

    assert exc_info.value.status_code == 409
    assert "audit trail missing" in exc_info.value.detail.lower()
    assert conn.rolled_back


# ─── RT-T07: runtime_form_schema 미승인 → 409 ───────────────────────────

def test_RT_T07_schema_not_approved_409():
    """RT-T07: runtime_form_schema.status=CANDIDATE → 409."""
    conn = _FakeConn(_FakeCursor(schema_status="CANDIDATE"))

    with pytest.raises(HTTPException) as exc_info:
        _call(conn)

    assert exc_info.value.status_code == 409
    assert "not approved for runtime use" in exc_info.value.detail.lower()
    assert conn.rolled_back


# ─── RT-T08: field connection 없음 → 422 ─────────────────────────────────

def test_RT_T08_no_field_connection_422():
    """RT-T08: 연결 runtime_field 없음 (0건) → 422."""
    conn = _FakeConn(_FakeCursor(matched_fields=[]))

    with pytest.raises(HTTPException) as exc_info:
        _call(conn)

    assert exc_info.value.status_code == 422
    assert "connection broken" in exc_info.value.detail.lower()
    assert conn.rolled_back


# ─── RT-T09: 중복 RUNTIME_EVIDENCE_APPROVE → 409 ─────────────────────────

def test_RT_T09_duplicate_runtime_approve_409():
    """RT-T09: 동일 runtime_evidence_field에 RUNTIME_EVIDENCE_APPROVE 이미 존재 → 409."""
    conn = _FakeConn(_FakeCursor(duplicate_runtime_decision=True))

    with pytest.raises(HTTPException) as exc_info:
        _call(conn)

    assert exc_info.value.status_code == 409
    assert "already exists" in exc_info.value.detail.lower()
    assert conn.rolled_back


# ─── RT-T10: review_reason 비어있음 → 400 ────────────────────────────────

def test_RT_T10_empty_review_reason_400():
    """RT-T10: review_reason 빈 문자열 / 공백 → 400 (DB 미도달)."""
    from routers.review_bridge import bridge_evidence_runtime_approve

    for bad_reason in ("", "   "):
        with pytest.raises(HTTPException) as exc_info:
            with patch("db.direct_sql._connect", side_effect=AssertionError("DB should not be reached")):
                bridge_evidence_runtime_approve(
                    runtime_evidence_field_id=_EV_ID,
                    review_reason=bad_reason,
                    current_user=_AUTH_USER,
                )
        assert exc_info.value.status_code == 400


# ─── RT-T11: 트랜잭션 실패 → rollback ───────────────────────────────────

def test_RT_T11_unexpected_exception_rollback():
    """RT-T11: UPDATE rowcount=0 (concurrent modification) → 409 + rollback."""
    conn = _FakeConn(_FakeCursor(update_rowcount=0))

    with pytest.raises(HTTPException) as exc_info:
        _call(conn)

    assert exc_info.value.status_code == 409
    assert "concurrent modification" in exc_info.value.detail.lower()
    assert conn.rolled_back
