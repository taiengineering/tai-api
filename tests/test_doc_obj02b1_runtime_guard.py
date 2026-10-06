"""OBJ02-B1: Runtime fail-close guard tests.

create_document() must deny any schema whose status != APPROVED_FOR_RUNTIME_USE.
"""

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

APPROVED_SCHEMA_ID = "cccccccc-0001-0001-0001-000000000001"
CANDIDATE_SCHEMA_ID = "cccccccc-0002-0002-0002-000000000002"
FACTORY_ID = "ffffffff-0001-0001-0001-000000000001"
USER_ID = "eeeeeeee-0001-0001-0001-000000000001"

_insert_calls: list = []

_SCHEMA_DB: dict[str, dict] = {
    APPROVED_SCHEMA_ID: {"id": APPROVED_SCHEMA_ID, "status": "APPROVED_FOR_RUNTIME_USE"},
    CANDIDATE_SCHEMA_ID: {"id": CANDIDATE_SCHEMA_ID, "status": "CANDIDATE"},
}
_STATUS_DB: dict[str, dict] = {
    "NEEDS_HUMAN_REVIEW": {"id": "cc-03", "status": "NEEDS_HUMAN_REVIEW"},
    "APPROVED_BY_HUMAN":  {"id": "cc-04", "status": "APPROVED_BY_HUMAN"},
    "REJECTED":           {"id": "cc-05", "status": "REJECTED"},
    "ARCHIVED":           {"id": "cc-06", "status": "ARCHIVED"},
}

# ── stub infrastructure ───────────────────────────────────────────────────────

class _FakeSingle:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return self


class _FakeInsert:
    def __init__(self):
        self.data = [{"id": "new-doc-id", "status": "DRAFT"}]

    def execute(self):
        return self


class _FakeQuery:
    def __init__(self, table):
        self._table = table
        self._schema_id: str = None

    def select(self, *_, **__):
        return self

    def eq(self, col, val):
        if col == "id":
            self._schema_id = val
        return self

    def single(self):
        row = _SCHEMA_DB.get(self._schema_id)
        return _FakeSingle(row)

    def insert(self, record):
        _insert_calls.append(record)
        return _FakeInsert()


class _FakeTable:
    def __init__(self, name):
        self._name = name

    def select(self, *_, **__):
        return _FakeQuery(self._name)

    def insert(self, record):
        _insert_calls.append(record)
        return _FakeInsert()


class _FakeSupabase:
    def table(self, name):
        return _FakeTable(name)


_MODULE_NAMES = (
    "db",
    "db.supabase_client",
    "services",
    "services.time",
    "services.document_engine_svc",
)
_MISSING = object()
_saved = {n: sys.modules.get(n, _MISSING) for n in _MODULE_NAMES}

try:
    _db_pkg = types.ModuleType("db")
    _db_pkg.__path__ = [str(ROOT / "db")]
    _db_client = types.ModuleType("db.supabase_client")
    _db_client.get_supabase = lambda: _FakeSupabase()
    _db_pkg.supabase_client = _db_client
    sys.modules["db"] = _db_pkg
    sys.modules["db.supabase_client"] = _db_client

    _svc_pkg = types.ModuleType("services")
    _svc_pkg.__path__ = [str(ROOT / "services")]
    _time_mod = types.ModuleType("services.time")
    _time_mod.now_kst = lambda: __import__("datetime").datetime(2026, 10, 7, 12, 0)
    _time_mod.serialize_external_utc = lambda dt: dt.isoformat() + "Z"
    _svc_pkg.time = _time_mod
    sys.modules["services"] = _svc_pkg
    sys.modules["services.time"] = _time_mod

    sys.modules.pop("services.document_engine_svc", None)
    from services.document_engine_svc import create_document

finally:
    for _n, _prev in _saved.items():
        if _prev is _MISSING:
            sys.modules.pop(_n, None)
        else:
            sys.modules[_n] = _prev


def _reset():
    _insert_calls.clear()


# ── G1: APPROVED_FOR_RUNTIME_USE → allowed ───────────────────────────────────

def test_G1_approved_schema_allowed():
    _reset()
    result = create_document(
        form_schema_id=APPROVED_SCHEMA_ID,
        factory_id=FACTORY_ID,
        created_by=USER_ID,
    )
    assert result.get("status") == "DRAFT"
    assert len(_insert_calls) >= 1


# ── G2: CANDIDATE → denied ───────────────────────────────────────────────────

def test_G2_candidate_schema_denied():
    _reset()
    try:
        create_document(form_schema_id=CANDIDATE_SCHEMA_ID, factory_id=FACTORY_ID)
        assert False, "should have raised ValueError"
    except ValueError as e:
        assert "CANDIDATE" in str(e)
    assert len(_insert_calls) == 0


# ── G3~G6: all non-APPROVED statuses → denied ────────────────────────────────

def _make_guard_schema(status: str):
    schema_id = f"guard-{status.lower()}"
    _SCHEMA_DB[schema_id] = {"id": schema_id, "status": status}
    return schema_id


def test_G3_needs_human_review_denied():
    _reset()
    sid = _make_guard_schema("NEEDS_HUMAN_REVIEW")
    try:
        create_document(form_schema_id=sid)
        assert False
    except ValueError as e:
        assert "NEEDS_HUMAN_REVIEW" in str(e)


def test_G4_approved_by_human_denied():
    _reset()
    sid = _make_guard_schema("APPROVED_BY_HUMAN")
    try:
        create_document(form_schema_id=sid)
        assert False
    except ValueError as e:
        assert "APPROVED_BY_HUMAN" in str(e)


def test_G5_rejected_denied():
    _reset()
    sid = _make_guard_schema("REJECTED")
    try:
        create_document(form_schema_id=sid)
        assert False
    except ValueError as e:
        assert "REJECTED" in str(e)


def test_G6_archived_denied():
    _reset()
    sid = _make_guard_schema("ARCHIVED")
    try:
        create_document(form_schema_id=sid)
        assert False
    except ValueError as e:
        assert "ARCHIVED" in str(e)


# ── G7: schema not found → denied ────────────────────────────────────────────

def test_G7_schema_not_found_denied():
    _reset()
    try:
        create_document(form_schema_id="nonexistent-id-999")
        assert False
    except ValueError as e:
        assert "not found" in str(e)
    assert len(_insert_calls) == 0


# ── G8: no DB insert for any denied schema ───────────────────────────────────

def test_G8_no_insert_on_deny():
    """Comprehensive: all non-APPROVED statuses produce zero inserts."""
    blocked_statuses = [
        "CANDIDATE", "NEEDS_HUMAN_REVIEW", "APPROVED_BY_HUMAN",
        "REJECTED", "ARCHIVED",
    ]
    for status in blocked_statuses:
        _reset()
        sid = _make_guard_schema(status)
        try:
            create_document(form_schema_id=sid)
        except ValueError:
            pass
        assert len(_insert_calls) == 0, (
            f"insert called for status={status}"
        )
