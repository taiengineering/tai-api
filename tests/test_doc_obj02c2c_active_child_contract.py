"""WO-DOC-OBJ02-C2C2: Active Child Contract tests.

C2C2-01  _validate_runtime_keys: APPROVED_BY_HUMAN field key → passes
C2C2-02  _validate_runtime_keys: inactive field key (status filter) → ValueError
C2C2-03  _validate_runtime_keys: APPROVED_BY_HUMAN checklist UUID → passes
C2C2-04  _validate_runtime_keys: inactive checklist UUID (status filter) → ValueError
C2C2-05  _validate_evidence_links: APPROVED_BY_HUMAN evidence id → passes
C2C2-06  _validate_evidence_links: inactive evidence id → ValueError
C2C2-07  get_form_schema_detail: APPROVED_FOR_RUNTIME_USE schema → status filter applied
C2C2-08  get_form_schema_detail: CANDIDATE schema → no status filter applied
C2C2-09  resolve_runtime_document_state: fields/checklists/evidence all use APPROVED_BY_HUMAN filter
C2C2-10  confirm: inactive field key in runtime_data_json → 422 INACTIVE_RUNTIME_KEY
C2C2-11  confirm: inactive checklist UUID in runtime_data_json → 422 INACTIVE_RUNTIME_KEY
C2C2-12  confirm: inactive evidence link → 422 INACTIVE_EVIDENCE_FIELD
C2C2-13  confirm: active field key + valid runtime_data_json → no inactive-key error
C2C2-14  confirm: active checklist UUID + valid value → no inactive-key error
C2C2-15  confirm: evidence_links referencing active evidence id → no inactive-evidence error
C2C2-16  apply_profile_to_document: inactive field (not APPROVED_BY_HUMAN) → SignatureError
"""

import sys
import types
import datetime as _dt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ── Shared UUIDs ──────────────────────────────────────────────────────────────

USER_ID   = "11111111-1111-1111-1111-111111111111"
SCHEMA_ID = "ssssssss-0001-0001-0001-000000000001"
DOC_ID    = "dddddddd-0001-0001-0001-000000000001"
FIELD_ID  = "ffffffff-0001-0001-0001-000000000001"
FIELD_KEY = "site_name"

ACTIVE_CL_UUID   = "cccccccc-0001-0001-0001-000000000001"  # APPROVED_BY_HUMAN
INACTIVE_CL_UUID = "cccccccc-9999-9999-9999-999999999999"  # not in active set

ACTIVE_EV_ID   = "eeeeeeee-0001-0001-0001-000000000001"
INACTIVE_EV_ID = "eeeeeeee-9999-9999-9999-999999999999"

ARCHIVE_ID = "aaaaaaaa-0001-0001-0001-000000000001"
TS = _dt.datetime(2026, 10, 7, 9, 0, 0, tzinfo=_dt.timezone.utc)

# ── Fake Supabase for engine/signature/resolve tests ─────────────────────────

class _FakeSingle:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return self


class _FakeResult:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return self


class _FakeQuery:
    """Minimal Supabase query builder fake.

    Tracks eq() filters so tests can control what 'active' rows are returned.
    """

    def __init__(self, table, *, active_field_keys=None, active_cl_ids=None,
                 active_ev_ids=None, schema_status="APPROVED_FOR_RUNTIME_USE"):
        self._table = table
        self._filters = {}
        self._active_field_keys = active_field_keys or {FIELD_KEY}
        self._active_cl_ids = active_cl_ids or {ACTIVE_CL_UUID}
        self._active_ev_ids = active_ev_ids or {ACTIVE_EV_ID}
        self._schema_status = schema_status

    def select(self, *_, **__):
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def order(self, *_, **__):
        return self

    def single(self):
        t = self._table
        if t == "runtime_form_schema":
            return _FakeSingle({
                "id": SCHEMA_ID,
                "status": self._schema_status,
                "form_name": "테스트",
                "version": 1,
                "catalog_document_id": None,
            })
        if t == "runtime_document_data":
            return _FakeSingle({
                "id": DOC_ID,
                "form_schema_id": SCHEMA_ID,
                "status": "DRAFT",
                "runtime_data_json": {},
                "evidence_links": [],
                "version": 1,
                "updated_at": "2026-10-07T00:00:00+00:00",
            })
        if t == "users":
            return _FakeSingle({
                "signature_url": "storage://signatures/profiles/user/sig.png",
                "signature_registered_at": "2026-10-01T00:00:00Z",
            })
        return _FakeSingle(None)

    def execute(self):
        t = self._table
        status_filter = self._filters.get("status")

        if t == "runtime_field":
            if status_filter == "APPROVED_BY_HUMAN":
                # Return only active fields
                return _FakeResult([
                    {"id": FIELD_ID, "field_key": fk, "input_type": "text",
                     "field_order": i, "status": "APPROVED_BY_HUMAN"}
                    for i, fk in enumerate(self._active_field_keys, 1)
                ])
            else:
                # No filter — return all (including inactive)
                return _FakeResult([
                    {"id": FIELD_ID, "field_key": FIELD_KEY, "input_type": "text",
                     "field_order": 1, "status": "APPROVED_BY_HUMAN"},
                    {"id": "ff000000-dead-dead-dead-000000000001", "field_key": "inactive_field",
                     "input_type": "text", "field_order": 2, "status": "CANDIDATE"},
                ])

        if t == "runtime_checklist_item":
            if status_filter == "APPROVED_BY_HUMAN":
                return _FakeResult([
                    {"id": cid, "form_schema_id": SCHEMA_ID, "raw_text": "점검항목",
                     "item_order": i, "status": "APPROVED_BY_HUMAN"}
                    for i, cid in enumerate(self._active_cl_ids, 1)
                ])
            else:
                return _FakeResult([
                    {"id": ACTIVE_CL_UUID, "form_schema_id": SCHEMA_ID, "raw_text": "점검항목",
                     "item_order": 1, "status": "APPROVED_BY_HUMAN"},
                    {"id": INACTIVE_CL_UUID, "form_schema_id": SCHEMA_ID, "raw_text": "중복점검",
                     "item_order": 2, "status": "REJECTED_BY_HUMAN"},
                ])

        if t == "runtime_evidence_field":
            if status_filter == "APPROVED_BY_HUMAN":
                return _FakeResult([
                    {"id": eid, "form_schema_id": SCHEMA_ID, "status": "APPROVED_BY_HUMAN"}
                    for eid in self._active_ev_ids
                ])
            else:
                return _FakeResult([
                    {"id": ACTIVE_EV_ID, "form_schema_id": SCHEMA_ID, "status": "APPROVED_BY_HUMAN"},
                    {"id": INACTIVE_EV_ID, "form_schema_id": SCHEMA_ID, "status": "REJECTED_BY_HUMAN"},
                ])

        return _FakeResult([])


class _FakeSupabase:
    def __init__(self, **kw):
        self._kw = kw

    def table(self, name):
        return _FakeQuery(name, **self._kw)


def _install_sb(monkeypatch, **kw):
    import services.document_engine_svc as eng
    monkeypatch.setattr(eng, "get_supabase", lambda: _FakeSupabase(**kw))


# ════════════════════════════════════════════════════════════════════════
# C2C2-01  _validate_runtime_keys: APPROVED_BY_HUMAN field key → passes
# ════════════════════════════════════════════════════════════════════════

def test_c2c2_01_active_field_key_passes(monkeypatch):
    sb = _FakeSupabase()
    from services.document_engine_svc import _validate_runtime_keys
    _validate_runtime_keys(sb, SCHEMA_ID, {FIELD_KEY: "서울"})


# ════════════════════════════════════════════════════════════════════════
# C2C2-02  _validate_runtime_keys: inactive field key → ValueError
# ════════════════════════════════════════════════════════════════════════

def test_c2c2_02_inactive_field_key_rejected(monkeypatch):
    # active_field_keys = {FIELD_KEY} only; "inactive_field" not in active set
    sb = _FakeSupabase(active_field_keys={FIELD_KEY})
    from services.document_engine_svc import _validate_runtime_keys
    try:
        _validate_runtime_keys(sb, SCHEMA_ID, {"inactive_field": "value"})
        assert False, "expected ValueError"
    except ValueError as e:
        assert "inactive_field" in str(e)


# ════════════════════════════════════════════════════════════════════════
# C2C2-03  _validate_runtime_keys: APPROVED_BY_HUMAN checklist UUID → passes
# ════════════════════════════════════════════════════════════════════════

def test_c2c2_03_active_checklist_uuid_passes(monkeypatch):
    sb = _FakeSupabase(active_cl_ids={ACTIVE_CL_UUID})
    from services.document_engine_svc import _validate_runtime_keys
    _validate_runtime_keys(sb, SCHEMA_ID, {ACTIVE_CL_UUID: "PASS"})


# ════════════════════════════════════════════════════════════════════════
# C2C2-04  _validate_runtime_keys: inactive checklist UUID → ValueError
# ════════════════════════════════════════════════════════════════════════

def test_c2c2_04_inactive_checklist_uuid_rejected(monkeypatch):
    # active_cl_ids = {ACTIVE_CL_UUID}; INACTIVE_CL_UUID not active
    sb = _FakeSupabase(active_cl_ids={ACTIVE_CL_UUID})
    from services.document_engine_svc import _validate_runtime_keys
    try:
        _validate_runtime_keys(sb, SCHEMA_ID, {INACTIVE_CL_UUID: "PASS"})
        assert False, "expected ValueError"
    except ValueError as e:
        assert INACTIVE_CL_UUID in str(e)


# ════════════════════════════════════════════════════════════════════════
# C2C2-05  _validate_evidence_links: APPROVED_BY_HUMAN evidence id → passes
# ════════════════════════════════════════════════════════════════════════

def test_c2c2_05_active_evidence_link_passes(monkeypatch):
    sb = _FakeSupabase(active_ev_ids={ACTIVE_EV_ID})
    from services.document_engine_svc import _validate_evidence_links
    _validate_evidence_links(sb, SCHEMA_ID, [{"linked_field_id": ACTIVE_EV_ID, "url": "https://x"}])


# ════════════════════════════════════════════════════════════════════════
# C2C2-06  _validate_evidence_links: inactive evidence id → ValueError
# ════════════════════════════════════════════════════════════════════════

def test_c2c2_06_inactive_evidence_link_rejected(monkeypatch):
    sb = _FakeSupabase(active_ev_ids={ACTIVE_EV_ID})
    from services.document_engine_svc import _validate_evidence_links
    try:
        _validate_evidence_links(sb, SCHEMA_ID, [{"linked_field_id": INACTIVE_EV_ID, "url": "https://x"}])
        assert False, "expected ValueError"
    except ValueError as e:
        assert INACTIVE_EV_ID in str(e)


# ════════════════════════════════════════════════════════════════════════
# C2C2-07  get_form_schema_detail: APPROVED_FOR_RUNTIME_USE → status filter
# ════════════════════════════════════════════════════════════════════════

def test_c2c2_07_get_form_schema_detail_approved_filters(monkeypatch):
    _install_sb(monkeypatch, schema_status="APPROVED_FOR_RUNTIME_USE",
                active_field_keys={FIELD_KEY}, active_cl_ids={ACTIVE_CL_UUID},
                active_ev_ids={ACTIVE_EV_ID})
    from services.document_engine_svc import get_form_schema_detail
    result = get_form_schema_detail(SCHEMA_ID)
    # All returned children should be the active sets only
    field_keys = {f["field_key"] for f in result["fields"]}
    assert FIELD_KEY in field_keys
    # "inactive_field" must NOT appear (it's filtered out by APPROVED_BY_HUMAN)
    assert "inactive_field" not in field_keys
    # Only active checklist returned
    cl_ids = {str(c["id"]) for c in result["checklists"]}
    assert ACTIVE_CL_UUID in cl_ids
    assert INACTIVE_CL_UUID not in cl_ids


# ════════════════════════════════════════════════════════════════════════
# C2C2-08  get_form_schema_detail: CANDIDATE schema → no status filter applied
# ════════════════════════════════════════════════════════════════════════

def test_c2c2_08_get_form_schema_detail_candidate_no_filter(monkeypatch):
    _install_sb(monkeypatch, schema_status="CANDIDATE")
    from services.document_engine_svc import get_form_schema_detail
    result = get_form_schema_detail(SCHEMA_ID)
    # No status filter → both active and inactive rows returned
    field_keys = {f["field_key"] for f in result["fields"]}
    # inactive_field appears because no filter was applied
    assert "inactive_field" in field_keys


# ════════════════════════════════════════════════════════════════════════
# C2C2-09  resolve_runtime_document_state: always filters APPROVED_BY_HUMAN
# ════════════════════════════════════════════════════════════════════════

def test_c2c2_09_resolve_state_uses_approved_filter(monkeypatch):
    _install_sb(monkeypatch, active_field_keys={FIELD_KEY},
                active_cl_ids={ACTIVE_CL_UUID}, active_ev_ids={ACTIVE_EV_ID})
    from services.document_engine_svc import resolve_runtime_document_state
    state = resolve_runtime_document_state(DOC_ID)
    field_keys = {f["field_key"] for f in state["fields"]}
    assert FIELD_KEY in field_keys
    assert "inactive_field" not in field_keys
    cl_ids = {str(c["id"]) for c in state["checklists"]}
    assert ACTIVE_CL_UUID in cl_ids
    assert INACTIVE_CL_UUID not in cl_ids
    ev_ids = {str(e["id"]) for e in state["evidence_fields"]}
    assert ACTIVE_EV_ID in ev_ids
    assert INACTIVE_EV_ID not in ev_ids


# ════════════════════════════════════════════════════════════════════════
# C2C2-10 ~ 15  confirm_document_atomic — inactive key / evidence fail-close
# Use the psycopg2-fake layer from test_document_confirm_svc infrastructure.
# ════════════════════════════════════════════════════════════════════════

import services.document_confirm_svc as _cmod
from services.document_confirm_svc import confirm_document_atomic, ConfirmError


class _FakeErrors:
    class UniqueViolation(Exception): pass
    class LockNotAvailable(Exception): pass
    class DeadlockDetected(Exception): pass
    class QueryCanceled(Exception): pass


class _FakeExtras:
    class RealDictCursor: pass


class _FakePsycopg2:
    OperationalError = Exception
    errors = _FakeErrors
    extras = _FakeExtras


COMPANY_A = "aaaaaaaa-0001-0001-0001-000000000001"


def _locked_row(runtime=None, evidence=None):
    return {
        "id": DOC_ID,
        "form_schema_id": SCHEMA_ID,
        "status": "REVIEW_PENDING",
        "company_id": COMPANY_A,
        "factory_id": None,
        "version": 1,
        "submitted_by": USER_ID,
        "runtime_data_json": {} if runtime is None else runtime,
        "evidence_links": [] if evidence is None else evidence,
    }


def _user(uid=USER_ID):
    return {"id": uid, "role_code": "011", "company_id": COMPANY_A, "factory_id": None}


class _ConfirmFakeCursor:
    """Extended FakeCursor that supports runtime_evidence_field routing.

    Passes active field/checklist/evidence ids from FakeConfirmConn.
    """

    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        s = sql.strip().upper()
        self.conn.executed.append((s[:60], params))
        for marker, exc in self.conn.fail_on.items():
            if marker in sql:
                raise exc
        if "FOR UPDATE" in s:
            self.conn._last = self.conn.locked_row
            self.conn._last_many = []
        elif "FROM FACTORIES" in s:
            self.conn._last = self.conn.factory_row
            self.conn._last_many = []
        elif "RUNTIME_STATE_TRANSITION_RULE" in s:
            self.conn._last = self.conn.rule_row
            self.conn._last_many = []
        elif "RUNTIME_FORM_SCHEMA" in s:
            self.conn._last = self.conn.schema_row
            self.conn._last_many = []
        elif "RUNTIME_FIELD" in s:
            self.conn._last_many = self.conn.field_rows
            self.conn._last = None
        elif "RUNTIME_CHECKLIST_ITEM" in s:
            self.conn._last_many = self.conn.checklist_rows
            self.conn._last = None
        elif "RUNTIME_EVIDENCE_FIELD" in s:
            self.conn._last_many = self.conn.evidence_rows
            self.conn._last = None
        elif "CLOCK_TIMESTAMP" in s:
            self.conn._last = {"ts": TS}
            self.conn._last_many = []
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
            if params:
                sealed["reviewed_by"] = params[1]
                sealed["reviewed_at"] = params[2]
            self.conn._last = sealed
        else:
            self.conn._last = None
            self.conn._last_many = []

    def fetchone(self):
        return self.conn._last

    def fetchall(self):
        return list(getattr(self.conn, "_last_many", []))


class _ConfirmFakeConn:
    def __init__(self, **kw):
        self.locked_row = kw.get("locked_row", _locked_row())
        self.factory_row = kw.get("factory_row", None)
        self.rule_row = kw.get("rule_row", {"requires_reviewer": True, "requires_comment": True})
        self.schema_row = kw.get("schema_row", {"id": SCHEMA_ID, "form_name": "테스트"})
        self.field_rows = kw.get("field_rows", [])
        self.checklist_rows = kw.get("checklist_rows", [])
        self.evidence_rows = kw.get("evidence_rows", [])
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
        return _ConfirmFakeCursor(self)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def _install_confirm(conn, audit_calls=None):
    import db.direct_sql as ds
    ds._connect = lambda: conn
    sys.modules["psycopg2"] = _FakePsycopg2
    sys.modules["psycopg2.errors"] = _FakeErrors
    sys.modules["psycopg2.extras"] = _FakeExtras
    if audit_calls is not None:
        _cmod._best_effort_audit = lambda *a, **k: audit_calls.append(a)


# ════════════════════════════════════════════════════════════════════════
# C2C2-10  confirm: inactive field key in runtime_data_json → 422
# ════════════════════════════════════════════════════════════════════════

def test_c2c2_10_confirm_inactive_field_key_422():
    # field_rows is empty → "inactive_field" is not in active set
    conn = _ConfirmFakeConn(
        locked_row=_locked_row(runtime={"inactive_field": "value"}),
        field_rows=[],
        checklist_rows=[],
    )
    _install_confirm(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="ok", current_user=_user())
        assert False, "expected ConfirmError"
    except ConfirmError as e:
        assert e.http_status == 422
        assert "INACTIVE_RUNTIME_KEY" in e.detail
    assert conn.rolled_back


# ════════════════════════════════════════════════════════════════════════
# C2C2-11  confirm: inactive checklist UUID in runtime_data_json → 422
# ════════════════════════════════════════════════════════════════════════

def test_c2c2_11_confirm_inactive_checklist_uuid_422():
    # checklist_rows empty → INACTIVE_CL_UUID not active
    conn = _ConfirmFakeConn(
        locked_row=_locked_row(runtime={INACTIVE_CL_UUID: "PASS"}),
        field_rows=[],
        checklist_rows=[],
    )
    _install_confirm(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="ok", current_user=_user())
        assert False, "expected ConfirmError"
    except ConfirmError as e:
        assert e.http_status == 422
        assert "INACTIVE_RUNTIME_KEY" in e.detail
    assert conn.rolled_back


# ════════════════════════════════════════════════════════════════════════
# C2C2-12  confirm: inactive evidence link → 422 INACTIVE_EVIDENCE_FIELD
# ════════════════════════════════════════════════════════════════════════

def test_c2c2_12_confirm_inactive_evidence_link_422():
    # evidence_rows empty → INACTIVE_EV_ID not active
    conn = _ConfirmFakeConn(
        locked_row=_locked_row(evidence=[{"linked_field_id": INACTIVE_EV_ID, "url": "https://x"}]),
        field_rows=[],
        checklist_rows=[],
        evidence_rows=[],
    )
    _install_confirm(conn)
    try:
        confirm_document_atomic(DOC_ID, actor_id=None, comment="ok", current_user=_user())
        assert False, "expected ConfirmError"
    except ConfirmError as e:
        assert e.http_status == 422
        assert "INACTIVE_EVIDENCE_FIELD" in e.detail
    assert conn.rolled_back


# ════════════════════════════════════════════════════════════════════════
# C2C2-13  confirm: active field key → inactive-key check passes
# ════════════════════════════════════════════════════════════════════════

def test_c2c2_13_confirm_active_field_key_passes():
    audit = []
    conn = _ConfirmFakeConn(
        locked_row=_locked_row(runtime={FIELD_KEY: "현장A"}),
        field_rows=[{"field_key": FIELD_KEY, "id": FIELD_ID, "input_type": "text",
                     "field_label": "현장명", "required_status": "NOT_REQUIRED",
                     "form_schema_id": SCHEMA_ID}],
        checklist_rows=[],
        evidence_rows=[],
    )
    _install_confirm(conn, audit)
    out = confirm_document_atomic(DOC_ID, actor_id=None, comment="ok", current_user=_user())
    assert conn.committed
    assert out["status"] == "APPROVED_BY_HUMAN"


# ════════════════════════════════════════════════════════════════════════
# C2C2-14  confirm: active checklist UUID → passes
# ════════════════════════════════════════════════════════════════════════

def test_c2c2_14_confirm_active_checklist_uuid_passes():
    audit = []
    conn = _ConfirmFakeConn(
        locked_row=_locked_row(runtime={ACTIVE_CL_UUID: "PASS"}),
        field_rows=[],
        checklist_rows=[{"id": ACTIVE_CL_UUID, "form_schema_id": SCHEMA_ID,
                         "raw_text": "점검항목", "item_order": 1,
                         "input_type": "PASS_FAIL_NA"}],
        evidence_rows=[],
    )
    _install_confirm(conn, audit)
    out = confirm_document_atomic(DOC_ID, actor_id=None, comment="ok", current_user=_user())
    assert conn.committed
    assert out["status"] == "APPROVED_BY_HUMAN"


# ════════════════════════════════════════════════════════════════════════
# C2C2-15  confirm: evidence_links with active evidence id → passes
# ════════════════════════════════════════════════════════════════════════

def test_c2c2_15_confirm_active_evidence_link_passes():
    audit = []
    conn = _ConfirmFakeConn(
        locked_row=_locked_row(evidence=[{"linked_field_id": ACTIVE_EV_ID, "url": "https://x"}]),
        field_rows=[],
        checklist_rows=[],
        evidence_rows=[{"id": ACTIVE_EV_ID}],
    )
    _install_confirm(conn, audit)
    out = confirm_document_atomic(DOC_ID, actor_id=None, comment="ok", current_user=_user())
    assert conn.committed
    assert out["status"] == "APPROVED_BY_HUMAN"


# ════════════════════════════════════════════════════════════════════════
# C2C2-16  apply_profile_to_document: inactive field → SignatureError
# ════════════════════════════════════════════════════════════════════════

def test_c2c2_16_signature_inactive_field_rejected(monkeypatch):
    """Field not in APPROVED_BY_HUMAN set → SignatureError 'field_key not found'."""

    class _SigFakeQuery:
        def __init__(self, table):
            self._table = table
            self._filters = {}

        def select(self, *_, **__):
            return self

        def eq(self, col, val):
            self._filters[col] = val
            return self

        def single(self):
            t = self._table
            if t == "runtime_document_data":
                return _FakeSingle({
                    "id": DOC_ID,
                    "form_schema_id": SCHEMA_ID,
                    "status": "DRAFT",
                    "runtime_data_json": {},
                    "evidence_links": [],
                    "version": 1,
                    "updated_at": "2026-10-07T00:00:00+00:00",
                })
            if t == "users":
                return _FakeSingle({
                    "signature_url": "storage://signatures/profiles/user/sig.png",
                    "signature_registered_at": "2026-10-01T00:00:00Z",
                })
            return _FakeSingle(None)

        def execute(self):
            t = self._table
            status_filter = self._filters.get("status")
            if t == "runtime_field":
                if status_filter == "APPROVED_BY_HUMAN":
                    # Return empty → field_key not in active set
                    return _FakeResult([])
                return _FakeResult([{
                    "id": FIELD_ID,
                    "field_key": "sig_field",
                    "input_type": "signature",
                    "status": "CANDIDATE",  # inactive
                }])
            return _FakeResult([])

    class _SigFakeSupabase:
        def table(self, name):
            return _SigFakeQuery(name)

    import services.document_signature_svc as sig_svc
    monkeypatch.setattr(sig_svc, "get_supabase", lambda: _SigFakeSupabase())

    from services.document_signature_svc import apply_profile_to_document, SignatureError
    try:
        apply_profile_to_document(DOC_ID, "sig_field", {"id": USER_ID})
        assert False, "expected SignatureError"
    except SignatureError as e:
        assert "not found in schema" in str(e)
