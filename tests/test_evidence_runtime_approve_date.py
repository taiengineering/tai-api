"""WO-DOC260-DATE-GATE-B WP-G-B01 — DATE family runtime approve 테스트 (G-B01 해소)

G-B01: evidence-runtime-approve가 DATE family를 차단하던 버그를 수정한 후
DATE family 경로가 올바르게 동작하는지 검증한다.

테스트 케이스:
  DT-T01: DATE family 정상 승인 — review_decision INSERT + ev.status UPDATE 원자 커밋
  DT-T02: DATE family + upload_type=attachment (교차 조합) → 422
  DT-T03: DATE family + upload_type=timestamp_auto + input_type=file (교차 조합) → 422
  DT-T04: ATTACHMENT family + upload_type=timestamp_auto (교차 조합) → 422
  DT-T05: ATTACHMENT family 기존 경로 회귀 없음 — 정상 승인
  DT-T06: 미지원 evidence_family → 422
  DT-T07: DATE family Allowlist 미등록 ID → 403 (DB 미도달)

Production DB write = 0 (mock 전용).
"""
from __future__ import annotations

from unittest.mock import patch
from fastapi import HTTPException

import pytest

# ─── 테스트 상수 ──────────────────────────────────────────────────────────────

# 기존 Allowlist에 있는 ATTACHMENT ID (fd3f3c99)
_ATTACH_EV_ID = "fd3f3c99-62cd-4336-bf23-dda92a4b2a43"
# DATE family용 미등록 ID (Allowlist 미포함 → DT-T07에서 403 확인)
_DATE_EV_ID_UNLISTED = "aaaaaaaa-0000-0000-0000-000000000001"

_EFC_ID = "987c5b1f-099e-4941-abcc-0aa5fc2cb868"
_SCHEMA_ID = "3c09d127-84df-4ba6-92ff-7b7941c2b811"
_FIELD_DATE_ID = "cccccccc-0000-0000-0000-000000000001"
_REVIEWER_ID = "user-safety-mgr-001"
_AUTH_USER = {"id": _REVIEWER_ID, "role_code": "003"}
_REASON = "DATE 증빙 법령 근거 확인 완료 — WO-DOC260-DATE-GATE-B"

# ─── DB 쿼리 실행 순서 (FakeCursor 기준, 기존 파일과 동일) ───────────────────
# 1: authority SELECT
# 2: runtime_evidence_field SELECT FOR UPDATE
# 3: evidence_field_candidate SELECT
# 4: 선행 EVIDENCE APPROVE decision SELECT
# 5: runtime_form_schema SELECT
# 6: runtime_field SELECT (fetchall)
# 7: 중복 RUNTIME_EVIDENCE_APPROVE decision SELECT
# 8: runtime_review_decision INSERT RETURNING id
# 9: runtime_evidence_field UPDATE (rowcount 확인)


class _FakeCursor:
    """9단계 쿼리 순서 기반 fake 커서 (DATE 전용 기본값)."""

    def __init__(
        self,
        authority_ok: bool = True,
        ev_found: bool = True,
        ev_status: str = "CANDIDATE",
        ev_family: str = "DATE",
        ev_upload_type: str = "timestamp_auto",
        ev_candidate_id: str = _EFC_ID,
        efc_found: bool = True,
        efc_status: str = "APPROVED_BY_HUMAN",
        efc_field_candidate_id: str = "fk-field-cand-date-001",
        prior_approve_decision: bool = True,
        schema_found: bool = True,
        schema_status: str = "APPROVED_FOR_RUNTIME_USE",
        matched_fields: list | None = None,
        duplicate_runtime_decision: bool = False,
        decision_id: str = "dec-date-rt-001",
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
            {"id": _FIELD_DATE_ID, "input_type": "date"}
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
                "id": _ATTACH_EV_ID,
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
    ev_id: str = _ATTACH_EV_ID,
    reason: str = _REASON,
):
    from routers.review_bridge import bridge_evidence_runtime_approve
    with patch("db.direct_sql._connect", return_value=conn):
        return bridge_evidence_runtime_approve(
            runtime_evidence_field_id=ev_id,
            review_reason=reason,
            current_user=current_user,
        )


# ─── DT-T01: DATE family 정상 승인 ───────────────────────────────────────────

def test_DT_T01_date_family_success():
    """DT-T01: DATE family + timestamp_auto + input_type=date → 정상 승인.
    Allowlist에 있는 ID(fd3f3c99)에 DATE family를 주입하여 G-B01 코드 경로 확인."""
    conn = _FakeConn(_FakeCursor(
        ev_family="DATE",
        ev_upload_type="timestamp_auto",
        matched_fields=[{"id": _FIELD_DATE_ID, "input_type": "date"}],
        decision_id="dec-date-rt-t01",
    ))

    result = _call(conn)

    assert result["data"]["new_status"] == "APPROVED_BY_HUMAN"
    assert result["data"]["review_decision_id"] == "dec-date-rt-t01"
    assert conn.committed
    assert not conn.rolled_back


# ─── DT-T02: DATE family + upload_type=attachment (교차 조합) → 422 ──────────

def test_DT_T02_date_family_wrong_upload_type_422():
    """DT-T02: DATE family인데 upload_type=attachment → 교차 조합 차단 422."""
    conn = _FakeConn(_FakeCursor(
        ev_family="DATE",
        ev_upload_type="attachment",  # DATE family에 ATTACHMENT upload_type
    ))

    with pytest.raises(HTTPException) as exc_info:
        _call(conn)

    assert exc_info.value.status_code == 422
    assert "timestamp_auto" in exc_info.value.detail
    assert conn.rolled_back


# ─── DT-T03: DATE family + timestamp_auto + input_type=file (교차 조합) → 422

def test_DT_T03_date_family_wrong_input_type_422():
    """DT-T03: DATE family + timestamp_auto이나 input_type=file → field 교차 조합 차단 422."""
    conn = _FakeConn(_FakeCursor(
        ev_family="DATE",
        ev_upload_type="timestamp_auto",
        matched_fields=[{"id": _FIELD_DATE_ID, "input_type": "file"}],  # DATE에 file input_type
    ))

    with pytest.raises(HTTPException) as exc_info:
        _call(conn)

    assert exc_info.value.status_code == 422
    assert "date" in exc_info.value.detail.lower()
    assert conn.rolled_back


# ─── DT-T04: ATTACHMENT family + upload_type=timestamp_auto (교차 조합) → 422

def test_DT_T04_attachment_family_wrong_upload_type_422():
    """DT-T04: ATTACHMENT family인데 upload_type=timestamp_auto → 교차 조합 차단 422."""
    conn = _FakeConn(_FakeCursor(
        ev_family="ATTACHMENT",
        ev_upload_type="timestamp_auto",  # ATTACHMENT family에 DATE upload_type
    ))

    with pytest.raises(HTTPException) as exc_info:
        _call(conn)

    assert exc_info.value.status_code == 422
    assert "attachment" in exc_info.value.detail.lower()
    assert conn.rolled_back


# ─── DT-T05: ATTACHMENT family 기존 경로 회귀 없음 ───────────────────────────

def test_DT_T05_attachment_family_regression():
    """DT-T05: ATTACHMENT family + attachment + input_type=file → 기존 정상 경로 회귀 없음."""
    conn = _FakeConn(_FakeCursor(
        ev_family="ATTACHMENT",
        ev_upload_type="attachment",
        matched_fields=[{"id": "field-attach-001", "input_type": "file"}],
        decision_id="dec-attach-regression",
    ))

    result = _call(conn)

    assert result["data"]["new_status"] == "APPROVED_BY_HUMAN"
    assert result["data"]["review_decision_id"] == "dec-attach-regression"
    assert conn.committed
    assert not conn.rolled_back


# ─── DT-T06: 미지원 evidence_family → 422 ────────────────────────────────────

def test_DT_T06_unsupported_family_422():
    """DT-T06: evidence_family='SIGNATURE' 등 미지원 → 422."""
    conn = _FakeConn(_FakeCursor(
        ev_family="SIGNATURE",
        ev_upload_type="manual",
    ))

    with pytest.raises(HTTPException) as exc_info:
        _call(conn)

    assert exc_info.value.status_code == 422
    assert "not supported" in exc_info.value.detail.lower()
    assert conn.rolled_back


# ─── DT-T07: DATE ID Allowlist 미등록 → 403 (DB 미도달) ─────────────────────

def test_DT_T07_date_id_not_in_allowlist_403():
    """DT-T07: DATE family ID가 _RUNTIME_EV_ALLOWLIST에 없으면 DB 미도달 403.
    G-B01 family 분기 추가 ≠ Allowlist 확장 — ID 단위 Owner Gate 유지."""
    from routers.review_bridge import bridge_evidence_runtime_approve

    with pytest.raises(HTTPException) as exc_info:
        with patch("db.direct_sql._connect", side_effect=AssertionError("DB should not be reached")):
            bridge_evidence_runtime_approve(
                runtime_evidence_field_id=_DATE_EV_ID_UNLISTED,
                review_reason=_REASON,
                current_user=_AUTH_USER,
            )

    assert exc_info.value.status_code == 403
    assert "allowlist" in exc_info.value.detail.lower()
