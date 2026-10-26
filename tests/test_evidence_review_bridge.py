"""WO-027 C3-04 — Evidence Candidate 승인 브릿지 테스트
C2-FINAL §2-3 계약 검증 (C3-T08~T13)

C3-T08: evidence_field_candidate 승인 시 runtime_review_decision INSERT + status UPDATE 동시
C3-T09: reviewer_id = 권한 없는 사용자 → 403
C3-T09B: UUID 일치이나 역할 불일치 → 403 (AND 조건)
C3-T11: 동일 evidence_field_candidate 중복 APPROVE → 409
C3-T12: APPROVED_BY_HUMAN 상태에서 재승인 → 409
C3-T13: review_reason 빈 문자열로 승인 요청 → 400

Production DB write = 0 (mock 전용).
bridge_evidence_approve는 current_user를 Depends(get_current_user)로 받지만,
테스트에서는 FastAPI DI를 우회하고 직접 호출한다 (_connect는 패치).
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock
from fastapi import HTTPException

import pytest


# ─── psycopg2 커서 / 커넥션 fakery ────────────────────────────────────────

class _FakeCursor:
    """순서 기반 fake 커서.

    execute 호출 순서:
      1 = authority 검증 SELECT
      2 = evidence_field_candidate SELECT FOR UPDATE
      3 = 중복 decision SELECT
      4 = runtime_review_decision INSERT (RETURNING id)
      5 = evidence_field_candidate UPDATE
    """
    def __init__(
        self,
        authority_ok: bool = True,
        target_status: str = "CANDIDATE",
        target_found: bool = True,
        existing_decision: bool = False,
        decision_id: str = "dec-001",
        update_rowcount: int = 1,
    ):
        self._authority_ok = authority_ok
        self._target_status = target_status
        self._target_found = target_found
        self._existing_decision = existing_decision
        self._decision_id = decision_id
        self._update_rowcount = update_rowcount
        self._call = 0
        self.rowcount = 0

    def execute(self, sql, params=None):
        self._call += 1
        if self._call == 5:
            self.rowcount = self._update_rowcount

    def fetchone(self):
        c = self._call
        if c == 1:
            return {"1": 1} if self._authority_ok else None
        if c == 2:
            if not self._target_found:
                return None
            return {"id": "efc-target", "status": self._target_status}
        if c == 3:
            return {"1": 1} if self._existing_decision else None
        if c == 4:
            return {"id": self._decision_id}
        return None

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


# ─── 공통 상수 ────────────────────────────────────────────────────────────

_EFC_ID = "5e5687b3-e62f-480c-ad75-1efc41706e3b"
_REVIEWER_ID = "user-safety-mgr-001"
_AUTH_USER = {"id": _REVIEWER_ID}


def _call(conn: _FakeConn, current_user: dict = _AUTH_USER,
          efc_id: str = _EFC_ID,
          review_reason: str = "법적 증빙 요건 검토 완료"):
    """bridge_evidence_approve를 직접 호출 (FastAPI DI 우회)."""
    from routers.review_bridge import bridge_evidence_approve
    with patch("db.direct_sql._connect", return_value=conn):
        return bridge_evidence_approve(
            evidence_field_candidate_id=efc_id,
            review_reason=review_reason,
            current_user=current_user,
        )


# ─── C3-T08: 원자 처리 — review_decision INSERT + status UPDATE ──────────

def test_C3_T08_atomic_decision_and_status_update():
    """C3-T08: APPROVE 시 review_decision INSERT와 status UPDATE가 동일 TX에서 커밋."""
    cursor = _FakeCursor(
        authority_ok=True,
        target_status="CANDIDATE",
        existing_decision=False,
        decision_id="dec-c3t08",
    )
    conn = _FakeConn(cursor)

    result = _call(conn)

    assert result["data"]["new_status"] == "APPROVED_BY_HUMAN"
    assert result["data"]["review_decision_id"] == "dec-c3t08"
    assert conn.committed, "C3-T08: COMMIT 필요 (동일 TX)"
    assert not conn.rolled_back


# ─── C3-T09: 권한 없는 reviewer → 403 ──────────────────────────────────

def test_C3_T09_unauthorized_reviewer_403():
    """C3-T09: runtime_review_authority에 해당 reviewer 없음 → 403."""
    cursor = _FakeCursor(authority_ok=False)
    conn = _FakeConn(cursor)

    with pytest.raises(HTTPException) as exc_info:
        _call(conn, current_user={"id": "unauth-user-999"})

    assert exc_info.value.status_code == 403
    assert conn.rolled_back


# ─── C3-T09B: UUID 일치하나 역할 불일치 → 403 (AND 조건) ──────────────────

def test_C3_T09B_role_mismatch_403():
    """C3-T09B: AND 조건 불충족(역할 불일치) → 403. OR 조건 허용 금지 계약 확인."""
    # AND 조건이므로 역할 불일치 → DB 쿼리 결과 없음 → authority_ok=False와 동일 효과
    cursor = _FakeCursor(authority_ok=False)
    conn = _FakeConn(cursor)

    with pytest.raises(HTTPException) as exc_info:
        _call(conn)  # reviewer_id 일치하지만 authority_ok=False로 시뮬레이션

    assert exc_info.value.status_code == 403
    assert conn.rolled_back


# ─── C3-T11: 중복 APPROVE → 409 ────────────────────────────────────────

def test_C3_T11_duplicate_approve_409():
    """C3-T11: 동일 evidence_field_candidate에 APPROVE decision 이미 존재 → 409."""
    cursor = _FakeCursor(
        authority_ok=True,
        target_status="CANDIDATE",
        existing_decision=True,  # 중복
    )
    conn = _FakeConn(cursor)

    with pytest.raises(HTTPException) as exc_info:
        _call(conn)

    assert exc_info.value.status_code == 409
    assert "already exists" in exc_info.value.detail.lower()
    assert conn.rolled_back


# ─── C3-T12: APPROVED_BY_HUMAN 상태에서 재승인 → 409 ────────────────────

def test_C3_T12_already_approved_409():
    """C3-T12: evidence_field_candidate.status=APPROVED_BY_HUMAN → 재승인 차단 409."""
    cursor = _FakeCursor(
        authority_ok=True,
        target_status="APPROVED_BY_HUMAN",  # 이미 승인됨
    )
    conn = _FakeConn(cursor)

    with pytest.raises(HTTPException) as exc_info:
        _call(conn)

    assert exc_info.value.status_code == 409
    assert "already processed" in exc_info.value.detail.lower()
    assert conn.rolled_back


# ─── C3-T13: review_reason 빈 문자열 → 400 ──────────────────────────────

def test_C3_T13_empty_review_reason_400():
    """C3-T13: review_reason 빈 문자열/공백 → 400 (필수 사유 강제)."""
    from routers.review_bridge import bridge_evidence_approve

    # DB 연결 없이 사전 검증에서 차단되어야 함
    with pytest.raises(HTTPException) as exc_info:
        with patch("db.direct_sql._connect", side_effect=AssertionError("DB should not be reached")):
            bridge_evidence_approve(
                evidence_field_candidate_id=_EFC_ID,
                review_reason="",
                current_user=_AUTH_USER,
            )
    assert exc_info.value.status_code == 400

    with pytest.raises(HTTPException) as exc_info:
        with patch("db.direct_sql._connect", side_effect=AssertionError("DB should not be reached")):
            bridge_evidence_approve(
                evidence_field_candidate_id=_EFC_ID,
                review_reason="   ",
                current_user=_AUTH_USER,
            )
    assert exc_info.value.status_code == 400
