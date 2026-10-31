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
        self.schema_row = kw.get("schema_row", {"id": SCHEMA_ID, "form_name": "테스트", "form_schema_id": SCHEMA_ID, "status": "APPROVED_FOR_RUNTIME_USE"})
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
            "status": "APPROVED_BY_HUMAN",
            "evidence_family": "ATTACHMENT",
            "upload_type": "attachment",
        }],
        evidence_candidate_row={
            "id": "efc-001",
            "field_candidate_id": "fc-001",
            "status": "CANDIDATE",  # evidence approval gate 미통과
            "schema_candidate_id": None,
        },
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False, "expected ConfirmError"
    except ConfirmError as e:
        assert e.http_status == 422
        assert "not approved" in e.detail.lower()
        assert "CANDIDATE" in e.detail
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
            "status": "APPROVED_BY_HUMAN",
            "evidence_family": "ATTACHMENT",
            "upload_type": "attachment",
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


# ── R1 보강 테스트 (WO-024-R1) ──────────────────────────────────

def test_R1_T03_unknown_evidence_status_blocks():
    """R1-T03: evidence_field_candidate.status=UNKNOWN → 422 (allowlist 차단)."""
    conn = FakeConn(
        locked_row=locked(runtime={"attached_documents": {
            "_type": "file_snapshot",
            "field_key": "attached_documents",
            "field_id": "f-att",
            "storage_ref": f"storage://company-docs/attachments/document/{DOC_ID}/f-att/abc.pdf",
            "sha256": "a" * 64,
            "mime_type": "application/pdf",
            "byte_size": 100,
        }}),
        field_rows=[_field_ev("f-att", "attached_documents", input_type="file", field_candidate_id="fc-u")],
        evidence_field_rows=[{"id": "ev-u", "form_schema_id": SCHEMA_ID,
                               "evidence_candidate_id": "efc-u", "evidence_type": "ATTACHMENT",
                               "status": "APPROVED_BY_HUMAN",
                               "evidence_family": "ATTACHMENT", "upload_type": "attachment"}],
        evidence_candidate_row={"id": "efc-u", "field_candidate_id": "fc-u",
                                 "status": "UNKNOWN", "schema_candidate_id": None},
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "not approved" in e.detail.lower()
    assert conn.rolled_back


def test_R1_T03b_null_evidence_status_blocks():
    """R1-T03b: evidence_field_candidate.status=NULL → defaults to UNKNOWN → 422."""
    conn = FakeConn(
        locked_row=locked(runtime={"attached_documents": {
            "_type": "file_snapshot",
            "field_key": "attached_documents",
            "field_id": "f-null",
            "storage_ref": f"storage://company-docs/attachments/document/{DOC_ID}/f-null/abc.pdf",
            "sha256": "b" * 64,
            "mime_type": "application/pdf",
            "byte_size": 100,
        }}),
        field_rows=[_field_ev("f-null", "attached_documents", input_type="file", field_candidate_id="fc-n")],
        evidence_field_rows=[{"id": "ev-n", "form_schema_id": SCHEMA_ID,
                               "evidence_candidate_id": "efc-n", "evidence_type": "ATTACHMENT",
                               "status": "APPROVED_BY_HUMAN",
                               "evidence_family": "ATTACHMENT", "upload_type": "attachment"}],
        evidence_candidate_row={"id": "efc-n", "field_candidate_id": "fc-n",
                                 "status": None, "schema_candidate_id": None},
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "not approved" in e.detail.lower()
    assert conn.rolled_back


def test_R1_T05_unapproved_schema_status_blocks():
    """R1-T05: runtime schema status=CANDIDATE → 422 (봉인 차단)."""
    conn = FakeConn(
        locked_row=locked(),
        schema_row={"id": SCHEMA_ID, "form_name": "test", "status": "CANDIDATE"},
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="ok", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "not approved" in e.detail.lower()
    assert conn.rolled_back


def test_R1_T06_candidate_only_field_blocks():
    """R1-T06: CANDIDATE_ONLY 필드 존재 → 422 (봉인 차단)."""
    conn = FakeConn(
        locked_row=locked(),
        field_rows=[
            _field_ev("f-req", "company_name", required_status="REQUIRED_BY_HUMAN"),
            _field_ev("f-cand", "candidate_field", required_status="CANDIDATE_ONLY"),
        ],
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="ok", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "CANDIDATE_ONLY" in e.detail
    assert conn.rolled_back


def test_R1_T07_non_file_evidence_input_type_blocks():
    """R1-T07: Evidence 연결 필드가 file이 아닌 경우(text) → 422."""
    conn = FakeConn(
        locked_row=locked(runtime={"some_text": "value"}),
        field_rows=[_field_ev("f-txt", "some_text", input_type="text", field_candidate_id="fc-txt")],
        evidence_field_rows=[{"id": "ev-txt", "form_schema_id": SCHEMA_ID,
                               "evidence_candidate_id": "efc-txt", "evidence_type": "TEXT_REF",
                               "status": "APPROVED_BY_HUMAN",
                               "evidence_family": "ATTACHMENT", "upload_type": "attachment"}],
        evidence_candidate_row={"id": "efc-txt", "field_candidate_id": "fc-txt",
                                 "status": "APPROVED_BY_HUMAN", "schema_candidate_id": None},
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "input_type" in e.detail
        assert "text" in e.detail
    assert conn.rolled_back


# ── R2 보강 테스트 (WO-024-R2) ──────────────────────────────────

def _ev_row_approved(ev_id="ev-r2", efc_id="efc-r2"):
    """Helper: runtime_evidence_field row that passes all R2 checks (C2-FINAL §3)."""
    return {
        "id": ev_id,
        "form_schema_id": SCHEMA_ID,
        "evidence_candidate_id": efc_id,
        "evidence_type": "ATTACHMENT",
        "status": "APPROVED_BY_HUMAN",
        "evidence_family": "ATTACHMENT",
        "upload_type": "attachment",
    }


def _efc_row_approved(efc_id="efc-r2", fc_id="fc-r2", sc_id="sc-001"):
    """Helper: evidence_field_candidate row that passes all R2 checks (C2-FINAL §2 D1)."""
    return {"id": efc_id, "field_candidate_id": fc_id,
            "status": "APPROVED_BY_HUMAN", "schema_candidate_id": sc_id}


def test_R2_T01_unapproved_evidence_field_status_blocks():
    """R2-T01: runtime_evidence_field.status=CANDIDATE → 422 (R2-01)."""
    conn = FakeConn(
        locked_row=locked(),
        field_rows=[_field_ev("f-r2", "attached_documents", input_type="file", field_candidate_id="fc-r2")],
        evidence_field_rows=[{
            **_ev_row_approved(),
            "status": "CANDIDATE",  # not approved
        }],
        evidence_candidate_row=_efc_row_approved(),
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "runtime_evidence_field.status" in e.detail
        assert "CANDIDATE" in e.detail
    assert conn.rolled_back


def test_R2_T02_null_evidence_field_status_blocks():
    """R2-T02: runtime_evidence_field.status=NULL → defaults to UNKNOWN → 422 (R2-01)."""
    conn = FakeConn(
        locked_row=locked(),
        field_rows=[_field_ev("f-r2", "attached_documents", input_type="file", field_candidate_id="fc-r2")],
        evidence_field_rows=[{
            **_ev_row_approved(),
            "status": None,
        }],
        evidence_candidate_row=_efc_row_approved(),
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "runtime_evidence_field.status" in e.detail
    assert conn.rolled_back


def test_R2_T03_unsupported_evidence_family_blocks():
    """R2-T03: evidence_family=IMAGE_CAPTURE (not ATTACHMENT) → 422 (R2-03)."""
    conn = FakeConn(
        locked_row=locked(),
        field_rows=[_field_ev("f-r2", "attached_documents", input_type="file", field_candidate_id="fc-r2")],
        evidence_field_rows=[{
            **_ev_row_approved(),
            "evidence_family": "IMAGE_CAPTURE",
        }],
        evidence_candidate_row=_efc_row_approved(),
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "evidence_family" in e.detail
        assert "IMAGE_CAPTURE" in e.detail
    assert conn.rolled_back


def test_R2_T04_unsupported_upload_type_blocks():
    """R2-T04: upload_type=image_upload (not attachment) → 422 (R2-03)."""
    conn = FakeConn(
        locked_row=locked(),
        field_rows=[_field_ev("f-r2", "attached_documents", input_type="file", field_candidate_id="fc-r2")],
        evidence_field_rows=[{
            **_ev_row_approved(),
            "upload_type": "image_upload",
        }],
        evidence_candidate_row=_efc_row_approved(),
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "upload_type" in e.detail
        assert "image_upload" in e.detail
    assert conn.rolled_back


def test_R2_T05_schema_candidate_mismatch_blocks():
    """R2-T05: evidence_field_candidate.schema_candidate_id != schema_candidate_id → 422 (R2-C2)."""
    conn = FakeConn(
        locked_row=locked(),
        schema_row={"id": SCHEMA_ID, "form_name": "테스트", "status": "APPROVED_FOR_RUNTIME_USE",
                    "schema_candidate_id": "sc-correct"},
        field_rows=[_field_ev("f-r2", "attached_documents", input_type="file", field_candidate_id="fc-r2")],
        evidence_field_rows=[_ev_row_approved()],
        evidence_candidate_row={
            **_efc_row_approved(),
            "schema_candidate_id": "sc-wrong",  # mismatch
        },
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "schema candidate mismatch" in e.detail
        assert "sc-wrong" in e.detail
        assert "sc-correct" in e.detail
    assert conn.rolled_back


def test_R2_T06_schema_candidate_id_empty_skips_c2_check():
    """R2-T06: schema_candidate_id absent → C2 check skipped (no mismatch error raised).

    The confirm proceeds past the C2 gate and fails later at FileSnapshot validation,
    proving schema candidate mismatch was NOT the blocker.
    """
    conn = FakeConn(
        locked_row=locked(),  # no runtime_data_json → FileSnapshot missing triggers later
        schema_row={"id": SCHEMA_ID, "form_name": "테스트", "status": "APPROVED_FOR_RUNTIME_USE"},
        field_rows=[_field_ev("f-r2", "attached_documents", input_type="file", field_candidate_id="fc-r2")],
        evidence_field_rows=[_ev_row_approved()],
        evidence_candidate_row=_efc_row_approved(),  # has schema_candidate_id="sc-001", C2 skipped
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "schema candidate mismatch" not in e.detail, (
            "C2 check must be skipped when schema_candidate_id is absent"
        )
        assert "FileSnapshot missing" in e.detail or "evidence" in e.detail.lower()
    assert conn.rolled_back


# ── C3 신규 테스트 (WO-027-C2-FINAL §7-2 / C3-T01~T04, T10) ──────────────────

def test_C3_T01_approved_by_human_evidence_field_passes_r2():
    """C3-T01: runtime_evidence_field.status=APPROVED_BY_HUMAN → R2-01 통과 (C2-FINAL §3)."""
    conn = FakeConn(
        locked_row=locked(runtime={"attached_documents": {
            "_type": "file_snapshot",
            "field_key": "attached_documents",
            "field_id": "f-c3t01",
            "storage_ref": f"storage://company-docs/attachments/document/{DOC_ID}/f-c3t01/ev.pdf",
            "sha256": "c" * 64,
            "mime_type": "application/pdf",
            "byte_size": 100,
        }}),
        field_rows=[_field_ev("f-c3t01", "attached_documents", input_type="file",
                              field_candidate_id="fc-c3t01")],
        evidence_field_rows=[{
            "id": "ev-c3t01",
            "form_schema_id": SCHEMA_ID,
            "evidence_candidate_id": "efc-c3t01",
            "evidence_type": "ATTACHMENT",
            "status": "APPROVED_BY_HUMAN",   # C2-FINAL §3 터미널 승인값
            "evidence_family": "ATTACHMENT",
            "upload_type": "attachment",
        }],
        evidence_candidate_row={
            "id": "efc-c3t01",
            "field_candidate_id": "fc-c3t01",
            "status": "APPROVED_BY_HUMAN",   # C2-FINAL §2 D1 승인값
            "schema_candidate_id": None,
        },
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="ok", current_user=user())
    except ConfirmError as e:
        # R2-01 또는 R1-02에서 차단되면 안 됨 — "not approved" 포함 오류는 테스트 실패
        assert "not approved" not in e.detail.lower(), (
            f"C3-T01: APPROVED_BY_HUMAN should pass R2-01 and R1-02, got: {e.detail}"
        )


def test_C3_T02_candidate_evidence_field_still_blocked():
    """C3-T02: runtime_evidence_field.status=CANDIDATE → 422 (R2-01 차단 유지)."""
    conn = FakeConn(
        locked_row=locked(),
        field_rows=[_field_ev("f-c3t02", "attached_documents", input_type="file",
                              field_candidate_id="fc-c3t02")],
        evidence_field_rows=[{
            **_ev_row_approved("ev-c3t02", "efc-c3t02"),
            "status": "CANDIDATE",   # 승인 안 된 상태
        }],
        evidence_candidate_row=_efc_row_approved("efc-c3t02", "fc-c3t02"),
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False, "expected ConfirmError"
    except ConfirmError as e:
        assert e.http_status == 422
        assert "runtime_evidence_field.status" in e.detail
        assert "CANDIDATE" in e.detail
    assert conn.rolled_back


def test_C3_T03_approved_by_human_evidence_candidate_passes_r1():
    """C3-T03: evidence_field_candidate.status=APPROVED_BY_HUMAN → R1-02 통과 (C2-FINAL §2 D1)."""
    conn = FakeConn(
        locked_row=locked(runtime={"attached_documents": {
            "_type": "file_snapshot",
            "field_key": "attached_documents",
            "field_id": "f-c3t03",
            "storage_ref": f"storage://company-docs/attachments/document/{DOC_ID}/f-c3t03/ev.pdf",
            "sha256": "d" * 64,
            "mime_type": "application/pdf",
            "byte_size": 100,
        }}),
        field_rows=[_field_ev("f-c3t03", "attached_documents", input_type="file",
                              field_candidate_id="fc-c3t03")],
        evidence_field_rows=[_ev_row_approved("ev-c3t03", "efc-c3t03")],
        evidence_candidate_row={
            "id": "efc-c3t03",
            "field_candidate_id": "fc-c3t03",
            "status": "APPROVED_BY_HUMAN",   # D1 Migration 후 승인된 상태
            "schema_candidate_id": None,
        },
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="ok", current_user=user())
    except ConfirmError as e:
        assert "not approved" not in e.detail.lower(), (
            f"C3-T03: APPROVED_BY_HUMAN should pass R1-02, got: {e.detail}"
        )


def test_C3_T04_candidate_evidence_candidate_still_blocked():
    """C3-T04: evidence_field_candidate.status=CANDIDATE → 422 (R1-02 차단 유지)."""
    conn = FakeConn(
        locked_row=locked(),
        field_rows=[_field_ev("f-c3t04", "attached_documents", input_type="file",
                              field_candidate_id="fc-c3t04")],
        evidence_field_rows=[_ev_row_approved("ev-c3t04", "efc-c3t04")],
        evidence_candidate_row={
            "id": "efc-c3t04",
            "field_candidate_id": "fc-c3t04",
            "status": "CANDIDATE",   # 미승인 — evidence approval gate 차단
            "schema_candidate_id": None,
        },
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False, "expected ConfirmError"
    except ConfirmError as e:
        assert e.http_status == 422
        assert "not approved" in e.detail.lower()
        assert "CANDIDATE" in e.detail
    assert conn.rolled_back


def test_C3_T10_error_message_no_leg_gate():
    """C3-T10: 에러 메시지에 'LEG gate' 미포함 — C2-FINAL §4B 계약 (C3-04B)."""
    conn = FakeConn(
        locked_row=locked(),
        field_rows=[_field_ev("f-c3t10", "attached_documents", input_type="file",
                              field_candidate_id="fc-c3t10")],
        evidence_field_rows=[_ev_row_approved("ev-c3t10", "efc-c3t10")],
        evidence_candidate_row={
            "id": "efc-c3t10",
            "field_candidate_id": "fc-c3t10",
            "status": "CANDIDATE",   # 미승인 → 오류 메시지 유발
            "schema_candidate_id": None,
        },
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False, "expected ConfirmError"
    except ConfirmError as e:
        assert e.http_status == 422
        assert "LEG gate" not in e.detail, (
            f"C3-T10: 에러 메시지에 'LEG gate' 포함 금지 (C2-FINAL §4B). got: {e.detail!r}"
        )
        assert "evidence approval gate" in e.detail, (
            f"C3-T10: 에러 메시지에 'evidence approval gate' 포함 필요. got: {e.detail!r}"
        )
    assert conn.rolled_back


# ── REPORT_NUMBER evidence 테스트 (WO-DOC260-P0E-REPORT-NUMBER-001-R2) ──────────

def _ev_row_report_number(ev_id="ev-rn", efc_id="efc-rn"):
    """Helper: runtime_evidence_field row for REPORT_NUMBER family."""
    return {
        "id": ev_id,
        "form_schema_id": SCHEMA_ID,
        "evidence_candidate_id": efc_id,
        "evidence_type": "REPORT_NUMBER",
        "status": "APPROVED_BY_HUMAN",
        "evidence_family": "REPORT_NUMBER",
        "upload_type": "inspector_identity",
    }


def test_RN_T01_report_number_family_passes_r2_blocked_r1():
    """RN-T01: REPORT_NUMBER family는 R2-03(family check)를 통과하고 R1-02(승인 게이트)에서 차단."""
    conn = FakeConn(
        locked_row=locked(),
        field_rows=[_field_ev("f-rn", "registration_number", input_type="text", field_candidate_id="fc-rn")],
        evidence_field_rows=[_ev_row_report_number()],
        evidence_candidate_row={
            "id": "efc-rn",
            "field_candidate_id": "fc-rn",
            "status": "CANDIDATE",    # 미승인 → R1-02 차단
            "schema_candidate_id": None,
        },
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False, "expected ConfirmError"
    except ConfirmError as e:
        assert e.http_status == 422
        assert "evidence approval gate" in e.detail
    assert conn.rolled_back


def test_RN_T02_report_number_empty_string_blocks():
    """RN-T02: REPORT_NUMBER evidence 빈 문자열 → 422 (R1-03-D)."""
    conn = FakeConn(
        locked_row=locked(runtime={"registration_number": ""}),
        field_rows=[_field_ev("f-rn", "registration_number", input_type="text", field_candidate_id="fc-rn")],
        evidence_field_rows=[_ev_row_report_number()],
        evidence_candidate_row={
            "id": "efc-rn",
            "field_candidate_id": "fc-rn",
            "status": "APPROVED_BY_HUMAN",
            "schema_candidate_id": None,
        },
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "REPORT_NUMBER" in e.detail
        assert "registration_number" in e.detail
    assert conn.rolled_back


def test_RN_T03_report_number_non_string_blocks():
    """RN-T03: REPORT_NUMBER evidence 숫자값 → 422 (R1-03-D). 숫자·배열·객체 차단."""
    conn = FakeConn(
        locked_row=locked(runtime={"registration_number": 12345}),
        field_rows=[_field_ev("f-rn", "registration_number", input_type="text", field_candidate_id="fc-rn")],
        evidence_field_rows=[_ev_row_report_number()],
        evidence_candidate_row={
            "id": "efc-rn",
            "field_candidate_id": "fc-rn",
            "status": "APPROVED_BY_HUMAN",
            "schema_candidate_id": None,
        },
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "REPORT_NUMBER" in e.detail
        assert "str" in e.detail or "int" in e.detail
    assert conn.rolled_back


def test_RN_T04_report_number_wrong_upload_type_blocks():
    """RN-T04: REPORT_NUMBER + upload_type=attachment → 422 (R2-03 교차 조합 차단)."""
    conn = FakeConn(
        locked_row=locked(),
        field_rows=[_field_ev("f-rn", "registration_number", input_type="text", field_candidate_id="fc-rn")],
        evidence_field_rows=[{
            **_ev_row_report_number(),
            "upload_type": "attachment",
        }],
        evidence_candidate_row={
            "id": "efc-rn",
            "field_candidate_id": "fc-rn",
            "status": "APPROVED_BY_HUMAN",
            "schema_candidate_id": None,
        },
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "upload_type" in e.detail
        assert "attachment" in e.detail
    assert conn.rolled_back


def test_RN_T05_report_number_valid_string_confirm_succeeds():
    """RN-T05: REPORT_NUMBER 정상 문자열 + APPROVED_BY_HUMAN → Confirm 성공.

    R1-04 요건: 승인된 REPORT_NUMBER + 정상 문자열 → Confirm 및 Snapshot 성공.
    """
    conn = FakeConn(
        locked_row=locked(runtime={"registration_number": "ABC-12345-2026"}),
        field_rows=[_field_ev("f-rn", "registration_number", input_type="text", field_candidate_id="fc-rn")],
        evidence_field_rows=[_ev_row_report_number()],
        evidence_candidate_row={
            "id": "efc-rn",
            "field_candidate_id": "fc-rn",
            "status": "APPROVED_BY_HUMAN",
            "schema_candidate_id": None,
        },
    )
    _install(conn)
    out = confirm_document_atomic(DOC_ID, actor_id=None, comment="검토완료", current_user=user())
    assert conn.committed and not conn.rolled_back
    assert out["status"] == "APPROVED_BY_HUMAN"


# ---------------------------------------------------------------------------
# DATE family tests (DT-T01 ~ DT-T04)
# ---------------------------------------------------------------------------

def _ev_row_date(ev_id="ev-dt", efc_id="efc-dt"):
    """Helper: runtime_evidence_field row for DATE family."""
    return {
        "id": ev_id,
        "form_schema_id": SCHEMA_ID,
        "evidence_candidate_id": efc_id,
        "evidence_type": "DATE",
        "status": "APPROVED_BY_HUMAN",
        "evidence_family": "DATE",
        "upload_type": "timestamp_auto",
    }


def test_DT_T01_date_valid_confirm_succeeds():
    """DT-T01: DATE 정상 날짜 + APPROVED_BY_HUMAN → Confirm 성공, DATE Manifest 포함."""
    conn = FakeConn(
        locked_row=locked(runtime={"inspection_date": "2026-10-31"}),
        field_rows=[_field_ev("f-dt", "inspection_date", input_type="date", field_candidate_id="fc-dt")],
        evidence_field_rows=[_ev_row_date()],
        evidence_candidate_row={
            "id": "efc-dt",
            "field_candidate_id": "fc-dt",
            "status": "APPROVED_BY_HUMAN",
            "schema_candidate_id": None,
        },
    )
    _install(conn)
    captured: list = []

    def spy_render(*args, **kwargs):
        captured.append(kwargs.get("attachment_evidence_manifest", []))
        return {
            "rendered_body": "<html/>",
            "source_trace_snapshot": [],
            "template_identity": "tpl",
            "evidence_manifest": kwargs.get("attachment_evidence_manifest", []),
        }

    with (
        patch("services.document_confirm_svc.build_render_artifacts", side_effect=spy_render),
        patch("services.document_confirm_svc.compute_confirmed_snapshot_hash", return_value="a" * 64),
    ):
        out = confirm_document_atomic(DOC_ID, actor_id=None, comment="날짜확인", current_user=user())

    assert conn.committed and not conn.rolled_back
    assert out["status"] == "APPROVED_BY_HUMAN"
    assert len(captured) == 1
    date_entries = [m for m in captured[0] if m.get("evidence_family") == "DATE"]
    assert len(date_entries) == 1
    assert date_entries[0]["date_value"] == "2026-10-31"
    assert date_entries[0]["value_source"] == "USER_INPUT"
    assert date_entries[0]["input_type"] == "date"


def test_DT_T02_date_invalid_calendar_blocks():
    """DT-T02: DATE 2026-02-30 (달력에 없는 날) → 422."""
    conn = FakeConn(
        locked_row=locked(runtime={"inspection_date": "2026-02-30"}),
        field_rows=[_field_ev("f-dt", "inspection_date", input_type="date", field_candidate_id="fc-dt")],
        evidence_field_rows=[_ev_row_date()],
        evidence_candidate_row={
            "id": "efc-dt",
            "field_candidate_id": "fc-dt",
            "status": "APPROVED_BY_HUMAN",
            "schema_candidate_id": None,
        },
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "DATE" in e.detail or "date" in e.detail.lower()
    assert conn.rolled_back


def test_DT_T03_date_wrong_format_blocks():
    """DT-T03: DATE "20261031" (대시 없는 포맷) → 422."""
    conn = FakeConn(
        locked_row=locked(runtime={"inspection_date": "20261031"}),
        field_rows=[_field_ev("f-dt", "inspection_date", input_type="date", field_candidate_id="fc-dt")],
        evidence_field_rows=[_ev_row_date()],
        evidence_candidate_row={
            "id": "efc-dt",
            "field_candidate_id": "fc-dt",
            "status": "APPROVED_BY_HUMAN",
            "schema_candidate_id": None,
        },
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "DATE" in e.detail or "date" in e.detail.lower()
    assert conn.rolled_back


def test_DT_T04_date_empty_string_blocks():
    """DT-T04: DATE 빈 문자열 → 422."""
    conn = FakeConn(
        locked_row=locked(runtime={"inspection_date": ""}),
        field_rows=[_field_ev("f-dt", "inspection_date", input_type="date", field_candidate_id="fc-dt")],
        evidence_field_rows=[_ev_row_date()],
        evidence_candidate_row={
            "id": "efc-dt",
            "field_candidate_id": "fc-dt",
            "status": "APPROVED_BY_HUMAN",
            "schema_candidate_id": None,
        },
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "DATE" in e.detail or "date" in e.detail.lower()
    assert conn.rolled_back


# ---------------------------------------------------------------------------
# MEASUREMENT family tests (MT-T01 ~ MT-T07)
# ---------------------------------------------------------------------------

def _ev_row_measurement(ev_id="ev-mt", efc_id="efc-mt"):
    """Helper: runtime_evidence_field row for MEASUREMENT family."""
    return {
        "id": ev_id,
        "form_schema_id": SCHEMA_ID,
        "evidence_candidate_id": efc_id,
        "evidence_type": "MEASUREMENT",
        "status": "APPROVED_BY_HUMAN",
        "evidence_family": "MEASUREMENT",
        "upload_type": "measurement_input",
    }


def test_MT_T01_measurement_valid_string_confirm_succeeds():
    """MT-T01: MEASUREMENT measurement 정상 문자열 → Confirm 성공, Manifest 포함."""
    conn = FakeConn(
        locked_row=locked(runtime={"oxygen_level": "21.0"}),
        field_rows=[_field_ev("f-mt", "oxygen_level", input_type="measurement", field_candidate_id="fc-mt")],
        evidence_field_rows=[_ev_row_measurement()],
        evidence_candidate_row={
            "id": "efc-mt",
            "field_candidate_id": "fc-mt",
            "status": "APPROVED_BY_HUMAN",
            "schema_candidate_id": None,
        },
    )
    _install(conn)
    captured: list = []

    def spy_render(*args, **kwargs):
        captured.append(kwargs.get("attachment_evidence_manifest", []))
        return {
            "rendered_body": "<html/>",
            "source_trace_snapshot": [],
            "template_identity": "tpl",
            "evidence_manifest": kwargs.get("attachment_evidence_manifest", []),
        }

    with (
        patch("services.document_confirm_svc.build_render_artifacts", side_effect=spy_render),
        patch("services.document_confirm_svc.compute_confirmed_snapshot_hash", return_value="a" * 64),
    ):
        out = confirm_document_atomic(DOC_ID, actor_id=None, comment="측정완료", current_user=user())

    assert conn.committed and not conn.rolled_back
    assert out["status"] == "APPROVED_BY_HUMAN"
    assert len(captured) == 1
    mt_entries = [m for m in captured[0] if m.get("evidence_family") == "MEASUREMENT"]
    assert len(mt_entries) == 1
    assert mt_entries[0]["text_value"] == "21.0"
    assert mt_entries[0]["input_type"] == "measurement"
    assert mt_entries[0]["value_source"] == "USER_INPUT"
    assert mt_entries[0]["value_semantic_class"] == "MEASUREMENT"


def test_MT_T02_measurement_date_subtype_valid_confirm_succeeds():
    """MT-T02: MEASUREMENT date 서브타입 정상 날짜 → Confirm 성공, Manifest 포함."""
    conn = FakeConn(
        locked_row=locked(runtime={"measurement_datetime": "2026-10-31"}),
        field_rows=[_field_ev("f-mt", "measurement_datetime", input_type="date", field_candidate_id="fc-mt")],
        evidence_field_rows=[_ev_row_measurement()],
        evidence_candidate_row={
            "id": "efc-mt",
            "field_candidate_id": "fc-mt",
            "status": "APPROVED_BY_HUMAN",
            "schema_candidate_id": None,
        },
    )
    _install(conn)
    captured: list = []

    def spy_render(*args, **kwargs):
        captured.append(kwargs.get("attachment_evidence_manifest", []))
        return {
            "rendered_body": "<html/>",
            "source_trace_snapshot": [],
            "template_identity": "tpl",
            "evidence_manifest": kwargs.get("attachment_evidence_manifest", []),
        }

    with (
        patch("services.document_confirm_svc.build_render_artifacts", side_effect=spy_render),
        patch("services.document_confirm_svc.compute_confirmed_snapshot_hash", return_value="a" * 64),
    ):
        out = confirm_document_atomic(DOC_ID, actor_id=None, comment="측정완료", current_user=user())

    assert conn.committed and not conn.rolled_back
    assert out["status"] == "APPROVED_BY_HUMAN"
    assert len(captured) == 1
    mt_entries = [m for m in captured[0] if m.get("evidence_family") == "MEASUREMENT"]
    assert len(mt_entries) == 1
    assert mt_entries[0]["date_value"] == "2026-10-31"
    assert mt_entries[0]["input_type"] == "date"
    assert mt_entries[0]["value_semantic_class"] == "PENDING_CLASSIFICATION"


def test_MT_T03_measurement_candidate_status_blocks():
    """MT-T03: MEASUREMENT CANDIDATE → 422 evidence approval gate."""
    conn = FakeConn(
        locked_row=locked(runtime={"oxygen_level": "21.0"}),
        field_rows=[_field_ev("f-mt", "oxygen_level", input_type="measurement", field_candidate_id="fc-mt")],
        evidence_field_rows=[_ev_row_measurement()],
        evidence_candidate_row={
            "id": "efc-mt",
            "field_candidate_id": "fc-mt",
            "status": "CANDIDATE",
            "schema_candidate_id": None,
        },
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "evidence approval gate" in e.detail
    assert conn.rolled_back


def test_MT_T04_measurement_empty_string_blocks():
    """MT-T04: MEASUREMENT 빈 문자열 → 422."""
    conn = FakeConn(
        locked_row=locked(runtime={"oxygen_level": ""}),
        field_rows=[_field_ev("f-mt", "oxygen_level", input_type="measurement", field_candidate_id="fc-mt")],
        evidence_field_rows=[_ev_row_measurement()],
        evidence_candidate_row={
            "id": "efc-mt",
            "field_candidate_id": "fc-mt",
            "status": "APPROVED_BY_HUMAN",
            "schema_candidate_id": None,
        },
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "MEASUREMENT" in e.detail
    assert conn.rolled_back


def test_MT_T05_measurement_non_string_blocks():
    """MT-T05: MEASUREMENT 숫자 타입 → 422 (문자열 강제 아님)."""
    conn = FakeConn(
        locked_row=locked(runtime={"oxygen_level": 21.0}),
        field_rows=[_field_ev("f-mt", "oxygen_level", input_type="measurement", field_candidate_id="fc-mt")],
        evidence_field_rows=[_ev_row_measurement()],
        evidence_candidate_row={
            "id": "efc-mt",
            "field_candidate_id": "fc-mt",
            "status": "APPROVED_BY_HUMAN",
            "schema_candidate_id": None,
        },
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "MEASUREMENT" in e.detail
    assert conn.rolled_back


def test_MT_T06_measurement_wrong_upload_type_blocks():
    """MT-T06: MEASUREMENT + upload_type=attachment → 422 (교차 조합 차단)."""
    conn = FakeConn(
        locked_row=locked(),
        field_rows=[_field_ev("f-mt", "oxygen_level", input_type="measurement", field_candidate_id="fc-mt")],
        evidence_field_rows=[{
            **_ev_row_measurement(),
            "upload_type": "attachment",
        }],
        evidence_candidate_row={
            "id": "efc-mt",
            "field_candidate_id": "fc-mt",
            "status": "APPROVED_BY_HUMAN",
            "schema_candidate_id": None,
        },
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "upload_type" in e.detail
        assert "attachment" in e.detail
    assert conn.rolled_back


def test_MT_T07_measurement_date_invalid_calendar_blocks():
    """MT-T07: MEASUREMENT date 서브타입 + 달력에 없는 날짜 → 422."""
    conn = FakeConn(
        locked_row=locked(runtime={"measurement_datetime": "2026-02-30"}),
        field_rows=[_field_ev("f-mt", "measurement_datetime", input_type="date", field_candidate_id="fc-mt")],
        evidence_field_rows=[_ev_row_measurement()],
        evidence_candidate_row={
            "id": "efc-mt",
            "field_candidate_id": "fc-mt",
            "status": "APPROVED_BY_HUMAN",
            "schema_candidate_id": None,
        },
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "date" in e.detail.lower() or "DATE" in e.detail
    assert conn.rolled_back

# MEASUREMENT R1 — required_status 계약 보정 (MT-T08 ~ MT-T11)
# ---------------------------------------------------------------------------

def test_MT_T08_not_required_measurement_empty_skips_manifest():
    """MT-T08: NOT_REQUIRED MEASUREMENT 빈 값 → Confirm 성공, Manifest 미포함."""
    conn = FakeConn(
        locked_row=locked(runtime={"evacuation_time": None}),
        field_rows=[_field_ev("f-mt", "evacuation_time", input_type="measurement",
                              field_candidate_id="fc-mt", required_status="NOT_REQUIRED")],
        evidence_field_rows=[_ev_row_measurement()],
        evidence_candidate_row={
            "id": "efc-mt",
            "field_candidate_id": "fc-mt",
            "status": "APPROVED_BY_HUMAN",
            "schema_candidate_id": None,
        },
    )
    _install(conn)
    captured: list = []

    def spy_render(*args, **kwargs):
        captured.append(kwargs.get("attachment_evidence_manifest", []))
        return {
            "rendered_body": "<html/>",
            "source_trace_snapshot": [],
            "template_identity": "tpl",
            "evidence_manifest": kwargs.get("attachment_evidence_manifest", []),
        }

    with (
        patch("services.document_confirm_svc.build_render_artifacts", side_effect=spy_render),
        patch("services.document_confirm_svc.compute_confirmed_snapshot_hash", return_value="a" * 64),
    ):
        out = confirm_document_atomic(DOC_ID, actor_id=None, comment="측정완료", current_user=user())

    assert conn.committed and not conn.rolled_back
    assert out["status"] == "APPROVED_BY_HUMAN"
    assert len(captured) == 1
    mt_entries = [m for m in captured[0] if m.get("evidence_family") == "MEASUREMENT"]
    assert len(mt_entries) == 0


def test_MT_T09_not_required_measurement_valid_value_in_manifest():
    """MT-T09: NOT_REQUIRED MEASUREMENT 유효한 값 → Confirm 성공, Manifest 포함."""
    conn = FakeConn(
        locked_row=locked(runtime={"measurer": "홍길동"}),
        field_rows=[_field_ev("f-mt", "measurer", input_type="measurement",
                              field_candidate_id="fc-mt", required_status="NOT_REQUIRED")],
        evidence_field_rows=[_ev_row_measurement()],
        evidence_candidate_row={
            "id": "efc-mt",
            "field_candidate_id": "fc-mt",
            "status": "APPROVED_BY_HUMAN",
            "schema_candidate_id": None,
        },
    )
    _install(conn)
    captured: list = []

    def spy_render(*args, **kwargs):
        captured.append(kwargs.get("attachment_evidence_manifest", []))
        return {
            "rendered_body": "<html/>",
            "source_trace_snapshot": [],
            "template_identity": "tpl",
            "evidence_manifest": kwargs.get("attachment_evidence_manifest", []),
        }

    with (
        patch("services.document_confirm_svc.build_render_artifacts", side_effect=spy_render),
        patch("services.document_confirm_svc.compute_confirmed_snapshot_hash", return_value="a" * 64),
    ):
        out = confirm_document_atomic(DOC_ID, actor_id=None, comment="측정완료", current_user=user())

    assert conn.committed and not conn.rolled_back
    assert out["status"] == "APPROVED_BY_HUMAN"
    assert len(captured) == 1
    mt_entries = [m for m in captured[0] if m.get("evidence_family") == "MEASUREMENT"]
    assert len(mt_entries) == 1
    assert mt_entries[0]["text_value"] == "홍길동"
    assert mt_entries[0]["input_type"] == "measurement"
    assert mt_entries[0]["value_semantic_class"] == "MEASUREMENT"


def test_MT_T10_required_from_source_measurement_empty_blocks():
    """MT-T10: REQUIRED_FROM_SOURCE MEASUREMENT 빈 값 → 422."""
    conn = FakeConn(
        locked_row=locked(runtime={"oxygen_level": None}),
        field_rows=[_field_ev("f-mt", "oxygen_level", input_type="measurement",
                              field_candidate_id="fc-mt", required_status="REQUIRED_FROM_SOURCE")],
        evidence_field_rows=[_ev_row_measurement()],
        evidence_candidate_row={
            "id": "efc-mt",
            "field_candidate_id": "fc-mt",
            "status": "APPROVED_BY_HUMAN",
            "schema_candidate_id": None,
        },
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "MEASUREMENT" in e.detail
    assert conn.rolled_back


def test_MT_T11_not_required_measurement_candidate_still_blocks():
    """MT-T11: NOT_REQUIRED MEASUREMENT + CANDIDATE evidence → 422 (evidence approval gate 유지)."""
    conn = FakeConn(
        locked_row=locked(runtime={"evacuation_time": None}),
        field_rows=[_field_ev("f-mt", "evacuation_time", input_type="measurement",
                              field_candidate_id="fc-mt", required_status="NOT_REQUIRED")],
        evidence_field_rows=[_ev_row_measurement()],
        evidence_candidate_row={
            "id": "efc-mt",
            "field_candidate_id": "fc-mt",
            "status": "CANDIDATE",
            "schema_candidate_id": None,
        },
    )
    _install(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "evidence approval gate" in e.detail
    assert conn.rolled_back

# PHOTO family tests (PT-T01 ~ PT-T06)
# ---------------------------------------------------------------------------

_PHOTO_FIELD_ID  = "f-pt"
_PHOTO_STORAGE   = "storage://company-docs/attachments/document/%s/%s/abc123.jpg" % (DOC_ID, _PHOTO_FIELD_ID)

def _ev_row_photo(ev_id="ev-pt", efc_id="efc-pt"):
    """Helper: runtime_evidence_field row for PHOTO family."""
    return {
        "id": ev_id,
        "form_schema_id": SCHEMA_ID,
        "evidence_candidate_id": efc_id,
        "evidence_type": "PHOTO",
        "status": "APPROVED_BY_HUMAN",
        "evidence_family": "PHOTO",
        "upload_type": "image_upload",
    }


def _photo_snap(field_key="photos", field_id=_PHOTO_FIELD_ID, mime="image/jpeg"):
    """Helper: minimal valid FileSnapshot for a photo field."""
    return {
        "_type": "file_snapshot",
        "version": 1,
        "field_id": field_id,
        "field_key": field_key,
        "storage_ref": _PHOTO_STORAGE,
        "sha256": "a" * 64,
        "mime_type": mime,
        "byte_size": 1024,
        "original_file_name": "photo.jpg",
        "uploaded_by_user_id": "user-1",
        "uploaded_at": "2026-10-31T00:00:00Z",
    }


def test_PT_T01_not_required_photo_no_image_confirm_succeeds():
    """PT-T01: NOT_REQUIRED PHOTO 이미지 없음 → Confirm 성공, PHOTO Manifest 미포함."""
    conn = FakeConn(
        locked_row=locked(runtime={"photos": None}),
        field_rows=[_field_ev("f-pt", "photos", input_type="image",
                              field_candidate_id="fc-pt", required_status="NOT_REQUIRED")],
        evidence_field_rows=[_ev_row_photo()],
        evidence_candidate_row={
            "id": "efc-pt", "field_candidate_id": "fc-pt",
            "status": "APPROVED_BY_HUMAN", "schema_candidate_id": None,
        },
    )
    _install(conn)
    captured: list = []

    def spy_render(*args, **kwargs):
        captured.append(kwargs.get("attachment_evidence_manifest", []))
        return {"rendered_body": "<html/>", "source_trace_snapshot": [], "template_identity": "tpl",
                "evidence_manifest": []}

    with (
        patch("services.document_confirm_svc.build_render_artifacts", side_effect=spy_render),
        patch("services.document_confirm_svc.compute_confirmed_snapshot_hash", return_value="a" * 64),
        patch("services.document_confirm_svc.resolve_attachment_images_for_render", return_value={}),
    ):
        out = confirm_document_atomic(DOC_ID, actor_id=None, comment="공사일지", current_user=user())

    assert conn.committed and not conn.rolled_back
    assert out["status"] == "APPROVED_BY_HUMAN"
    assert len(captured) == 1
    photo_entries = [m for m in captured[0] if m.get("evidence_family") == "PHOTO"]
    assert len(photo_entries) == 0


def test_PT_T02_valid_photo_creates_manifest():
    """PT-T02: 정상 사진 + resolver 결과 포함 → Manifest 생성."""
    snap = _photo_snap()
    conn = FakeConn(
        locked_row=locked(runtime={"photos": snap}),
        field_rows=[_field_ev("f-pt", "photos", input_type="image",
                              field_candidate_id="fc-pt", required_status="NOT_REQUIRED")],
        evidence_field_rows=[_ev_row_photo()],
        evidence_candidate_row={
            "id": "efc-pt", "field_candidate_id": "fc-pt",
            "status": "APPROVED_BY_HUMAN", "schema_candidate_id": None,
        },
    )
    _install(conn)
    captured: list = []

    def spy_render(*args, **kwargs):
        captured.append(kwargs.get("attachment_evidence_manifest", []))
        return {"rendered_body": "<html/>", "source_trace_snapshot": [], "template_identity": "tpl",
                "evidence_manifest": []}

    with (
        patch("services.document_confirm_svc.build_render_artifacts", side_effect=spy_render),
        patch("services.document_confirm_svc.compute_confirmed_snapshot_hash", return_value="a" * 64),
        patch("services.document_confirm_svc.resolve_attachment_images_for_render",
              return_value={"photos": "data:image/jpeg;base64,/9j/"}),
    ):
        out = confirm_document_atomic(DOC_ID, actor_id=None, comment="공사일지", current_user=user())

    assert conn.committed and not conn.rolled_back
    assert len(captured) == 1
    photo_entries = [m for m in captured[0] if m.get("evidence_family") == "PHOTO"]
    assert len(photo_entries) == 1
    assert photo_entries[0]["input_type"] == "image"
    assert photo_entries[0]["mime_type"] == "image/jpeg"
    assert photo_entries[0]["sha256"] == "a" * 64
    assert photo_entries[0]["value_semantic_class"] == "PHOTO"


def test_PT_T03_snapshot_not_in_resolver_result_blocks():
    """PT-T03: Snapshot 존재하나 step 14a-1 결과에 field_key 없음 → 422."""
    snap = _photo_snap()
    conn = FakeConn(
        locked_row=locked(runtime={"photos": snap}),
        field_rows=[_field_ev("f-pt", "photos", input_type="image",
                              field_candidate_id="fc-pt", required_status="NOT_REQUIRED")],
        evidence_field_rows=[_ev_row_photo()],
        evidence_candidate_row={
            "id": "efc-pt", "field_candidate_id": "fc-pt",
            "status": "APPROVED_BY_HUMAN", "schema_candidate_id": None,
        },
    )
    _install(conn)
    try:
        with patch("services.document_confirm_svc.resolve_attachment_images_for_render",
                   return_value={}):  # field_key 없음
            confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "not verified by image resolver" in e.detail
    assert conn.rolled_back


def test_PT_T04_photo_wrong_mime_blocks():
    """PT-T04: MIME=application/pdf (비이미지) → 422."""
    snap = _photo_snap(mime="application/pdf")
    conn = FakeConn(
        locked_row=locked(runtime={"photos": snap}),
        field_rows=[_field_ev("f-pt", "photos", input_type="image",
                              field_candidate_id="fc-pt", required_status="NOT_REQUIRED")],
        evidence_field_rows=[_ev_row_photo()],
        evidence_candidate_row={
            "id": "efc-pt", "field_candidate_id": "fc-pt",
            "status": "APPROVED_BY_HUMAN", "schema_candidate_id": None,
        },
    )
    _install(conn)
    try:
        with patch("services.document_confirm_svc.resolve_attachment_images_for_render",
                   return_value={"photos": "data:image/jpeg;base64,/9j/"}):
            confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "image allowlist" in e.detail
    assert conn.rolled_back


def test_PT_T05_photo_candidate_evidence_blocks():
    """PT-T05: PHOTO + CANDIDATE evidence → 422 (evidence approval gate 유지)."""
    snap = _photo_snap()
    conn = FakeConn(
        locked_row=locked(runtime={"photos": snap}),
        field_rows=[_field_ev("f-pt", "photos", input_type="image",
                              field_candidate_id="fc-pt", required_status="NOT_REQUIRED")],
        evidence_field_rows=[_ev_row_photo()],
        evidence_candidate_row={
            "id": "efc-pt", "field_candidate_id": "fc-pt",
            "status": "CANDIDATE", "schema_candidate_id": None,
        },
    )
    _install(conn)
    try:
        with patch("services.document_confirm_svc.resolve_attachment_images_for_render",
                   return_value={"photos": "data:image/jpeg;base64,/9j/"}):
            confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "evidence approval gate" in e.detail
    assert conn.rolled_back


def test_PT_T06_photo_wrong_upload_type_blocks():
    """PT-T06: PHOTO + upload_type=attachment → 422 (교차 조합 차단)."""
    conn = FakeConn(
        locked_row=locked(runtime={}),
        field_rows=[_field_ev("f-pt", "photos", input_type="image",
                              field_candidate_id="fc-pt", required_status="NOT_REQUIRED")],
        evidence_field_rows=[{
            **_ev_row_photo(),
            "upload_type": "attachment",
        }],
        evidence_candidate_row={
            "id": "efc-pt", "field_candidate_id": "fc-pt",
            "status": "APPROVED_BY_HUMAN", "schema_candidate_id": None,
        },
    )
    _install(conn)
    try:
        with patch("services.document_confirm_svc.resolve_attachment_images_for_render",
                   return_value={}):
            confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "upload_type" in e.detail
        assert "attachment" in e.detail
    assert conn.rolled_back


# ---------------------------------------------------------------------------
# SIGNATURE family tests (SG-T01 ~ SG-T07)
# ---------------------------------------------------------------------------

_SIG_FIELD_ID  = "f-sg"
_SIG_STORAGE   = "storage://company-docs/signatures/document/%s/%s/sig.png" % (DOC_ID, _SIG_FIELD_ID)

def _ev_row_signature(ev_id="ev-sg", efc_id="efc-sg"):
    """Helper: runtime_evidence_field row for SIGNATURE family."""
    return {
        "id": ev_id,
        "form_schema_id": SCHEMA_ID,
        "evidence_candidate_id": efc_id,
        "evidence_type": "SIGNATURE",
        "status": "APPROVED_BY_HUMAN",
        "evidence_family": "SIGNATURE",
        "upload_type": "signature",
    }


def _signature_snap(field_key="inspector_signature", field_id=_SIG_FIELD_ID):
    """Helper: minimal valid signature_snapshot for a signature field."""
    return {
        "_type": "signature_snapshot",
        "version": 1,
        "field_id": field_id,
        "field_key": field_key,
        "storage_ref": _SIG_STORAGE,
        "sha256": "b" * 64,
        "mime_type": "image/png",
        "byte_size": 2048,
        "signer_user_id": "user-1",
        "signed_at": "2026-10-31T09:00:00Z",
        "source": "signature_pad",
    }


def test_SG_T01_not_required_signature_no_snap_confirm_succeeds():
    """SG-T01: NOT_REQUIRED SIGNATURE 서명 없음 → Confirm 성공, SIGNATURE Manifest 미포함."""
    conn = FakeConn(
        locked_row=locked(runtime={"inspector_signature": None}),
        field_rows=[_field_ev(_SIG_FIELD_ID, "inspector_signature", input_type="signature",
                              field_candidate_id="fc-sg", required_status="NOT_REQUIRED")],
        evidence_field_rows=[_ev_row_signature()],
        evidence_candidate_row={
            "id": "efc-sg", "field_candidate_id": "fc-sg",
            "status": "APPROVED_BY_HUMAN", "schema_candidate_id": None,
        },
    )
    _install(conn)
    captured: list = []

    def spy_render(*args, **kwargs):
        captured.append(kwargs.get("attachment_evidence_manifest", []))
        return {"rendered_body": "<html/>", "source_trace_snapshot": [], "template_identity": "tpl",
                "evidence_manifest": []}

    with (
        patch("services.document_confirm_svc.build_render_artifacts", side_effect=spy_render),
        patch("services.document_confirm_svc.compute_confirmed_snapshot_hash", return_value="a" * 64),
        patch("services.document_confirm_svc.resolve_attachment_images_for_render", return_value={}),
        patch("services.document_confirm_svc.resolve_signature_images_for_render",
              return_value={"images": {}, "manifest": []}),
    ):
        out = confirm_document_atomic(DOC_ID, actor_id=None, comment="서명서", current_user=user())

    assert conn.committed and not conn.rolled_back
    assert out["status"] == "APPROVED_BY_HUMAN"
    assert len(captured) == 1
    sig_entries = [m for m in captured[0] if m.get("evidence_family") == "SIGNATURE"]
    assert len(sig_entries) == 0


def test_SG_T02_valid_signature_creates_manifest():
    """SG-T02: 정상 서명 + resolver 결과 포함 → Manifest 생성, signer_user_id/signed_at 포함."""
    snap = _signature_snap()
    conn = FakeConn(
        locked_row=locked(runtime={"inspector_signature": snap}),
        field_rows=[_field_ev(_SIG_FIELD_ID, "inspector_signature", input_type="signature",
                              field_candidate_id="fc-sg", required_status="NOT_REQUIRED")],
        evidence_field_rows=[_ev_row_signature()],
        evidence_candidate_row={
            "id": "efc-sg", "field_candidate_id": "fc-sg",
            "status": "APPROVED_BY_HUMAN", "schema_candidate_id": None,
        },
    )
    _install(conn)
    captured: list = []

    def spy_render(*args, **kwargs):
        captured.append(kwargs.get("attachment_evidence_manifest", []))
        return {"rendered_body": "<html/>", "source_trace_snapshot": [], "template_identity": "tpl",
                "evidence_manifest": []}

    with (
        patch("services.document_confirm_svc.build_render_artifacts", side_effect=spy_render),
        patch("services.document_confirm_svc.compute_confirmed_snapshot_hash", return_value="a" * 64),
        patch("services.document_confirm_svc.resolve_attachment_images_for_render", return_value={}),
        patch("services.document_confirm_svc.resolve_signature_images_for_render",
              return_value={"images": {"inspector_signature": "data:image/png;base64,iVBOR"}, "manifest": []}),
    ):
        out = confirm_document_atomic(DOC_ID, actor_id=None, comment="서명서", current_user=user())

    assert conn.committed and not conn.rolled_back
    assert len(captured) == 1
    sig_entries = [m for m in captured[0] if m.get("evidence_family") == "SIGNATURE"]
    assert len(sig_entries) == 1
    e = sig_entries[0]
    assert e["input_type"] == "signature"
    assert e["mime_type"] == "image/png"
    assert e["sha256"] == "b" * 64
    assert e["value_semantic_class"] == "SIGNATURE"
    assert e["signer_user_id"] == "user-1"
    assert e["signed_at"] == "2026-10-31T09:00:00Z"


def test_SG_T03_snapshot_not_in_resolver_result_blocks():
    """SG-T03: Snapshot 존재하나 step 14a 결과에 field_key 없음 → 422."""
    snap = _signature_snap()
    conn = FakeConn(
        locked_row=locked(runtime={"inspector_signature": snap}),
        field_rows=[_field_ev(_SIG_FIELD_ID, "inspector_signature", input_type="signature",
                              field_candidate_id="fc-sg", required_status="NOT_REQUIRED")],
        evidence_field_rows=[_ev_row_signature()],
        evidence_candidate_row={
            "id": "efc-sg", "field_candidate_id": "fc-sg",
            "status": "APPROVED_BY_HUMAN", "schema_candidate_id": None,
        },
    )
    _install(conn)
    try:
        with (
            patch("services.document_confirm_svc.resolve_attachment_images_for_render", return_value={}),
            patch("services.document_confirm_svc.resolve_signature_images_for_render",
                  return_value={"images": {}, "manifest": []}),  # field_key 없음
        ):
            confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "not verified by signature resolver" in e.detail
    assert conn.rolled_back


def test_SG_T04_malformed_snapshot_type_blocks():
    """SG-T04: snapshot._type != 'signature_snapshot' → 422 (형식 오류)."""
    bad_snap = {**_signature_snap(), "_type": "file_snapshot"}
    conn = FakeConn(
        locked_row=locked(runtime={"inspector_signature": bad_snap}),
        field_rows=[_field_ev(_SIG_FIELD_ID, "inspector_signature", input_type="signature",
                              field_candidate_id="fc-sg", required_status="NOT_REQUIRED")],
        evidence_field_rows=[_ev_row_signature()],
        evidence_candidate_row={
            "id": "efc-sg", "field_candidate_id": "fc-sg",
            "status": "APPROVED_BY_HUMAN", "schema_candidate_id": None,
        },
    )
    _install(conn)
    try:
        with (
            patch("services.document_confirm_svc.resolve_attachment_images_for_render", return_value={}),
            patch("services.document_confirm_svc.resolve_signature_images_for_render",
                  return_value={"images": {"inspector_signature": "data:image/png;base64,iVBOR"}, "manifest": []}),
        ):
            confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "SIGNATURE snapshot malformed" in e.detail
    assert conn.rolled_back


def test_SG_T05_candidate_evidence_blocks():
    """SG-T05: SIGNATURE + CANDIDATE evidence → 422 (evidence approval gate 유지)."""
    snap = _signature_snap()
    conn = FakeConn(
        locked_row=locked(runtime={"inspector_signature": snap}),
        field_rows=[_field_ev(_SIG_FIELD_ID, "inspector_signature", input_type="signature",
                              field_candidate_id="fc-sg", required_status="NOT_REQUIRED")],
        evidence_field_rows=[_ev_row_signature()],
        evidence_candidate_row={
            "id": "efc-sg", "field_candidate_id": "fc-sg",
            "status": "CANDIDATE", "schema_candidate_id": None,
        },
    )
    _install(conn)
    try:
        with (
            patch("services.document_confirm_svc.resolve_attachment_images_for_render", return_value={}),
            patch("services.document_confirm_svc.resolve_signature_images_for_render",
                  return_value={"images": {"inspector_signature": "data:image/png;base64,iVBOR"}, "manifest": []}),
        ):
            confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "evidence approval gate" in e.detail
    assert conn.rolled_back


def test_SG_T06_wrong_upload_type_blocks():
    """SG-T06: SIGNATURE + upload_type=attachment → 422 (교차 조합 차단)."""
    conn = FakeConn(
        locked_row=locked(runtime={}),
        field_rows=[_field_ev(_SIG_FIELD_ID, "inspector_signature", input_type="signature",
                              field_candidate_id="fc-sg", required_status="NOT_REQUIRED")],
        evidence_field_rows=[{
            **_ev_row_signature(),
            "upload_type": "attachment",
        }],
        evidence_candidate_row={
            "id": "efc-sg", "field_candidate_id": "fc-sg",
            "status": "APPROVED_BY_HUMAN", "schema_candidate_id": None,
        },
    )
    _install(conn)
    try:
        with (
            patch("services.document_confirm_svc.resolve_attachment_images_for_render", return_value={}),
            patch("services.document_confirm_svc.resolve_signature_images_for_render",
                  return_value={"images": {}, "manifest": []}),
        ):
            confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "upload_type" in e.detail
        assert "attachment" in e.detail
    assert conn.rolled_back


def test_SG_T07_wrong_input_type_blocks():
    """SG-T07: SIGNATURE evidence + input_type=image (불일치) → 422."""
    conn = FakeConn(
        locked_row=locked(runtime={}),
        field_rows=[_field_ev(_SIG_FIELD_ID, "inspector_signature", input_type="image",
                              field_candidate_id="fc-sg", required_status="NOT_REQUIRED")],
        evidence_field_rows=[_ev_row_signature()],
        evidence_candidate_row={
            "id": "efc-sg", "field_candidate_id": "fc-sg",
            "status": "APPROVED_BY_HUMAN", "schema_candidate_id": None,
        },
    )
    _install(conn)
    try:
        with (
            patch("services.document_confirm_svc.resolve_attachment_images_for_render", return_value={}),
            patch("services.document_confirm_svc.resolve_signature_images_for_render",
                  return_value={"images": {}, "manifest": []}),
        ):
            confirm_document_atomic(DOC_ID, actor_id=None, comment="x", current_user=user())
        assert False
    except ConfirmError as e:
        assert e.http_status == 422
        assert "SIGNATURE family" in e.detail
    assert conn.rolled_back


def test_SG_T08_sig_manifest_dedup_filters_evidence_covered_fields():
    """SG-T08 (R1): sig_result["manifest"]에 field_key가 있고 SIGNATURE evidence도 있을 때
    build_render_artifacts에 전달되는 signature_manifest에서 해당 field_key가 제거된다.
    이중 기록 방지 검증."""
    snap = _signature_snap()
    conn = FakeConn(
        locked_row=locked(runtime={"inspector_signature": snap}),
        field_rows=[_field_ev(_SIG_FIELD_ID, "inspector_signature", input_type="signature",
                              field_candidate_id="fc-sg", required_status="NOT_REQUIRED")],
        evidence_field_rows=[_ev_row_signature()],
        evidence_candidate_row={
            "id": "efc-sg", "field_candidate_id": "fc-sg",
            "status": "APPROVED_BY_HUMAN", "schema_candidate_id": None,
        },
    )
    _install(conn)
    captured_render_kwargs: list = []

    def spy_render(*args, **kwargs):
        captured_render_kwargs.append(kwargs)
        return {"rendered_body": "<html/>", "source_trace_snapshot": [], "template_identity": "tpl",
                "evidence_manifest": []}

    # sig_result["manifest"]에 inspector_signature가 이미 들어있는 경우를 시뮬레이션
    fake_sig_manifest_entry = {
        "type": "signature", "field_id": _SIG_FIELD_ID,
        "field_key": "inspector_signature", "storage_ref": _SIG_STORAGE,
        "sha256": "b" * 64, "mime_type": "image/png", "byte_size": 2048,
        "signer_user_id": "user-1", "signed_at": "2026-10-31T09:00:00Z", "source": "signature_pad",
    }

    with (
        patch("services.document_confirm_svc.build_render_artifacts", side_effect=spy_render),
        patch("services.document_confirm_svc.compute_confirmed_snapshot_hash", return_value="a" * 64),
        patch("services.document_confirm_svc.resolve_attachment_images_for_render", return_value={}),
        patch("services.document_confirm_svc.resolve_signature_images_for_render",
              return_value={"images": {"inspector_signature": "data:image/png;base64,iVBOR"},
                            "manifest": [fake_sig_manifest_entry]}),
    ):
        out = confirm_document_atomic(DOC_ID, actor_id=None, comment="서명서", current_user=user())

    assert conn.committed and not conn.rolled_back
    assert len(captured_render_kwargs) == 1
    kw = captured_render_kwargs[0]

    # signature_manifest에서 inspector_signature 제거됐어야 함 (이중 기록 방지)
    sig_manifest_passed = kw.get("signature_manifest", [])
    assert all(e.get("field_key") != "inspector_signature" for e in sig_manifest_passed), \
        "inspector_signature가 signature_manifest에 남아 이중 기록 발생"

    # combined_evidence_manifest에는 SIGNATURE evidence entry가 있어야 함
    ev_manifest_passed = kw.get("attachment_evidence_manifest", [])
    sig_ev_entries = [e for e in ev_manifest_passed if e.get("evidence_family") == "SIGNATURE"]
    assert len(sig_ev_entries) == 1
    assert sig_ev_entries[0]["field_key"] == "inspector_signature"
