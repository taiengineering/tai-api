"""OBJ02-B1: Catalog resolver + workspace readmodel tests."""

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CAT_ID_APPROVED = "ddddd001-0001-0001-0001-000000000001"
CAT_ID_PREPARING = "ddddd002-0002-0002-0002-000000000002"
CAT_ID_NO_SCHEMA = "ddddd003-0003-0003-0003-000000000003"
CAT_ID_MISSING = "ddddd999-9999-9999-9999-999999999999"

SCHEMA_APPROVED_ID = "eeeee001-0001-0001-0001-000000000001"
SCHEMA_CANDIDATE_ID = "eeeee002-0002-0002-0002-000000000002"

_CATALOG_DB = {
    CAT_ID_APPROVED: {"id": CAT_ID_APPROVED, "doc_id": "D001",
                      "doc_name": "점검표 A", "document_family": "CHK",
                      "created_at": "2026-01-01T00:00:00Z",
                      "updated_at": "2026-01-01T00:00:00Z"},
    CAT_ID_PREPARING: {"id": CAT_ID_PREPARING, "doc_id": "D002",
                       "doc_name": "점검표 B", "document_family": "CHK",
                       "created_at": "2026-01-01T00:00:00Z",
                       "updated_at": "2026-01-01T00:00:00Z"},
    CAT_ID_NO_SCHEMA: {"id": CAT_ID_NO_SCHEMA, "doc_id": "D003",
                       "doc_name": "점검표 C", "document_family": "EQUIP",
                       "created_at": "2026-01-01T00:00:00Z",
                       "updated_at": "2026-01-01T00:00:00Z"},
}

_SCHEMA_DB_BY_CATALOG = {
    CAT_ID_APPROVED: [
        {"id": SCHEMA_APPROVED_ID, "status": "APPROVED_FOR_RUNTIME_USE",
         "form_name": "점검표 A v1", "version": 1,
         "catalog_document_id": CAT_ID_APPROVED,
         "source_trace": {"source_table": "document_forms"}},
    ],
    CAT_ID_PREPARING: [
        {"id": SCHEMA_CANDIDATE_ID, "status": "CANDIDATE",
         "form_name": "점검표 B v1 draft", "version": 1,
         "catalog_document_id": CAT_ID_PREPARING,
         "source_trace": {"source_table": "document_forms"}},
    ],
    CAT_ID_NO_SCHEMA: [],
}

_FIELDS_DB = {
    SCHEMA_APPROVED_ID: [
        {"id": "f001", "form_schema_id": SCHEMA_APPROVED_ID,
         "field_key": "site_name", "field_label": "현장명",
         "input_type": "text", "field_order": 1, "required_status": "REQUIRED"},
    ],
}

# ── Fake Supabase ─────────────────────────────────────────────────────────────

class _FakeSingle:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return self


class _FakeResult:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count or len(data)

    def execute(self):
        return self


class _FakeQuery:
    def __init__(self, table_name):
        self._table = table_name
        self._filters: dict = {}
        self._in_values: list = []
        self._cols = "*"

    def select(self, cols="*", **__):
        self._cols = cols
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def in_(self, col, vals):
        self._in_values = list(vals)
        return self

    def order(self, *_, **__):
        return self

    def range(self, *_, **__):
        return self

    def single(self):
        table = self._table
        if table == "document_forms":
            cat_id = self._filters.get("id")
            return _FakeSingle(_CATALOG_DB.get(cat_id))
        if table == "runtime_form_schema":
            schema_id = self._filters.get("id")
            for schemas in _SCHEMA_DB_BY_CATALOG.values():
                for s in schemas:
                    if s["id"] == schema_id:
                        return _FakeSingle(s)
            return _FakeSingle(None)
        return _FakeSingle(None)

    def execute(self):
        table = self._table
        if table == "document_forms":
            if self._in_values:
                rows = [_CATALOG_DB[i] for i in self._in_values if i in _CATALOG_DB]
                return _FakeResult(rows)
            rows = list(_CATALOG_DB.values())
            return _FakeResult(rows)

        if table == "runtime_form_schema":
            cat_id = self._filters.get("catalog_document_id")
            if cat_id:
                return _FakeResult(_SCHEMA_DB_BY_CATALOG.get(cat_id, []))
            if self._in_values:
                rows = []
                for cid in self._in_values:
                    rows.extend(_SCHEMA_DB_BY_CATALOG.get(cid, []))
                return _FakeResult(rows)
            return _FakeResult([])

        if table == "runtime_field":
            schema_id = self._filters.get("form_schema_id")
            return _FakeResult(_FIELDS_DB.get(schema_id, []))

        return _FakeResult([])


class _FakeSupabase:
    def table(self, name):
        return _FakeQuery(name)


# ── module isolation ──────────────────────────────────────────────────────────

_MODULE_NAMES = (
    "db",
    "db.supabase_client",
    "services",
    "services.document_engine",
    "services.document_engine.catalog_resolver",
    "services.document_engine.workspace_readmodel",
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
    sys.modules["services"] = _svc_pkg

    _doc_eng_pkg = types.ModuleType("services.document_engine")
    _doc_eng_pkg.__path__ = [str(ROOT / "services" / "document_engine")]
    sys.modules["services.document_engine"] = _doc_eng_pkg

    for mod_name in (
        "services.document_engine.catalog_resolver",
        "services.document_engine.workspace_readmodel",
    ):
        sys.modules.pop(mod_name, None)

    from services.document_engine.catalog_resolver import resolve_catalog_runtime_schema
    from services.document_engine.workspace_readmodel import list_document_workspace

finally:
    for _n, _prev in _saved.items():
        if _prev is _MISSING:
            sys.modules.pop(_n, None)
        else:
            sys.modules[_n] = _prev


# ── Resolver tests ────────────────────────────────────────────────────────────

def test_R1_approved_doc_returns_ready_for_edit():
    result = resolve_catalog_runtime_schema(CAT_ID_APPROVED)
    assert result["availability"] == "READY_FOR_EDIT"
    assert result["schema"] is not None
    assert result["schema"]["id"] == SCHEMA_APPROVED_ID
    assert result["schema"]["status"] == "APPROVED_FOR_RUNTIME_USE"


def test_R2_fields_populated_for_approved():
    result = resolve_catalog_runtime_schema(CAT_ID_APPROVED)
    assert len(result["fields"]) == 1
    assert result["fields"][0]["field_key"] == "site_name"


def test_R3_preparing_doc_returns_no_schema():
    result = resolve_catalog_runtime_schema(CAT_ID_PREPARING)
    assert result["availability"] == "PREPARING"
    assert result["schema"] is None
    assert result["fields"] == []


def test_R4_no_schema_doc_returns_no_schema():
    result = resolve_catalog_runtime_schema(CAT_ID_NO_SCHEMA)
    assert result["availability"] == "NO_SCHEMA"
    assert result["schema"] is None


def test_R5_missing_catalog_raises_value_error():
    try:
        resolve_catalog_runtime_schema(CAT_ID_MISSING)
        assert False, "should raise ValueError"
    except ValueError as e:
        assert CAT_ID_MISSING in str(e)


def test_R6_resolver_returns_all_keys():
    result = resolve_catalog_runtime_schema(CAT_ID_APPROVED)
    assert set(result.keys()) == {
        "availability", "schema", "fields", "checklists", "evidence_fields"
    }


# ── Workspace readmodel tests ─────────────────────────────────────────────────

def test_W1_workspace_returns_all_catalog_rows():
    result = list_document_workspace()
    assert "items" in result
    assert "total" in result
    assert result["total"] >= 3


def test_W2_availability_field_present():
    result = list_document_workspace()
    for item in result["items"]:
        assert "availability" in item
        assert item["availability"] in ("READY_FOR_EDIT", "PREPARING", "NO_SCHEMA")


def test_W3_schema_id_populated_for_approved():
    result = list_document_workspace()
    approved_items = [i for i in result["items"] if i["availability"] == "READY_FOR_EDIT"]
    for item in approved_items:
        assert item["schema_id"] is not None
        assert item["schema_status"] == "APPROVED_FOR_RUNTIME_USE"


def test_W4_schema_id_null_for_preparing():
    result = list_document_workspace()
    preparing = [i for i in result["items"] if i["availability"] == "PREPARING"]
    for item in preparing:
        assert item["schema_id"] is None
        assert item["candidate_count"] >= 1


def test_W5_schema_id_null_for_no_schema():
    result = list_document_workspace()
    no_schema = [i for i in result["items"] if i["availability"] == "NO_SCHEMA"]
    for item in no_schema:
        assert item["schema_id"] is None
        assert item["candidate_count"] == 0


def test_W6_availability_filter():
    result = list_document_workspace(availability="READY_FOR_EDIT")
    for item in result["items"]:
        assert item["availability"] == "READY_FOR_EDIT"


def test_W7_page_size_in_result():
    result = list_document_workspace(page=1, page_size=1)
    assert result["page_size"] == 1
    assert result["page"] == 1


def test_W8_page_size_capped_at_200():
    result = list_document_workspace(page=1, page_size=9999)
    assert result["page_size"] == 200
