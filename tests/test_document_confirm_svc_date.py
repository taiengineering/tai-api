"""WO-DOC260-MAINLINE-DATE-BE-CONTRACT-003 Gate A — DATE evidence 단위·회귀 테스트.

T-DATE-01 ~ T-DATE-09 (계약 §6) + 추가 교차 조합 차단 테스트.
Fake DB 레이어 재사용 (test_document_confirm_svc.py 패턴 동일).
"""

import hashlib
import sys
import datetime as _dt
from unittest.mock import MagicMock, patch

import services.document_confirm_svc as mod
from services.document_confirm_svc import (
    ConfirmError,
    _verify_date_evidence_value,
    confirm_document_atomic,
)

# ── 공유 픽스처 ───────────────────────────────────────────────
USER_ID   = "11111111-1111-1111-1111-111111111111"
DOC_ID    = "dddddddd-0002-0002-0002-000000000002"
SCHEMA_ID = "ssssssss-0002-0002-0002-000000000002"
ARCHIVE_ID = "cccccccc-0002-0002-0002-000000000002"
TS = _dt.datetime(2026, 10, 30, 9, 0, 0, tzinfo=_dt.timezone.utc)

FIELD_DATE_ID = "ffd00001-date-date-date-000000000001"
EV_FIELD_ID   = "evf00001-date-date-date-000000000001"
EFC_ID        = "efc00001-date-date-date-000000000001"
FC_ID         = "fc000001-date-date-date-000000000001"


# ── Fake psycopg2 ─────────────────────────────────────────────
class FakeUniqueViolation(Exception):
    pass

class _FakeErrors:
    UniqueViolation = FakeUniqueViolation
    LockNotAvailable = Exception
    DeadlockDetected = Exception
    QueryCanceled = Exception

class _FakeExtras:
    class RealDictCursor:
        pass

class _FakePsycopg2:
    OperationalError = Exception
    errors = _FakeErrors
    extras = _FakeExtras


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.conn.executed.append((sql.strip().split("\n")[0].strip(), params))
        s = sql.strip().upper()
        for marker, exc in self.conn.fail_on.items():
            if marker in sql:
                raise exc
        if "FOR UPDATE" in s:
            self.conn._last = self.conn.locked_row
        elif "FROM FACTORIES" in s:
            self.conn._last = self.conn.factory_row
        elif "RUNTIME_STATE_TRANSITION_RULE" in s:
            self.conn._last = self.conn.rule_row
        elif "RUNTIME_FORM_SCHEMA" in s:
            self.conn._last = self.conn.schema_row
        elif "RUNTIME_EVIDENCE_FIELD" in s:
            self.conn._last_many = self.conn.evidence_field_rows
        elif "FROM EVIDENCE_FIELD_CANDIDATE" in s:
            # pop per-call row if multi-evidence
            if self.conn._efc_queue:
                self.conn._last = self.conn._efc_queue.pop(0)
            else:
                self.conn._last = self.conn.evidence_candidate_row
        elif "RUNTIME_FIELD" in s:
            self.conn._last_many = self.conn.field_rows
        elif "RUNTIME_CHECKLIST_ITEM" in s:
            self.conn._last_many = self.conn.checklist_rows
        elif "CLOCK_TIMESTAMP" in s:
            self.conn._last = {"ts": TS}
        elif "INSERT INTO RUNTIME_DOCUMENT_ARCHIVE" in s:
            self.conn.archive_inserts += 1
            self.conn._last = {"id": ARCHIVE_ID}
        elif "INSERT INTO RUNTIME_DOCUMENT_APPROVAL" in s:
            self.conn.approval_inserts += 1
            self.conn._last = None
        elif "UPDATE RUNTIME_DOCUMENT_DATA" in s:
            self.conn.status_updates += 1
            sealed = dict(self.conn.locked_row)
            sealed["status"] = "APPROVED_BY_HUMAN"
            sealed["reviewed_by"] = params[1] if params else USER_ID
            sealed["reviewed_at"] = params[2] if params else TS
            self.conn._last = sealed
        else:
            self.conn._last = None

    def fetchone(self):
        return self.conn._last

    def fetchall(self):
        return getattr(self.conn, "_last_many", [])


class FakeConn:
    def __init__(self, **kw):
        self.locked_row = kw.get("locked_row")
        self.factory_row = kw.get("factory_row")
        self.rule_row = kw.get("rule_row", {"requires_reviewer": True, "requires_comment": True})
        self.schema_row = kw.get("schema_row", {
            "id": SCHEMA_ID, "form_name": "테스트", "status": "APPROVED_FOR_RUNTIME_USE",
        })
        self.field_rows = kw.get("field_rows", [])
        self.checklist_rows = kw.get("checklist_rows", [])
        self.evidence_field_rows = kw.get("evidence_field_rows", [])
        self.evidence_candidate_row = kw.get("evidence_candidate_row", None)
        self._efc_queue = list(kw.get("efc_queue", []))
        self.fail_on = kw.get("fail_on", {})
        self.autocommit = True
        self.executed = []
        self.committed = False
        self.rolled_back = False
        self.closed = False
        self.archive_inserts = 0
        self.approval_inserts = 0
        self.status_updates = 0
        self._last = None
        self._last_many = []

    def cursor(self, cursor_factory=None):
        return FakeCursor(self)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def _install(conn, audit_calls=None):
    import db.direct_sql as ds
    ds._connect = lambda: conn
    sys.modules["psycopg2"] = _FakePsycopg2
    sys.modules["psycopg2.errors"] = _FakeErrors
    sys.modules["psycopg2.extras"] = _FakeExtras
    if audit_calls is not None:
        mod._best_effort_audit = lambda *a, **k: audit_calls.append(a)


def _user(uid=USER_ID):
    return {"id": uid, "role_code": "011", "company_id": "aaa", "factory_id": None}


def _locked(runtime=None):
    return {
        "id": DOC_ID,
        "form_schema_id": SCHEMA_ID,
        "status": "REVIEW_PENDING",
        "company_id": "aaa",
        "factory_id": None,
        "version": 1,
        "submitted_by": USER_ID,
        "runtime_data_json": {} if runtime is None else runtime,
        "evidence_links": [],
    }


def _date_ev_field(ev_id=EV_FIELD_ID, efc_id=EFC_ID, status="APPROVED_BY_HUMAN"):
    return {
        "id": ev_id,
        "form_schema_id": SCHEMA_ID,
        "evidence_candidate_id": efc_id,
        "evidence_type": "DATE",
        "status": status,
        "evidence_family": "DATE",
        "upload_type": "timestamp_auto",
    }


def _date_efc_row(efc_id=EFC_ID, fc_id=FC_ID, status="APPROVED_BY_HUMAN"):
    return {"id": efc_id, "field_candidate_id": fc_id,
            "status": status, "schema_candidate_id": None}


def _date_field_row(fid=FIELD_DATE_ID, key="inspection_datetime", fc_id=FC_ID):
    return {
        "id": fid,
        "field_key": key,
        "input_type": "date",
        "field_label": key,
        "form_schema_id": SCHEMA_ID,
        "field_order": 1,
        "required_status": "REQUIRED_BY_HUMAN",
        "field_candidate_id": fc_id,
    }


# ════════════════════════════════════════════════════════════
# §1 _verify_date_evidence_value() 단위 테스트
# ════════════════════════════════════════════════════════════

def test_verify_date_none_raises():
    """None → 422 (T-DATE-03)."""
    try:
        _verify_date_evidence_value(date_value=None, ev_field_id="ev-1", field_key="k")
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "date value missing" in e.detail


def test_verify_date_non_string_raises():
    """int/dict → 422."""
    try:
        _verify_date_evidence_value(date_value=20261015, ev_field_id="ev-1", field_key="k")
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "must be str" in e.detail


def test_verify_date_slash_format_raises():
    """2026/10/15 (슬래시 구분자) → 422 (T-DATE-04)."""
    try:
        _verify_date_evidence_value(date_value="2026/10/15", ev_field_id="ev-1", field_key="k")
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "YYYY-MM-DD" in e.detail


def test_verify_date_yyyymmdd_format_raises():
    """20261015 (구분자 없음) → 422 (Python 3.11+ fromisoformat 허용 방어)."""
    try:
        _verify_date_evidence_value(date_value="20261015", ev_field_id="ev-1", field_key="k")
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "YYYY-MM-DD" in e.detail


def test_verify_date_invalid_calendar_raises():
    """2026-02-31 (형식은 맞으나 존재하지 않는 날짜) → 422."""
    try:
        _verify_date_evidence_value(date_value="2026-02-31", ev_field_id="ev-1", field_key="k")
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "not a valid calendar date" in e.detail


def test_verify_date_valid_passes():
    """2026-10-30 (정상) → 예외 없음."""
    _verify_date_evidence_value(date_value="2026-10-30", ev_field_id="ev-1", field_key="k")


def test_verify_date_valid_leap_year_passes():
    """2024-02-29 (윤년 정상) → 예외 없음."""
    _verify_date_evidence_value(date_value="2024-02-29", ev_field_id="ev-1", field_key="k")


def test_verify_date_invalid_leap_year_raises():
    """2023-02-29 (윤년 아님) → 422."""
    try:
        _verify_date_evidence_value(date_value="2023-02-29", ev_field_id="ev-1", field_key="k")
        assert False
    except ConfirmError as e:
        assert e.http_status == 422


# ════════════════════════════════════════════════════════════
# §2 T-DATE-01 미승인 DATE 증적 → 422
# ════════════════════════════════════════════════════════════

def test_T_DATE_01_unapproved_date_evidence_candidate_blocks():
    """T-DATE-01: evidence_field_candidate.status=CANDIDATE → 422."""
    conn = FakeConn(
        locked_row=_locked(runtime={"inspection_datetime": "2026-10-15"}),
        field_rows=[_date_field_row()],
        evidence_field_rows=[_date_ev_field()],
        evidence_candidate_row=_date_efc_row(status="CANDIDATE"),
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=_user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "not approved" in e.detail.lower()
        assert "CANDIDATE" in e.detail
    assert conn.rolled_back and conn.archive_inserts == 0


def test_T_DATE_01b_unapproved_date_ev_field_status_blocks():
    """T-DATE-01b: runtime_evidence_field.status=CANDIDATE → 422."""
    conn = FakeConn(
        locked_row=_locked(runtime={"inspection_datetime": "2026-10-15"}),
        field_rows=[_date_field_row()],
        evidence_field_rows=[_date_ev_field(status="CANDIDATE")],
        evidence_candidate_row=_date_efc_row(),
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=_user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "runtime_evidence_field.status" in e.detail
        assert "CANDIDATE" in e.detail
    assert conn.rolled_back and conn.archive_inserts == 0


# ════════════════════════════════════════════════════════════
# §3 T-DATE-02 승인된 DATE 증적 + 유효 날짜 → 200
# ════════════════════════════════════════════════════════════

def test_T_DATE_02_approved_date_evidence_confirms():
    """T-DATE-02: APPROVED_BY_HUMAN + 유효 날짜 → commit, Archive 생성, evidence_manifest에 DATE 항목."""
    audit = []
    conn = FakeConn(
        locked_row=_locked(runtime={"inspection_datetime": "2026-10-15"}),
        field_rows=[_date_field_row()],
        evidence_field_rows=[_date_ev_field()],
        evidence_candidate_row=_date_efc_row(),
    )
    _install(conn, audit)

    captured: list = []

    def spy_render(*args, **kwargs):
        captured.append(kwargs)
        return {
            "rendered_body": "<html/>",
            "source_trace_snapshot": [],
            "template_identity": "tpl",
            "evidence_manifest": kwargs.get("attachment_evidence_manifest", []),
        }

    with patch("services.document_confirm_svc.build_render_artifacts", side_effect=spy_render):
        with patch("services.document_confirm_svc.compute_confirmed_snapshot_hash",
                   return_value="a" * 64):
            result = confirm_document_atomic(DOC_ID, actor_id=None, comment="ok",
                                             current_user=_user())

    assert conn.committed and not conn.rolled_back
    assert conn.archive_inserts == 1 and conn.approval_inserts == 1
    assert result["status"] == "APPROVED_BY_HUMAN"
    assert len(audit) == 1

    # evidence_manifest에 DATE 항목 포함 확인
    assert len(captured) == 1
    manifest = captured[0].get("attachment_evidence_manifest", [])
    assert len(manifest) == 1
    entry = manifest[0]
    assert entry["evidence_family"] == "DATE"
    assert entry["date_value"] == "2026-10-15"
    assert entry["value_source"] == "USER_INPUT"
    assert entry["value_semantic_class"] == "PENDING_CLASSIFICATION"
    assert entry["input_type"] == "date"
    assert entry["field_key"] == "inspection_datetime"
    assert entry["evidence_field_id"] == EV_FIELD_ID
    assert entry["field_id"] == FIELD_DATE_ID


# ════════════════════════════════════════════════════════════
# §4 T-DATE-03/04 날짜 값 검증 실패
# ════════════════════════════════════════════════════════════

def test_T_DATE_03_date_value_null_blocks():
    """T-DATE-03: runtime_data_json에 날짜 값 없음 → 422."""
    conn = FakeConn(
        locked_row=_locked(runtime={}),  # date value absent
        field_rows=[_date_field_row()],
        evidence_field_rows=[_date_ev_field()],
        evidence_candidate_row=_date_efc_row(),
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=_user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "date value missing" in e.detail
    assert conn.rolled_back and conn.archive_inserts == 0


def test_T_DATE_04_date_value_invalid_format_blocks():
    """T-DATE-04: 날짜 형식 오류 → 422."""
    conn = FakeConn(
        locked_row=_locked(runtime={"inspection_datetime": "2026/10/15"}),
        field_rows=[_date_field_row()],
        evidence_field_rows=[_date_ev_field()],
        evidence_candidate_row=_date_efc_row(),
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=_user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "YYYY-MM-DD" in e.detail
    assert conn.rolled_back and conn.archive_inserts == 0


# ════════════════════════════════════════════════════════════
# §5 T-DATE-05 ATTACHMENT 회귀 없음
# ════════════════════════════════════════════════════════════

_ATT_FIELD_ID = "ffffffff-att-att-att-000000000001"
_ATT_EV_ID    = "evffffff-att-att-att-000000000001"
_ATT_EFC_ID   = "efcfffff-att-att-att-000000000001"
_ATT_FC_ID    = "fcffffff-att-att-att-000000000001"
_PDF_BYTES = b"%PDF" + b"\x00" * 100
_PDF_SHA = hashlib.sha256(_PDF_BYTES).hexdigest()
_PDF_REF = f"storage://company-docs/attachments/document/{DOC_ID}/{_ATT_FIELD_ID}/{_PDF_SHA}.pdf"

_ATT_RUNTIME = {
    "attached_doc": {
        "_type": "file_snapshot",
        "field_key": "attached_doc",
        "field_id": _ATT_FIELD_ID,
        "storage_ref": _PDF_REF,
        "sha256": _PDF_SHA,
        "mime_type": "application/pdf",
        "byte_size": len(_PDF_BYTES),
        "original_file_name": "doc.pdf",
        "uploaded_by_user_id": USER_ID,
        "uploaded_at": "2026-10-30T00:00:00Z",
    }
}

_ATT_EV_FIELD = {
    "id": _ATT_EV_ID,
    "form_schema_id": SCHEMA_ID,
    "evidence_candidate_id": _ATT_EFC_ID,
    "evidence_type": "ATTACHMENT",
    "status": "APPROVED_BY_HUMAN",
    "evidence_family": "ATTACHMENT",
    "upload_type": "attachment",
}

_ATT_EFC_ROW = {
    "id": _ATT_EFC_ID,
    "field_candidate_id": _ATT_FC_ID,
    "status": "APPROVED_BY_HUMAN",
    "schema_candidate_id": None,
}

_ATT_FIELD_ROW = {
    "id": _ATT_FIELD_ID,
    "field_key": "attached_doc",
    "input_type": "file",
    "field_label": "첨부서류",
    "form_schema_id": SCHEMA_ID,
    "field_order": 1,
    "required_status": "REQUIRED_BY_HUMAN",
    "field_candidate_id": _ATT_FC_ID,
}


def test_T_DATE_05_attachment_regression():
    """T-DATE-05: ATTACHMENT 증적 포함 서식 — 기존 동작 유지, 회귀 없음."""
    conn = FakeConn(
        locked_row=_locked(runtime=_ATT_RUNTIME),
        field_rows=[_ATT_FIELD_ROW],
        evidence_field_rows=[_ATT_EV_FIELD],
        evidence_candidate_row=_ATT_EFC_ROW,
    )
    _install(conn)

    sb = MagicMock()
    sb.storage.from_.return_value.download.return_value = _PDF_BYTES

    with patch("services.document_attachment_svc.get_supabase", return_value=sb):
        result = confirm_document_atomic(DOC_ID, actor_id=None, comment="ok",
                                         current_user=_user())
    assert conn.committed and result["status"] == "APPROVED_BY_HUMAN"
    assert conn.archive_inserts == 1


# ════════════════════════════════════════════════════════════
# §6 T-DATE-06 ATTACHMENT + DATE 혼합
# ════════════════════════════════════════════════════════════

def test_T_DATE_06_mixed_attachment_and_date():
    """T-DATE-06: ATTACHMENT + DATE 혼합 서식 — 각각 경로 처리, Archive 생성."""
    mixed_runtime = dict(_ATT_RUNTIME)
    mixed_runtime["inspection_datetime"] = "2026-10-15"

    conn = FakeConn(
        locked_row=_locked(runtime=mixed_runtime),
        field_rows=[_ATT_FIELD_ROW, _date_field_row()],
        evidence_field_rows=[_ATT_EV_FIELD, _date_ev_field()],
        efc_queue=[_ATT_EFC_ROW, _date_efc_row()],
    )
    _install(conn)

    sb = MagicMock()
    sb.storage.from_.return_value.download.return_value = _PDF_BYTES

    captured: list = []

    def spy_render(*args, **kwargs):
        captured.append(kwargs)
        return {
            "rendered_body": "<html/>",
            "source_trace_snapshot": [],
            "template_identity": "tpl",
            "evidence_manifest": kwargs.get("attachment_evidence_manifest", []),
        }

    with (
        patch("services.document_attachment_svc.get_supabase", return_value=sb),
        patch("services.document_confirm_svc.build_render_artifacts", side_effect=spy_render),
        patch("services.document_confirm_svc.compute_confirmed_snapshot_hash",
              return_value="a" * 64),
    ):
        result = confirm_document_atomic(DOC_ID, actor_id=None, comment="ok",
                                         current_user=_user())

    assert conn.committed and result["status"] == "APPROVED_BY_HUMAN"
    assert len(captured) == 1
    manifest = captured[0].get("attachment_evidence_manifest", [])
    # ATTACHMENT 항목 + DATE 항목 모두 포함
    families = {e.get("evidence_family") for e in manifest}
    assert "DATE" in families
    date_entry = next(e for e in manifest if e.get("evidence_family") == "DATE")
    assert date_entry["date_value"] == "2026-10-15"
    att_entry = next(e for e in manifest if e.get("evidence_family") != "DATE")
    assert att_entry.get("sha256") or att_entry.get("storage_ref")


# ════════════════════════════════════════════════════════════
# §7 T-DATE-07 Q4 hash 무결성 (실제 hash 계산 경로)
# ════════════════════════════════════════════════════════════

def test_T_DATE_07_q4_hash_integrity():
    """T-DATE-07: 실제 Q4 hash — DATE manifest 포함 여부 + 결정성 + date_value 민감도.

    Mock으로 고정 해시를 반환하는 방식은 Q4 무결성 근거가 되지 않는다.
    실제 compute_confirmed_snapshot_hash 를 통과시켜 검증한다.
    """
    from services.document_confirm_svc import compute_confirmed_snapshot_hash as real_hash

    def passthrough_render(*args, **kwargs):
        ev_manifest = kwargs.get("attachment_evidence_manifest", [])
        return {
            "rendered_body": "<html>test</html>",
            "source_trace_snapshot": [{"source": "tpl-test-01"}],  # 비어있지 않은 list 필수
            "template_identity": "tpl-test",
            "evidence_manifest": ev_manifest,  # DATE manifest 그대로 전달
        }

    def run_hash(date_val: str) -> str:
        captured: list = []

        def wrap_hash(**kwargs):
            result = real_hash(**kwargs)
            captured.append(result)
            return result

        conn = FakeConn(
            locked_row=_locked(runtime={"inspection_datetime": date_val}),
            field_rows=[_date_field_row()],
            evidence_field_rows=[_date_ev_field()],
            evidence_candidate_row=_date_efc_row(),
        )
        _install(conn)
        with patch("services.document_confirm_svc.build_render_artifacts",
                   side_effect=passthrough_render):
            with patch("services.document_confirm_svc.compute_confirmed_snapshot_hash",
                       side_effect=wrap_hash):
                confirm_document_atomic(DOC_ID, actor_id=None, comment="ok",
                                        current_user=_user())
        assert len(captured) == 1, "compute_confirmed_snapshot_hash must be called exactly once"
        return captured[0]

    # 결정성: 동일 date_value → 동일 Q4 hash
    h1 = run_hash("2026-10-15")
    h2 = run_hash("2026-10-15")
    assert h1 == h2, f"same input must produce same Q4 hash, got {h1!r} vs {h2!r}"

    # 민감도: date_value 변경 → Q4 hash 변경
    h3 = run_hash("2026-10-16")
    assert h1 != h3, "different date_value must produce different Q4 hash"

    # 형식: 64자 소문자 hex
    assert len(h1) == 64 and all(c in "0123456789abcdef" for c in h1), \
        f"hash must be 64-char lowercase hex, got {h1!r}"


# ════════════════════════════════════════════════════════════
# §8 T-DATE-09 confirmed_at vs date_value 독립성
# ════════════════════════════════════════════════════════════

def test_T_DATE_09_date_value_independent_of_confirmed_at():
    """T-DATE-09: date_value(사용자 입력)는 confirmed_at(서버 시각)과 독립적이다."""
    captured: list = []

    def spy_render(*args, **kwargs):
        captured.append(kwargs)
        return {
            "rendered_body": "<html/>",
            "source_trace_snapshot": [],
            "template_identity": "tpl",
            "evidence_manifest": kwargs.get("attachment_evidence_manifest", []),
        }

    conn = FakeConn(
        locked_row=_locked(runtime={"inspection_datetime": "2020-01-01"}),
        field_rows=[_date_field_row()],
        evidence_field_rows=[_date_ev_field()],
        evidence_candidate_row=_date_efc_row(),
    )
    _install(conn)
    with patch("services.document_confirm_svc.build_render_artifacts", side_effect=spy_render):
        with patch("services.document_confirm_svc.compute_confirmed_snapshot_hash",
                   return_value="a" * 64):
            confirm_document_atomic(DOC_ID, actor_id=None, comment="ok", current_user=_user())

    manifest = captured[0].get("attachment_evidence_manifest", [])
    assert len(manifest) == 1
    assert manifest[0]["date_value"] == "2020-01-01"
    # confirmed_at = TS (2026-10-30) — date_value와 독립적으로 다른 값
    assert manifest[0]["date_value"] != str(TS)
    assert conn.archive_inserts == 1


# ════════════════════════════════════════════════════════════
# §8b T-DATE-08 Archive 불변성
# ════════════════════════════════════════════════════════════

def test_T_DATE_08_archive_immutability():
    """T-DATE-08: DATE 지원 추가 후 Archive 불변성 유지.

    - 정상 DATE confirm: Archive INSERT 1건, Archive UPDATE 없음
    - 기존 ATTACHMENT Archive 회귀 없음 (INSERT 1건)
    - UniqueViolation → 409 (중복 Archive INSERT 차단, 덮어쓰기 불가)
    """
    _render_stub = {
        "rendered_body": "<html/>",
        "source_trace_snapshot": [{"source": "tpl"}],
        "template_identity": "tpl",
        "evidence_manifest": [],
    }

    # 1. DATE 정상 confirm — Archive INSERT 1건, Archive UPDATE 없음
    conn = FakeConn(
        locked_row=_locked(runtime={"inspection_datetime": "2026-10-15"}),
        field_rows=[_date_field_row()],
        evidence_field_rows=[_date_ev_field()],
        evidence_candidate_row=_date_efc_row(),
    )
    _install(conn)
    with patch("services.document_confirm_svc.build_render_artifacts",
               return_value=_render_stub):
        with patch("services.document_confirm_svc.compute_confirmed_snapshot_hash",
                   return_value="a" * 64):
            result = confirm_document_atomic(DOC_ID, actor_id=None, comment="ok",
                                             current_user=_user())
    assert conn.archive_inserts == 1, "DATE confirm must create exactly one Archive row"
    assert result["status"] == "APPROVED_BY_HUMAN"
    # Archive에 대한 UPDATE SQL이 없어야 함
    for sql, _ in conn.executed:
        su = sql.upper()
        assert not ("UPDATE" in su and "ARCHIVE" in su), \
            f"Archive rows must be immutable (no UPDATE), got: {sql!r}"

    # 2. ATTACHMENT 회귀 — Archive INSERT 1건 (DATE 지원 추가 후에도 불변)
    conn2 = FakeConn(
        locked_row=_locked(runtime=_ATT_RUNTIME),
        field_rows=[_ATT_FIELD_ROW],
        evidence_field_rows=[_ATT_EV_FIELD],
        evidence_candidate_row=_ATT_EFC_ROW,
    )
    _install(conn2)
    sb = MagicMock()
    sb.storage.from_.return_value.download.return_value = _PDF_BYTES
    with patch("services.document_attachment_svc.get_supabase", return_value=sb):
        with patch("services.document_confirm_svc.build_render_artifacts",
                   return_value=_render_stub):
            with patch("services.document_confirm_svc.compute_confirmed_snapshot_hash",
                       return_value="b" * 64):
                confirm_document_atomic(DOC_ID, actor_id=None, comment="ok",
                                        current_user=_user())
    assert conn2.archive_inserts == 1, "ATTACHMENT regression: must still create exactly one Archive row"

    # 3. UniqueViolation → 409 (중복 Archive INSERT 차단)
    conn3 = FakeConn(
        locked_row=_locked(runtime={"inspection_datetime": "2026-10-15"}),
        field_rows=[_date_field_row()],
        evidence_field_rows=[_date_ev_field()],
        evidence_candidate_row=_date_efc_row(),
        fail_on={"INSERT INTO runtime_document_archive": FakeUniqueViolation("dup")},
    )
    _install(conn3)
    with patch("services.document_confirm_svc.build_render_artifacts",
               return_value=_render_stub):
        with patch("services.document_confirm_svc.compute_confirmed_snapshot_hash",
                   return_value="c" * 64):
            try:
                confirm_document_atomic(DOC_ID, actor_id=None, comment="ok",
                                        current_user=_user())
                assert False, "expected ConfirmError(409)"
            except ConfirmError as e:
                assert e.http_status == 409, f"UniqueViolation must map to 409, got {e.http_status}"
    assert conn3.rolled_back


# ════════════════════════════════════════════════════════════
# §9 교차 조합 차단 (E-01)
# ════════════════════════════════════════════════════════════

def test_E01_attachment_with_timestamp_auto_upload_type_blocks():
    """E-01: ATTACHMENT family + upload_type=timestamp_auto → 422 (교차 조합 차단)."""
    conn = FakeConn(
        locked_row=_locked(),
        field_rows=[_date_field_row(key="attached_doc", fid=_ATT_FIELD_ID, fc_id=_ATT_FC_ID)],
        evidence_field_rows=[{**_ATT_EV_FIELD, "upload_type": "timestamp_auto"}],
        evidence_candidate_row=_ATT_EFC_ROW,
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=_user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "upload_type" in e.detail
        assert "timestamp_auto" in e.detail
        assert "ATTACHMENT" in e.detail
    assert conn.rolled_back


def test_E01_date_with_attachment_upload_type_blocks():
    """E-01: DATE family + upload_type=attachment → 422 (교차 조합 차단)."""
    conn = FakeConn(
        locked_row=_locked(runtime={"inspection_datetime": "2026-10-15"}),
        field_rows=[_date_field_row()],
        evidence_field_rows=[{**_date_ev_field(), "upload_type": "attachment"}],
        evidence_candidate_row=_date_efc_row(),
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=_user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "upload_type" in e.detail
        assert "attachment" in e.detail
        assert "DATE" in e.detail
    assert conn.rolled_back


def test_E01_date_family_with_file_input_type_blocks():
    """E-01: DATE family + connected field input_type=file → 422 (교차 조합 차단)."""
    wrong_field = {**_date_field_row(), "input_type": "file"}
    conn = FakeConn(
        locked_row=_locked(runtime={"inspection_datetime": "2026-10-15"}),
        field_rows=[wrong_field],
        evidence_field_rows=[_date_ev_field()],
        evidence_candidate_row=_date_efc_row(),
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=_user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "input_type" in e.detail
        assert "file" in e.detail
        assert "DATE" in e.detail
    assert conn.rolled_back


def test_E01_attachment_family_with_date_input_type_blocks():
    """E-01: ATTACHMENT family + connected field input_type=date → 422 (교차 조합 차단)."""
    wrong_field = {**_ATT_FIELD_ROW, "input_type": "date"}
    conn = FakeConn(
        locked_row=_locked(),
        field_rows=[wrong_field],
        evidence_field_rows=[_ATT_EV_FIELD],
        evidence_candidate_row=_ATT_EFC_ROW,
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=_user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "input_type" in e.detail
        assert "date" in e.detail
        assert "ATTACHMENT" in e.detail
    assert conn.rolled_back


# ════════════════════════════════════════════════════════════
# §10 schema status / CANDIDATE_ONLY 회귀
# ════════════════════════════════════════════════════════════

def test_T_DATE_unapproved_schema_still_blocks():
    """DATE 증적이 있어도 schema=CANDIDATE → 422."""
    conn = FakeConn(
        locked_row=_locked(runtime={"inspection_datetime": "2026-10-15"}),
        schema_row={"id": SCHEMA_ID, "form_name": "test", "status": "CANDIDATE"},
        field_rows=[_date_field_row()],
        evidence_field_rows=[_date_ev_field()],
        evidence_candidate_row=_date_efc_row(),
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="ok", current_user=_user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "not approved" in e.detail.lower()
    assert conn.rolled_back
