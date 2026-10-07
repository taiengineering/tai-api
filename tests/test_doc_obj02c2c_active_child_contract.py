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


# ════════════════════════════════════════════════════════════════════════
# MIG-01 ~ MIG-08  Static migration contract tests
# Read the migration file as text; assert/deny specific tokens.
# These tests do NOT run SQL — they verify the migration text is correct.
# ════════════════════════════════════════════════════════════════════════

_MIG_FILE = ROOT / "supabase" / "migrations" / "20261007131755_document_c2c2_active_child_correction.sql"


def _mig_sql():
    return _MIG_FILE.read_text(encoding="utf-8")


# MIG-01: migration file exists at expected path
def test_mig_01_file_exists():
    assert _MIG_FILE.exists(), f"migration file not found: {_MIG_FILE}"


# MIG-02: BLOCKER-1 fixed — APPROVED_FOR_RUNTIME_USE absent
def test_mig_02_approved_for_runtime_use_absent():
    assert "APPROVED_FOR_RUNTIME_USE" not in _mig_sql(), \
        "BLOCKER-1: APPROVED_FOR_RUNTIME_USE must not appear (invalid status for document_schema_candidate)"


# MIG-03: BLOCKER-2 fixed — rf.is_mandatory absent (column does not exist on runtime_field)
def test_mig_03_rf_is_mandatory_absent():
    assert "rf.is_mandatory" not in _mig_sql(), \
        "BLOCKER-2: rf.is_mandatory is not a column on runtime_field; use field_candidate.is_mandatory"


# MIG-04: BLOCKER-3 fixed — updated_at absent (no such column on child tables)
def test_mig_04_updated_at_absent():
    assert "updated_at" not in _mig_sql(), \
        "BLOCKER-3: runtime_field/runtime_checklist_item/runtime_evidence_field have no updated_at column"


# MIG-05: BLOCKER-4 fixed — old audit column name row_id absent
def test_mig_05_old_audit_row_id_absent():
    assert "row_id" not in _mig_sql(), \
        "BLOCKER-4: wrong audit column 'row_id' must not appear; correct column is 'target_id'"


# MIG-06: P0 scope uses document_type_mapping join with correct doc_type values
def test_mig_06_document_type_mapping_present():
    sql = _mig_sql()
    assert "document_type_mapping" in sql, \
        "P0 target must use document_type_mapping join"
    assert "'EQUIP'" in sql and "'INSP'" in sql and "'CHK'" in sql and "'TBM'" in sql and "'PPE'" in sql, \
        "P0 doc_type filter must include EQUIP, INSP, CHK, TBM, PPE"


# MIG-07: field_candidate join present for required_status derivation
def test_mig_07_field_candidate_is_mandatory_present():
    sql = _mig_sql()
    assert "field_candidate" in sql, \
        "required_status derivation requires reference to field_candidate"
    assert "fc.is_mandatory" in sql, \
        "required_status must be derived from fc.is_mandatory (field_candidate alias fc)"


# MIG-08: correct audit columns present; old wrong column names absent
def test_mig_08_correct_audit_columns():
    sql = _mig_sql()
    assert "target_table" in sql, "audit INSERT must use 'target_table'"
    assert "target_id" in sql, "audit INSERT must use 'target_id'"
    assert "changed_by" in sql, "audit INSERT must use 'changed_by'"
    assert "table_name" not in sql, \
        "BLOCKER-4: wrong audit column 'table_name' must not appear"
    assert "changed_at" not in sql, \
        "BLOCKER-4: wrong audit column 'changed_at' must not appear; use 'created_at'"


# ════════════════════════════════════════════════════════════════════════
# MIG-09 ~ MIG-19  CORR-002 fail-close guard structural tests
# These tests verify that named guards and exact assertions exist in the
# migration SQL; they check for guard variable names + assertion patterns,
# not just isolated token presence.
# ════════════════════════════════════════════════════════════════════════

# MIG-09: target schema distinct=24 guard exists (PRE-1)
def test_mig_09_target_schema_distinct_24_guard():
    sql = _mig_sql()
    assert "COUNT(DISTINCT rfs.id)" in sql, \
        "MIG-09: COUNT(DISTINCT rfs.id) must appear for schema distinct count"
    assert "v_pre_schema_count <> 24" in sql, \
        "MIG-09: assertion 'v_pre_schema_count <> 24' must be present"


# MIG-10: target schema CANDIDATE=24 guard exists in both pre and post
def test_mig_10_target_schema_candidate_24_both_guards():
    sql = _mig_sql()
    assert "v_pre_schema_candidate <> 24" in sql, \
        "MIG-10: precondition 'v_pre_schema_candidate <> 24' must be present"
    assert "v_post_schema_candidate <> 24" in sql, \
        "MIG-10: postcondition 'v_post_schema_candidate <> 24' must be present"


# MIG-11: field_candidate FK matched=96 guard exists (PRE-2)
def test_mig_11_field_fk_matched_96_guard():
    sql = _mig_sql()
    assert "v_pre_fk_matched <> 96" in sql, \
        "MIG-11: assertion 'v_pre_fk_matched <> 96' must be present"


# MIG-12: mandatory true=38 / false=58 / null=0 exact guards exist (PRE-2)
def test_mig_12_mandatory_exact_guards():
    sql = _mig_sql()
    assert "v_pre_mandatory_true <> 38" in sql, \
        "MIG-12: mandatory true=38 assertion must be present"
    assert "v_pre_mandatory_false <> 58" in sql, \
        "MIG-12: mandatory false=58 assertion must be present"
    assert "v_pre_mandatory_null <> 0" in sql, \
        "MIG-12: mandatory null=0 assertion must be present"


# MIG-13: evidence FK chain via evidence_field_candidate.field_candidate_id exists (PRE-4)
def test_mig_13_evidence_fk_chain_guard():
    sql = _mig_sql()
    assert "evidence_field_candidate" in sql, \
        "MIG-13: evidence_field_candidate must be joined in evidence guard"
    assert "efc.field_candidate_id" in sql, \
        "MIG-13: efc.field_candidate_id must be used in FK chain"


# MIG-14: timestamp_auto → date semantic pair guard exists
def test_mig_14_timestamp_auto_date_semantic_pair():
    sql = _mig_sql()
    assert "re.upload_type = 'timestamp_auto' AND rf.input_type = 'date'" in sql, \
        "MIG-14: semantic pair timestamp_auto → date must be explicitly guarded"


# MIG-15: signature → signature semantic pair guard exists
def test_mig_15_signature_signature_semantic_pair():
    sql = _mig_sql()
    assert "re.upload_type = 'signature'" in sql, \
        "MIG-15: re.upload_type = 'signature' must appear in semantic guard"
    assert "rf.input_type = 'signature'" in sql, \
        "MIG-15: rf.input_type = 'signature' must appear in semantic pair"


# MIG-16: audit exact total=204 postcondition exists (POST-5)
def test_mig_16_audit_total_204_guard():
    sql = _mig_sql()
    assert "v_post_audit_total <> 204" in sql, \
        "MIG-16: assertion 'v_post_audit_total <> 204' must be present"


# MIG-17: audit per-table 96/96/12 guards exist (POST-5)
def test_mig_17_audit_per_table_guards():
    sql = _mig_sql()
    assert "v_post_audit_field <> 96" in sql, \
        "MIG-17: audit field=96 assertion must be present"
    assert "v_post_audit_cl <> 96" in sql, \
        "MIG-17: audit checklist=96 assertion must be present"
    assert "v_post_audit_ev <> 12" in sql, \
        "MIG-17: audit evidence=12 assertion must be present"


# MIG-18: post-condition schema CANDIDATE=24 guard exists (POST-1)
def test_mig_18_post_schema_candidate_24_guard():
    sql = _mig_sql()
    assert "v_post_schema_candidate <> 24" in sql, \
        "MIG-18: postcondition 'v_post_schema_candidate <> 24' must be present"


# MIG-19: post-condition required_status 38/58 exact guards exist (POST-2)
def test_mig_19_post_required_status_guards():
    sql = _mig_sql()
    assert "v_post_required <> 38" in sql, \
        "MIG-19: postcondition REQUIRED_BY_HUMAN=38 assertion must be present"
    assert "v_post_not_required <> 58" in sql, \
        "MIG-19: postcondition NOT_REQUIRED=58 assertion must be present"
