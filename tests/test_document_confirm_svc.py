"""WP-DOCUMENT-ARCH-05B-B1 — confirm_document_atomic tests.

네트워크·실제 DB 없이 fake connection/cursor 로 트랜잭션 전 분기를 검증한다.
_connect 를 monkeypatch 하여 주입식 실패로 롤백을 확인한다.
05A 렌더러·Q4 해시·B0A authz 는 실제 모듈을 그대로 호출한다(순수).
"""

import hashlib
import sys
import datetime as _dt
from unittest.mock import MagicMock, patch

import services.document_confirm_svc as mod
from services.document_confirm_svc import confirm_document_atomic, ConfirmError


USER_ID = "11111111-1111-1111-1111-111111111111"
OTHER_ID = "99999999-9999-9999-9999-999999999999"
COMPANY_A = "aaaaaaaa-0001-0001-0001-000000000001"
COMPANY_B = "bbbbbbbb-0002-0002-0002-000000000002"
FACTORY_1 = "ffffffff-0001-0001-0001-000000000001"
DOC_ID = "dddddddd-0001-0001-0001-000000000001"
SCHEMA_ID = "ssssssss-0001-0001-0001-000000000001"
ARCHIVE_ID = "cccccccc-0001-0001-0001-000000000001"
TS = _dt.datetime(2026, 8, 23, 9, 0, 0, tzinfo=_dt.timezone.utc)


# ── Fake psycopg2 layer ─────────────────────────────────────────
class FakeUniqueViolation(Exception):
    pass


class FakeLockNotAvailable(Exception):
    pass


class FakeDeadlock(Exception):
    pass


class FakeQueryCanceled(Exception):
    pass


class FakeOperationalError(Exception):
    pass


class _FakeErrors:
    UniqueViolation = FakeUniqueViolation
    LockNotAvailable = FakeLockNotAvailable
    DeadlockDetected = FakeDeadlock
    QueryCanceled = FakeQueryCanceled


class _FakeExtras:
    class RealDictCursor:
        pass


class _FakePsycopg2:
    OperationalError = FakeOperationalError
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
        # 주입 실패 지점
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
            sealed["reviewed_by"] = params[1]
            sealed["reviewed_at"] = params[2]
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
        self.schema_row = kw.get("schema_row", {"id": SCHEMA_ID, "form_name": "테스트", "form_schema_id": SCHEMA_ID})
        self.field_rows = kw.get("field_rows", [])
        self.checklist_rows = kw.get("checklist_rows", [])
        self.evidence_field_rows = kw.get("evidence_field_rows", [])
        self.evidence_candidate_row = kw.get("evidence_candidate_row", None)
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


def _install(monkeypatch_conn, audit_calls=None):
    """mod 의 psycopg2/_connect/authz 의존을 fake 로 갈아끼운다."""
    import db.direct_sql as ds
    ds._connect = lambda: monkeypatch_conn
    # psycopg2 / errors 를 fake 로 (import psycopg2 는 함수 내부에서 일어남)
    sys.modules["psycopg2"] = _FakePsycopg2
    sys.modules["psycopg2.errors"] = _FakeErrors
    sys.modules["psycopg2.extras"] = _FakeExtras
    # audit 는 트랜잭션 밖 best-effort — 호출 여부만 관찰
    if audit_calls is not None:
        mod._best_effort_audit = lambda *a, **k: audit_calls.append(a)


def user(role_code="011", company_id=COMPANY_A, factory_id=None, uid=USER_ID):
    return {"id": uid, "role_code": role_code, "company_id": company_id, "factory_id": factory_id}


def locked(status="REVIEW_PENDING", company_id=COMPANY_A, factory_id=None, version=1,
           runtime=None, evidence=None, submitted_by=USER_ID):
    return {"id": DOC_ID, "form_schema_id": SCHEMA_ID, "status": status,
            "company_id": company_id, "factory_id": factory_id, "version": version,
            "submitted_by": submitted_by,
            "runtime_data_json": {} if runtime is None else runtime,
            "evidence_links": [] if evidence is None else evidence}


# ════════════════════════════════════════════════════════════
# 1. 정상 confirm
def test_01_normal_confirm():
    audit = []
    conn = FakeConn(locked_row=locked())
    _install(conn, audit)
    out = confirm_document_atomic(DOC_ID, actor_id=None, comment="검토완료",
                                  current_user=user())
    assert conn.committed and not conn.rolled_back and conn.closed
    assert conn.archive_inserts == 1 and conn.approval_inserts == 1 and conn.status_updates == 1
    assert out["status"] == "APPROVED_BY_HUMAN"
    assert out["reviewed_by"] == USER_ID
    assert len(audit) == 1  # best-effort audit 1회


# 2. actor spoof → 403
def test_02_actor_spoof_403():
    conn = FakeConn(locked_row=locked())
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=OTHER_ID, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 403
    assert conn.rolled_back and conn.archive_inserts == 0


# 3. (B1-CORR-01 반전) role 012 + 본인 제출 → PASS (role 은 판정 기준 아님)
def test_03_role_012_self_submitted_pass():
    conn = FakeConn(locked_row=locked(submitted_by=USER_ID))
    _install(conn)
    out = confirm_document_atomic(DOC_ID, actor_id=None, comment="ok",
                                  current_user=user(role_code="012", uid=USER_ID))
    assert conn.committed and out["status"] == "APPROVED_BY_HUMAN"


# 4. role 011 same company → PASS
def test_04_role_011_same_company_pass():
    conn = FakeConn(locked_row=locked(company_id=COMPANY_A))
    _install(conn)
    out = confirm_document_atomic(DOC_ID, actor_id=None, comment="ok",
                                  current_user=user(role_code="011", company_id=COMPANY_A))
    assert conn.committed and out["status"] == "APPROVED_BY_HUMAN"


# 5. cross-company → 404
def test_05_cross_company_404():
    conn = FakeConn(locked_row=locked(company_id=COMPANY_B))
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x",
                                current_user=user(company_id=COMPANY_A))
        assert False
    except ConfirmError as e:
        assert e.http_status == 404
    assert conn.rolled_back


# 6. ownership metadata conflict → 404
def test_06_ownership_conflict_404():
    conn = FakeConn(locked_row=locked(company_id=COMPANY_A, factory_id=FACTORY_1),
                    factory_row={"company_id": COMPANY_B})  # 충돌
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x",
                                current_user=user(company_id=COMPANY_A))
        assert False
    except ConfirmError as e:
        assert e.http_status == 404
    assert conn.rolled_back


# 7. REVIEW_PENDING 아님 → 409
def test_07_not_review_pending_409():
    conn = FakeConn(locked_row=locked(status="DRAFT"))
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 409
    assert conn.rolled_back and conn.archive_inserts == 0


# 8. transition rule 없음 → 409
def test_08_no_transition_rule_409():
    conn = FakeConn(locked_row=locked(),
                    rule_row=None)
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 409
    assert conn.rolled_back


# 9. comment 없음 → 422
def test_09_missing_comment_422():
    conn = FakeConn(locked_row=locked())
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="  ", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
    assert conn.rolled_back


# 10. renderer failure → rollback
def test_10_renderer_failure_rollback():
    # 05A 렌더러 실제 실패조건: runtime_field 가 다른 schema 소속이면 SchemaRenderError.
    # svc 의 version/schema gate 를 통과한 뒤 build_render_artifacts 에서 422 로 변환된다.
    conn = FakeConn(locked_row=locked(),
                    field_rows=[{"id": "fld1", "form_schema_id": "OTHER_SCHEMA",
                                 "field_key": "k", "field_order": 1}])
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
    assert conn.rolled_back and conn.archive_inserts == 0


# 11. hash failure → rollback
def test_11_hash_failure_rollback(monkeypatch=None):
    conn = FakeConn(locked_row=locked())
    _install(conn)
    orig = mod.compute_confirmed_snapshot_hash
    def boom(**k):
        from services.document_snapshot_integrity import SnapshotCanonicalizationError
        raise SnapshotCanonicalizationError("forced")
    mod.compute_confirmed_snapshot_hash = boom
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
    finally:
        mod.compute_confirmed_snapshot_hash = orig
    assert conn.rolled_back and conn.archive_inserts == 0


# 12. archive insert failure → rollback
def test_12_archive_insert_failure_rollback():
    conn = FakeConn(locked_row=locked(),
                    fail_on={"INSERT INTO runtime_document_archive": RuntimeError("archive fail")})
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 500
    assert conn.rolled_back and conn.approval_inserts == 0 and conn.status_updates == 0


# 13. approval insert failure → rollback
def test_13_approval_insert_failure_rollback():
    conn = FakeConn(locked_row=locked(),
                    fail_on={"INSERT INTO runtime_document_approval": RuntimeError("approval fail")})
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 500
    assert conn.rolled_back and conn.status_updates == 0


# 14. rdd seal failure → rollback
def test_14_rdd_seal_failure_rollback():
    conn = FakeConn(locked_row=locked(),
                    fail_on={"UPDATE runtime_document_data": RuntimeError("seal fail")})
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 500
    assert conn.rolled_back and not conn.committed


# 15. duplicate version → 409
def test_15_duplicate_version_409():
    conn = FakeConn(locked_row=locked(),
                    fail_on={"INSERT INTO runtime_document_archive": FakeUniqueViolation("dup")})
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 409
    assert conn.rolled_back


# 16. concurrent / stale second approval → 409 (락 후 status가 이미 APPROVED)
def test_16_stale_second_approval_409():
    conn = FakeConn(locked_row=locked(status="APPROVED_BY_HUMAN"))
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 409
    assert conn.rolled_back and conn.archive_inserts == 0


# 17. timestamp 동일성 (archive/approval/rdd 모두 같은 TS)
def test_17_timestamp_identical():
    conn = FakeConn(locked_row=locked())
    _install(conn)
    confirm_document_atomic(DOC_ID, actor_id=None, comment="ok", current_user=user())
    # archive INSERT params 의 confirmed_at, approval reviewed_at, update reviewed_at 모두 TS
    archive_params = next(p for (s, p) in conn.executed if "INSERT INTO runtime_document_archive" in s)
    approval_params = next(p for (s, p) in conn.executed if "INSERT INTO runtime_document_approval" in s)
    update_params = next(p for (s, p) in conn.executed if "UPDATE runtime_document_data" in s)
    # archive: (...) confirmed_at 는 index 3
    assert archive_params[3] == TS
    # approval: (doc, reviewer, reviewed_at=TS, ...)
    assert approval_params[2] == TS
    # update: (status, reviewer, reviewed_at=TS, comment, updated_at=TS, id)
    assert update_params[2] == TS and update_params[4] == TS


# 18. snapshot_id = 실제 archive.id
def test_18_snapshot_id_is_archive_id():
    conn = FakeConn(locked_row=locked())
    _install(conn)
    confirm_document_atomic(DOC_ID, actor_id=None, comment="ok", current_user=user())
    approval_params = next(p for (s, p) in conn.executed if "INSERT INTO runtime_document_approval" in s)
    # approval params: (doc, reviewer, reviewed_at, comment, snapshot_id, runtime, evidence, source_trace)
    assert approval_params[4] == ARCHIVE_ID


# 19. confirmed_by / reviewer / reviewed_by 모두 auth user
def test_19_all_ids_are_auth_user():
    conn = FakeConn(locked_row=locked())
    _install(conn)
    confirm_document_atomic(DOC_ID, actor_id=USER_ID, comment="ok", current_user=user(uid=USER_ID))
    archive_params = next(p for (s, p) in conn.executed if "INSERT INTO runtime_document_archive" in s)
    approval_params = next(p for (s, p) in conn.executed if "INSERT INTO runtime_document_approval" in s)
    update_params = next(p for (s, p) in conn.executed if "UPDATE runtime_document_data" in s)
    assert archive_params[4] == USER_ID     # archive.confirmed_by
    assert approval_params[1] == USER_ID     # approval.reviewer_id
    assert update_params[1] == USER_ID       # rdd.reviewed_by


# 20. 기존 _approval() 은 APPROVE 경로에서 호출되지 않는다
def test_20_existing_approval_not_called():
    import services.document_engine_svc as legacy
    calls = []
    orig = legacy._approval
    legacy._approval = lambda *a, **k: calls.append(a)
    conn = FakeConn(locked_row=locked())
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="ok", current_user=user())
    finally:
        legacy._approval = orig
    assert calls == []  # 기존 _approval 미호출


# ════════════════════════════════════════════════════════════
# B1-CORR-01 추가: submitter-as-confirmer
# ════════════════════════════════════════════════════════════

# B1. worker 014 self-submitted confirm → PASS
def test_B1_worker_014_self_submitted_pass():
    conn = FakeConn(locked_row=locked(submitted_by=USER_ID))
    _install(conn)
    out = confirm_document_atomic(DOC_ID, actor_id=None, comment="ok",
                                  current_user=user(role_code="014", uid=USER_ID))
    assert conn.committed and out["status"] == "APPROVED_BY_HUMAN"
    assert conn.archive_inserts == 1 and conn.approval_inserts == 1 and conn.status_updates == 1


# B2. safety manager 012 self-submitted confirm → PASS
def test_B2_safety_012_self_submitted_pass():
    conn = FakeConn(locked_row=locked(submitted_by=USER_ID))
    _install(conn)
    out = confirm_document_atomic(DOC_ID, actor_id=None, comment="ok",
                                  current_user=user(role_code="012", uid=USER_ID))
    assert conn.committed and out["status"] == "APPROVED_BY_HUMAN"


# B3. admin 001 이지만 다른 사람이 제출 → 403 + rollback
def test_B3_admin_other_submitter_403():
    conn = FakeConn(locked_row=locked(submitted_by=OTHER_ID))
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x",
                                current_user=user(role_code="001", uid=USER_ID))
        assert False
    except ConfirmError as e:
        assert e.http_status == 403
    assert conn.rolled_back and conn.archive_inserts == 0


# B4. submitted_by NULL → 409 + rollback
def test_B4_submitter_null_409():
    conn = FakeConn(locked_row=locked(submitted_by=None))
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 409
    assert conn.rolled_back and conn.archive_inserts == 0


# B5. confirmed_by / reviewer_id / reviewed_by = submitted_by = auth user
def test_B5_all_ids_equal_submitter():
    conn = FakeConn(locked_row=locked(submitted_by=USER_ID))
    _install(conn)
    confirm_document_atomic(DOC_ID, actor_id=USER_ID, comment="ok",
                            current_user=user(uid=USER_ID))
    archive_params = next(p for (s, p) in conn.executed if "INSERT INTO runtime_document_archive" in s)
    approval_params = next(p for (s, p) in conn.executed if "INSERT INTO runtime_document_approval" in s)
    update_params = next(p for (s, p) in conn.executed if "UPDATE runtime_document_data" in s)
    # archive.confirmed_by(idx4) / approval.reviewer_id(idx1) / rdd.reviewed_by(idx1) 모두 USER_ID
    # 그리고 locked.submitted_by 도 USER_ID → 4자 동일성
    assert archive_params[4] == USER_ID
    assert approval_params[1] == USER_ID
    assert update_params[1] == USER_ID
    assert conn.locked_row["submitted_by"] == USER_ID


# B6. (hardening) seal UPDATE 가 행을 반환하지 않으면 500 + rollback
def test_B6_seal_returns_no_row_500():
    conn = FakeConn(locked_row=locked(submitted_by=USER_ID))
    # UPDATE 는 성공하지만 RETURNING 이 None 인 상황을 강제
    class _NoRowCursor(FakeCursor):
        def execute(self, sql, params=None):
            super().execute(sql, params)
            if "UPDATE RUNTIME_DOCUMENT_DATA" in sql.strip().upper():
                self.conn._last = None  # RETURNING 없음
    conn.cursor = lambda cursor_factory=None: _NoRowCursor(conn)
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="ok", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 500
    assert conn.rolled_back and not conn.committed


# ════════════════════════════════════════════════════════════
# B7~B9 — 첨부 이미지 봉인 경로 (C1/C2/C3)

_IMG_FIELD_ID = "ffffffff-imag-imag-imag-000000000001"
_PNG_BYTES_CONF = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
_IMG_SHA_CONF = hashlib.sha256(_PNG_BYTES_CONF).hexdigest()
_IMG_STORAGE_REF = (
    f"storage://company-docs/attachments/document/"
    f"{DOC_ID}/{_IMG_FIELD_ID}/{_IMG_SHA_CONF}.png"
)
_IMAGE_RUNTIME = {
    "site_photo": {
        "_type": "file_snapshot",
        "field_key": "site_photo",
        "field_id": _IMG_FIELD_ID,
        "storage_ref": _IMG_STORAGE_REF,
        "sha256": _IMG_SHA_CONF,
        "mime_type": "image/png",
        "byte_size": len(_PNG_BYTES_CONF),
        "original_file_name": "photo.png",
        "uploaded_by_user_id": USER_ID,
        "uploaded_at": "2026-10-25T00:00:00Z",
    }
}
_IMAGE_FIELD_ROWS = [
    {
        "id": _IMG_FIELD_ID,
        "field_key": "site_photo",
        "input_type": "image",
        "field_label": "현장사진",
        "field_order": 1,
        "required_status": "OPTIONAL",
    }
]


def test_B7_confirm_calls_resolve_with_strict_and_doc_id():
    """confirm_document_atomic calls resolve_attachment_images_for_render with strict=True
    and document_id=str(doc_id), ensuring C1/C2/C3 binding contract is enforced."""
    conn = FakeConn(locked_row=locked())
    _install(conn)

    captured = []

    def spy_resolve(runtime_data_json, fields, document_id=None, strict=False):
        captured.append({"document_id": document_id, "strict": strict})
        return {}

    with patch("services.document_confirm_svc.resolve_attachment_images_for_render",
               side_effect=spy_resolve):
        confirm_document_atomic(DOC_ID, actor_id=None, comment="검토완료",
                                current_user=user())

    assert len(captured) == 1
    assert captured[0]["strict"] is True
    assert captured[0]["document_id"] == str(DOC_ID)
    assert conn.committed and not conn.rolled_back


def test_B8_confirm_fails_when_attachment_image_unreachable():
    """confirm raises ConfirmError(422) when image snap exists but storage fetch fails.
    Transaction must be rolled back (봉인 차단)."""
    conn = FakeConn(
        locked_row=locked(runtime=_IMAGE_RUNTIME),
        field_rows=_IMAGE_FIELD_ROWS,
    )
    _install(conn)

    sb = MagicMock()
    sb.storage.from_.return_value.download.side_effect = RuntimeError("storage down")

    with patch("services.document_attachment_svc.get_supabase", return_value=sb):
        try:
            confirm_document_atomic(DOC_ID, actor_id=None, comment="검토완료",
                                    current_user=user())
            assert False, "expected ConfirmError"
        except ConfirmError as e:
            assert e.http_status == 422
            assert "attachment" in e.detail.lower()

    assert conn.rolled_back and not conn.committed


def test_B9_confirm_fails_when_image_path_mismatch():
    """confirm raises ConfirmError(422) when image storage_ref path doesn't match
    the expected doc_id/field_id prefix (cross-document reference blocked)."""
    import copy

    bad_runtime = copy.deepcopy(_IMAGE_RUNTIME)
    bad_runtime["site_photo"]["storage_ref"] = (
        "storage://company-docs/attachments/document/WRONG-DOC-ID/field-xyz/abc123.png"
    )

    conn = FakeConn(
        locked_row=locked(runtime=bad_runtime),
        field_rows=_IMAGE_FIELD_ROWS,
    )
    _install(conn)

    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="검토완료",
                                current_user=user())
        assert False, "expected ConfirmError"
    except ConfirmError as e:
        assert e.http_status == 422
        assert "attachment" in e.detail.lower()

    assert conn.rolled_back and not conn.committed


def test_B10_confirm_fails_when_sha256_missing():
    """confirm raises ConfirmError(422) when image snap has no sha256 (strict blocks)."""
    import copy

    bad_runtime = copy.deepcopy(_IMAGE_RUNTIME)
    bad_runtime["site_photo"]["sha256"] = None

    conn = FakeConn(
        locked_row=locked(runtime=bad_runtime),
        field_rows=_IMAGE_FIELD_ROWS,
    )
    _install(conn)

    sb = MagicMock()
    sb.storage.from_.return_value.download.return_value = _PNG_BYTES_CONF

    with patch("services.document_attachment_svc.get_supabase", return_value=sb):
        try:
            confirm_document_atomic(DOC_ID, actor_id=None, comment="검토완료",
                                    current_user=user())
            assert False, "expected ConfirmError"
        except ConfirmError as e:
            assert e.http_status == 422
            assert "attachment" in e.detail.lower()

    assert conn.rolled_back and not conn.committed


def test_B11_confirm_fails_when_snapshot_malformed():
    """confirm raises ConfirmError(422) when image field holds a malformed (non-file_snapshot) value."""
    bad_runtime = {"site_photo": {"_type": "WRONG_TYPE", "some": "data"}}

    conn = FakeConn(
        locked_row=locked(runtime=bad_runtime),
        field_rows=_IMAGE_FIELD_ROWS,
    )
    _install(conn)

    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="검토완료",
                                current_user=user())
        assert False, "expected ConfirmError"
    except ConfirmError as e:
        assert e.http_status == 422
        assert "attachment" in e.detail.lower()

    assert conn.rolled_back and not conn.committed


def test_B12_confirm_with_valid_image_forwards_base64_to_renderer():
    """Valid image snap → build_render_artifacts receives attachment_images with base64 URI
    (봉인된 rendered_body에 Base64 포함 증거)."""
    import base64 as _b64

    conn = FakeConn(
        locked_row=locked(runtime=_IMAGE_RUNTIME),
        field_rows=_IMAGE_FIELD_ROWS,
    )
    _install(conn)

    sb = MagicMock()
    sb.storage.from_.return_value.download.return_value = _PNG_BYTES_CONF

    captured_kwargs: list = []

    def spy_render(*args, **kwargs):
        captured_kwargs.append(kwargs)
        return {
            "rendered_body": "<html/>",
            "source_trace_snapshot": [],
            "template_identity": "tpl",
            "evidence_manifest": [],
        }

    with (
        patch("services.document_attachment_svc.get_supabase", return_value=sb),
        patch("services.document_confirm_svc.build_render_artifacts", side_effect=spy_render),
        patch("services.document_confirm_svc.compute_confirmed_snapshot_hash",
              return_value="a" * 64),
    ):
        confirm_document_atomic(DOC_ID, actor_id=None, comment="검토완료",
                                current_user=user())

    assert conn.committed and not conn.rolled_back
    assert len(captured_kwargs) == 1
    ai = captured_kwargs[0].get("attachment_images", {})
    assert "site_photo" in ai
    expected_uri = "data:image/png;base64," + _b64.b64encode(_PNG_BYTES_CONF).decode()
    assert ai["site_photo"] == expected_uri


def test_B13_real_archive_rendered_body_contains_base64_image():
    """Real build_render_artifacts + compute_confirmed_snapshot_hash:
    archived rendered_body contains the Base64 image and snapshot_hash is a valid hex string
    computed from that rendered_body (봉인 HTML·Hash 일치 증거)."""
    import base64 as _b64
    import re

    # Fields need form_schema_id so the real renderer accepts them
    _fields_with_schema = [{**r, "form_schema_id": SCHEMA_ID} for r in _IMAGE_FIELD_ROWS]

    conn = FakeConn(
        locked_row=locked(runtime=_IMAGE_RUNTIME),
        field_rows=_fields_with_schema,
    )

    # Intercept archive INSERT to capture rendered_body and snapshot_hash params
    class _CaptureCursor(FakeCursor):
        def execute(self, sql, params=None):
            super().execute(sql, params)
            if "INSERT INTO RUNTIME_DOCUMENT_ARCHIVE" in sql.strip().upper():
                self.conn._archive_params = params
    conn.cursor = lambda cursor_factory=None: _CaptureCursor(conn)

    _install(conn)

    sb = MagicMock()
    sb.storage.from_.return_value.download.return_value = _PNG_BYTES_CONF

    with patch("services.document_attachment_svc.get_supabase", return_value=sb):
        confirm_document_atomic(DOC_ID, actor_id=None, comment="검토완료",
                                current_user=user())

    assert conn.committed and not conn.rolled_back

    # params[8] = rendered_body, params[10] = snapshot_hash (see INSERT column order)
    rendered_body: str = conn._archive_params[8]
    snapshot_hash: str = conn._archive_params[10]

    expected_b64 = _b64.b64encode(_PNG_BYTES_CONF).decode()
    assert "data:image/png;base64," in rendered_body, (
        "rendered_body does not contain image data URI"
    )
    assert expected_b64 in rendered_body, (
        "rendered_body does not contain expected PNG base64"
    )

    assert re.fullmatch(r"[0-9a-f]{64}", snapshot_hash), (
        "snapshot_hash is not a 64-char hex: %r" % snapshot_hash
    )


# ── Evidence gate tests (WO-024) ──────────────────────────────

def _field_ev(fid, key, input_type="text", field_candidate_id=None, **kw):
    """Helper: runtime_field row with optional field_candidate_id."""
    return {
        "id": fid,
        "field_key": key,
        "input_type": input_type,
        "field_label": key,
        "form_schema_id": SCHEMA_ID,
        "field_order": 1,
        "required_status": "REQUIRED_BY_HUMAN",
        "field_candidate_id": field_candidate_id,
        **kw,
    }


def _fake_storage_noop():
    sb = MagicMock()
    sb.storage.from_.return_value.download.return_value = b""
    return sb


def test_E24_01_no_evidence_fields_passes():
    """E24-11 regression: document without evidence fields seals normally."""
    conn = FakeConn(
        locked_row=locked(),
        field_rows=[_field_ev("f1", "company_name")],
        checklist_rows=[],
        evidence_field_rows=[],
    )
    _install(conn)
    with patch("services.document_attachment_svc.get_supabase",
               return_value=_fake_storage_noop()):
        with patch("services.document_signature_svc.get_supabase",
                   return_value=_fake_storage_noop()):
            result = confirm_document_atomic(
                DOC_ID, actor_id=None, comment="ok", current_user=user()
            )
    assert result["status"] == "APPROVED_BY_HUMAN"


def test_E24_09_candidate_evidence_status_blocks_confirm():
    """E24-09: LEG UNKNOWN (CANDIDATE evidence_field_candidate) → ConfirmError(422)."""
    conn = FakeConn(
        locked_row=locked(runtime={"attached_documents": {
            "_type": "file_snapshot",
            "field_key": "attached_documents",
            "field_id": "f-attached",
            "storage_ref": f"storage://company-docs/attachments/document/{DOC_ID}/f-attached/abc.pdf",
            "sha256": "a" * 64,
            "mime_type": "application/pdf",
            "byte_size": 100,
        }}),
        field_rows=[_field_ev("f-attached", "attached_documents",
                              input_type="file", field_candidate_id="fc-001")],
        checklist_rows=[],
        evidence_field_rows=[{
            "id": "ev-001",
            "form_schema_id": SCHEMA_ID,
            "evidence_candidate_id": "efc-001",
            "evidence_type": "ATTACHMENT",
        }],
        evidence_candidate_row={
            "id": "efc-001",
            "field_candidate_id": "fc-001",
            "status": "CANDIDATE",  # LEG not confirmed
        },
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False, "expected ConfirmError"
    except ConfirmError as e:
        assert e.http_status == 422
        assert "LEGAL_REQUIREDNESS=UNKNOWN" in e.detail
    assert conn.rolled_back and conn.archive_inserts == 0


def test_E24_02_evidence_connection_missing_candidate_id_blocks():
    """E24-02: evidence_candidate_id missing → ConfirmError(422)."""
    conn = FakeConn(
        locked_row=locked(),
        field_rows=[_field_ev("f-attached", "attached_documents",
                              input_type="file", field_candidate_id="fc-001")],
        checklist_rows=[],
        evidence_field_rows=[{
            "id": "ev-001",
            "form_schema_id": SCHEMA_ID,
            "evidence_candidate_id": None,  # missing
            "evidence_type": "ATTACHMENT",
        }],
        evidence_candidate_row=None,
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False, "expected ConfirmError"
    except ConfirmError as e:
        assert e.http_status == 422
        assert "evidence_candidate_id missing" in e.detail
    assert conn.rolled_back and conn.archive_inserts == 0
