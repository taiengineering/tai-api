"""WO-DOC260-OBJ10-WPA-RUNTIME-APPROVAL-EXTENSION-001
Runtime Evidence Field 사용 승인 — MEASUREMENT / SIGNATURE / REPORT_NUMBER 유형 추가 테스트

테스트 케이스:
  정상 경로
    T01: MEASUREMENT + measurement_input + input_type=measurement → 정상 승인
    T02: MEASUREMENT + measurement_input + input_type=date        → 정상 승인 (CONTRACT_ALLOWED)
    T03: SIGNATURE   + signature          + input_type=signature  → 정상 승인
    T04: REPORT_NUMBER + inspector_identity + input_type=text     → 정상 승인

  차단 경로
    T05: family/upload_type 불일치 (MEASUREMENT + attachment)    → 422
    T06: family/input_type 불일치 (MEASUREMENT + text)           → 422
    T07: APPROVAL_MARK                                           → 422 (미지원 family)
    T08: CERTIFICATE                                             → 422 (미지원 family)
    T09: PHOTO                                                   → 422 (미지원 family)
    T10: 허용 목록 미등록 UUID                                     → 403, DB 미접근
    T11: 선행 후보 승인 미완료 (efc.status=CANDIDATE)              → 409
    T12: 승인 결정 미완료 또는 누락                                 → 409
    T13: 승인자 권한 부족 (role_code 불일치)                        → 403
    T14A: 연결 runtime_field 0건                                  → 422
    T14B: 연결 runtime_field 복수건                               → 422
    T15: 중복 승인                                                → 409
    T16: 상태 변경 실패 (update_rowcount=0) → 전체 롤백             → 409

Production DB write = 0 (mock 전용).
"""
from __future__ import annotations

from unittest.mock import patch
from fastapi import HTTPException

import pytest

# ─── 테스트 상수 ──────────────────────────────────────────────────────────────
# Allowlist에 있는 기존 ID를 재사용 (Allowlist 검사를 통과시키기 위해 monkeypatch 사용)
_EV_ID_ALLOWLISTED = "fd3f3c99-62cd-4336-bf23-dda92a4b2a43"
_EV_ID_NOT_IN_ALLOWLIST = "00000000-0000-0000-0000-000000000099"

_EFC_ID = "aaa00001-0000-0000-0000-000000000001"
_SCHEMA_ID = "bbb00001-0000-0000-0000-000000000001"
_FIELD_ID = "ccc00001-0000-0000-0000-000000000001"
_REVIEWER_ID = "user-safety-mgr-wpa-001"
_AUTH_USER = {"id": _REVIEWER_ID, "role_code": "003"}
_REASON = "WO-DOC260-OBJ10-WPA 테스트용 사유"

# monkeypatch로 Allowlist를 테스트 UUID로 확장
_TEST_ALLOWLIST = frozenset({
    _EV_ID_ALLOWLISTED,
    "fd3f3c99-0000-0000-0000-meas000000001",  # MEASUREMENT 테스트 전용
    "fd3f3c99-0000-0000-0000-sig0000000001",  # SIGNATURE 테스트 전용
    "fd3f3c99-0000-0000-0000-rnum000000001",  # REPORT_NUMBER 테스트 전용
})

_MEAS_EV_ID = "fd3f3c99-0000-0000-0000-meas000000001"
_SIG_EV_ID  = "fd3f3c99-0000-0000-0000-sig0000000001"
_RNUM_EV_ID = "fd3f3c99-0000-0000-0000-rnum000000001"


# ─── DB 쿼리 순서 (FakeCursor 기준) ──────────────────────────────────────────
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
    """9단계 쿼리 순서 기반 fake 커서."""

    def __init__(
        self,
        authority_ok: bool = True,
        ev_found: bool = True,
        ev_status: str = "CANDIDATE",
        ev_family: str = "MEASUREMENT",
        ev_upload_type: str = "measurement_input",
        ev_candidate_id: str = _EFC_ID,
        efc_found: bool = True,
        efc_status: str = "APPROVED_BY_HUMAN",
        efc_field_candidate_id: str = "fk-field-cand-wpa-001",
        prior_approve_decision: bool = True,
        schema_found: bool = True,
        schema_status: str = "APPROVED_FOR_RUNTIME_USE",
        matched_fields: list | None = None,
        duplicate_runtime_decision: bool = False,
        decision_id: str = "dec-wpa-001",
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
            {"id": _FIELD_ID, "input_type": "measurement"}
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
                "id": _MEAS_EV_ID,
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
    ev_id: str = _MEAS_EV_ID,
    reason: str = _REASON,
):
    from routers.review_bridge import bridge_evidence_runtime_approve
    with patch("routers.review_bridge._RUNTIME_EV_ALLOWLIST", _TEST_ALLOWLIST):
        with patch("db.direct_sql._connect", return_value=conn):
            return bridge_evidence_runtime_approve(
                runtime_evidence_field_id=ev_id,
                review_reason=reason,
                current_user=current_user,
            )


# ═══ 정상 경로 ════════════════════════════════════════════════════════════════

def test_T01_measurement_measurement_success():
    """T01: MEASUREMENT + measurement_input + input_type=measurement → 정상 승인."""
    conn = _FakeConn(_FakeCursor(
        ev_family="MEASUREMENT",
        ev_upload_type="measurement_input",
        matched_fields=[{"id": _FIELD_ID, "input_type": "measurement"}],
        decision_id="dec-t01",
    ))

    result = _call(conn, ev_id=_MEAS_EV_ID)

    assert result["data"]["new_status"] == "APPROVED_BY_HUMAN"
    assert result["data"]["review_decision_id"] == "dec-t01"
    assert conn.committed
    assert not conn.rolled_back


def test_T02_measurement_date_input_type_success():
    """T02: MEASUREMENT + measurement_input + input_type=date → 정상 승인.
    DOC-OSH-048 CONTRACT_ALLOWED 계약 반영 — MEASUREMENT family에 date input_type 허용."""
    conn = _FakeConn(_FakeCursor(
        ev_family="MEASUREMENT",
        ev_upload_type="measurement_input",
        matched_fields=[{"id": _FIELD_ID, "input_type": "date"}],
        decision_id="dec-t02",
    ))

    result = _call(conn, ev_id=_MEAS_EV_ID)

    assert result["data"]["new_status"] == "APPROVED_BY_HUMAN"
    assert result["data"]["review_decision_id"] == "dec-t02"
    assert conn.committed
    assert not conn.rolled_back


def test_T03_signature_success():
    """T03: SIGNATURE + signature + input_type=signature → 정상 승인."""
    conn = _FakeConn(_FakeCursor(
        ev_family="SIGNATURE",
        ev_upload_type="signature",
        matched_fields=[{"id": _FIELD_ID, "input_type": "signature"}],
        decision_id="dec-t03",
    ))

    result = _call(conn, ev_id=_SIG_EV_ID)

    assert result["data"]["new_status"] == "APPROVED_BY_HUMAN"
    assert result["data"]["review_decision_id"] == "dec-t03"
    assert conn.committed
    assert not conn.rolled_back


def test_T04_report_number_success():
    """T04: REPORT_NUMBER + inspector_identity + input_type=text → 정상 승인."""
    conn = _FakeConn(_FakeCursor(
        ev_family="REPORT_NUMBER",
        ev_upload_type="inspector_identity",
        matched_fields=[{"id": _FIELD_ID, "input_type": "text"}],
        decision_id="dec-t04",
    ))

    result = _call(conn, ev_id=_RNUM_EV_ID)

    assert result["data"]["new_status"] == "APPROVED_BY_HUMAN"
    assert result["data"]["review_decision_id"] == "dec-t04"
    assert conn.committed
    assert not conn.rolled_back


# ═══ 차단 경로 ════════════════════════════════════════════════════════════════

def test_T05_measurement_wrong_upload_type_422():
    """T05: MEASUREMENT family + upload_type=attachment (교차 조합) → 422."""
    conn = _FakeConn(_FakeCursor(
        ev_family="MEASUREMENT",
        ev_upload_type="attachment",
    ))

    with pytest.raises(HTTPException) as exc_info:
        _call(conn, ev_id=_MEAS_EV_ID)

    assert exc_info.value.status_code == 422
    assert "measurement_input" in exc_info.value.detail
    assert conn.rolled_back


def test_T06_measurement_wrong_input_type_422():
    """T06: MEASUREMENT family + measurement_input + input_type=text → field 교차 조합 차단 422."""
    conn = _FakeConn(_FakeCursor(
        ev_family="MEASUREMENT",
        ev_upload_type="measurement_input",
        matched_fields=[{"id": _FIELD_ID, "input_type": "text"}],
    ))

    with pytest.raises(HTTPException) as exc_info:
        _call(conn, ev_id=_MEAS_EV_ID)

    assert exc_info.value.status_code == 422
    assert "measurement" in exc_info.value.detail.lower()
    assert conn.rolled_back


def test_T07_approval_mark_unsupported_422():
    """T07: APPROVAL_MARK family → 미지원 family 차단 422."""
    conn = _FakeConn(_FakeCursor(
        ev_family="APPROVAL_MARK",
        ev_upload_type="signature",
    ))

    with pytest.raises(HTTPException) as exc_info:
        _call(conn, ev_id=_MEAS_EV_ID)

    assert exc_info.value.status_code == 422
    assert "not supported" in exc_info.value.detail.lower()
    assert conn.rolled_back


def test_T08_certificate_unsupported_422():
    """T08: CERTIFICATE family → 미지원 family 차단 422."""
    conn = _FakeConn(_FakeCursor(
        ev_family="CERTIFICATE",
        ev_upload_type="certificate_input",
    ))

    with pytest.raises(HTTPException) as exc_info:
        _call(conn, ev_id=_MEAS_EV_ID)

    assert exc_info.value.status_code == 422
    assert "not supported" in exc_info.value.detail.lower()
    assert conn.rolled_back


def test_T09_photo_unsupported_422():
    """T09: PHOTO family → 미지원 family 차단 422."""
    conn = _FakeConn(_FakeCursor(
        ev_family="PHOTO",
        ev_upload_type="photo_upload",
    ))

    with pytest.raises(HTTPException) as exc_info:
        _call(conn, ev_id=_MEAS_EV_ID)

    assert exc_info.value.status_code == 422
    assert "not supported" in exc_info.value.detail.lower()
    assert conn.rolled_back


def test_T10_not_in_allowlist_403_db_not_reached():
    """T10: 허용 목록 미등록 UUID → 403, DB 미접근."""
    from routers.review_bridge import bridge_evidence_runtime_approve

    with pytest.raises(HTTPException) as exc_info:
        with patch("db.direct_sql._connect", side_effect=AssertionError("DB should not be reached")):
            bridge_evidence_runtime_approve(
                runtime_evidence_field_id=_EV_ID_NOT_IN_ALLOWLIST,
                review_reason=_REASON,
                current_user=_AUTH_USER,
            )

    assert exc_info.value.status_code == 403
    assert "allowlist" in exc_info.value.detail.lower()


def test_T11_efc_not_approved_409():
    """T11: 선행 후보 승인 미완료 (efc.status=CANDIDATE) → 409."""
    conn = _FakeConn(_FakeCursor(efc_status="CANDIDATE"))

    with pytest.raises(HTTPException) as exc_info:
        _call(conn, ev_id=_MEAS_EV_ID)

    assert exc_info.value.status_code == 409
    assert "not yet approved" in exc_info.value.detail.lower()
    assert conn.rolled_back


def test_T12_no_prior_approve_decision_409():
    """T12: 선행 EVIDENCE APPROVE decision 없음 (audit trail missing) → 409."""
    conn = _FakeConn(_FakeCursor(prior_approve_decision=False))

    with pytest.raises(HTTPException) as exc_info:
        _call(conn, ev_id=_MEAS_EV_ID)

    assert exc_info.value.status_code == 409
    assert "audit trail missing" in exc_info.value.detail.lower()
    assert conn.rolled_back


def test_T13_wrong_role_403():
    """T13: 승인자 role_code가 SAFETY_MANAGER 아님 → DB 미도달 403."""
    conn = _FakeConn(_FakeCursor())

    with pytest.raises(HTTPException) as exc_info:
        _call(conn, current_user={"id": _REVIEWER_ID, "role_code": "999"}, ev_id=_MEAS_EV_ID)

    assert exc_info.value.status_code == 403
    assert not conn.rolled_back  # DB 연결 전 차단


def test_T14A_no_field_connection_422():
    """T14A: 연결 runtime_field 0건 → connection broken 422."""
    conn = _FakeConn(_FakeCursor(matched_fields=[]))

    with pytest.raises(HTTPException) as exc_info:
        _call(conn, ev_id=_MEAS_EV_ID)

    assert exc_info.value.status_code == 422
    assert "connection broken" in exc_info.value.detail.lower()
    assert conn.rolled_back


def test_T14B_multiple_field_connections_422():
    """T14B: 연결 runtime_field 복수건 → ambiguous connection 422."""
    conn = _FakeConn(_FakeCursor(matched_fields=[
        {"id": "field-1", "input_type": "measurement"},
        {"id": "field-2", "input_type": "measurement"},
    ]))

    with pytest.raises(HTTPException) as exc_info:
        _call(conn, ev_id=_MEAS_EV_ID)

    assert exc_info.value.status_code == 422
    assert "ambiguous" in exc_info.value.detail.lower()
    assert conn.rolled_back


def test_T15_duplicate_runtime_approve_409():
    """T15: 동일 ID에 RUNTIME_EVIDENCE_APPROVE decision 이미 존재 → 중복 차단 409."""
    conn = _FakeConn(_FakeCursor(duplicate_runtime_decision=True))

    with pytest.raises(HTTPException) as exc_info:
        _call(conn, ev_id=_MEAS_EV_ID)

    assert exc_info.value.status_code == 409
    assert "already exists" in exc_info.value.detail.lower()
    assert conn.rolled_back


def test_T16_update_rowcount_zero_rollback():
    """T16: UPDATE rowcount=0 (concurrent modification) → 409 + 전체 롤백."""
    conn = _FakeConn(_FakeCursor(update_rowcount=0))

    with pytest.raises(HTTPException) as exc_info:
        _call(conn, ev_id=_MEAS_EV_ID)

    assert exc_info.value.status_code == 409
    assert "concurrent modification" in exc_info.value.detail.lower()
    assert conn.rolled_back
