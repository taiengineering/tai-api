"""OBJ02-B1 (CORR-01/02/04): Catalog resolver + workspace readmodel tests.

CORR-01: Catalog fixtures use actual document_forms columns (no document_family).
CORR-02: Pagination test verifies filter-before-paginate (W9).
CORR-04: Resolver parameter renamed catalog_document_id throughout.
"""

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CAT_ID_APPROVED  = "ddddd001-0001-0001-0001-000000000001"
CAT_ID_PREPARING = "ddddd002-0002-0002-0002-000000000002"
CAT_ID_NO_SCHEMA = "ddddd003-0003-0003-0003-000000000003"
CAT_ID_MISSING   = "ddddd999-9999-9999-9999-999999999999"

# Pagination test catalog IDs (W9): 3 READY, 3 PREPARING
CAT_P1 = "pppp0001-0001-0001-0001-000000000001"
CAT_P2 = "pppp0002-0002-0002-0002-000000000002"
CAT_P3 = "pppp0003-0003-0003-0003-000000000003"
CAT_P4 = "pppp0004-0004-0004-0004-000000000004"
CAT_P5 = "pppp0005-0005-0005-0005-000000000005"
CAT_P6 = "pppp0006-0006-0006-0006-000000000006"

SCHEMA_APPROVED_ID  = "eeeee001-0001-0001-0001-000000000001"
SCHEMA_CANDIDATE_ID = "eeeee002-0002-0002-0002-000000000002"

# ── Fixture: actual document_forms columns only ───────────────────────────────
# Production columns: id, doc_id, doc_name, sector, category, law_ref, obligation,
#   tai_grade, tai_difficulty, priority, has_legal_form, tai_auto, tai_method,
#   doc_format, doc_owner, is_external_writer, is_active
# Workspace SELECT uses: id, doc_id, doc_name, sector, category, is_active, priority

_KNOWN_DOCUMENT_FORMS_COLUMNS = frozenset({
    "id", "doc_id", "doc_name", "sector", "category",
    "law_ref", "obligation", "tai_grade", "tai_difficulty",
    "priority", "has_legal_form", "tai_auto", "tai_method",
    "doc_format", "doc_owner", "is_external_writer", "is_active",
})

def _cat(cid, doc_id, doc_name, sector="CONSTRUCTION", category="일상",
         is_active=True, priority=3):
    return {
        "id": cid, "doc_id": doc_id, "doc_name": doc_name,
        "sector": sector, "category": category,
        "is_active": is_active, "priority": priority,
    }

_CATALOG_DB = {
    CAT_ID_APPROVED:  _cat(CAT_ID_APPROVED,  "D001", "점검표 A"),
    CAT_ID_PREPARING: _cat(CAT_ID_PREPARING, "D002", "점검표 B"),
    CAT_ID_NO_SCHEMA: _cat(CAT_ID_NO_SCHEMA, "D003", "점검표 C"),
    # pagination fixtures (ordered: P1,P2 PREPARING | P3,P4,P5 READY | P6 PREPARING)
    CAT_P1: _cat(CAT_P1, "PP1", "페이징-준비1"),
    CAT_P2: _cat(CAT_P2, "PP2", "페이징-준비2"),
    CAT_P3: _cat(CAT_P3, "PP3", "페이징-완료1"),
    CAT_P4: _cat(CAT_P4, "PP4", "페이징-완료2"),
    CAT_P5: _cat(CAT_P5, "PP5", "페이징-준비3"),
    CAT_P6: _cat(CAT_P6, "PP6", "페이징-완료3"),
}

_SCHEMA_DB_BY_CATALOG = {
    CAT_ID_APPROVED:  [{"id": SCHEMA_APPROVED_ID, "status": "APPROVED_FOR_RUNTIME_USE",
                        "form_name": "점검표 A v1", "version": 1,
                        "catalog_document_id": CAT_ID_APPROVED,
                        "source_trace": {"source_table": "document_forms"}}],
    CAT_ID_PREPARING: [{"id": SCHEMA_CANDIDATE_ID, "status": "CANDIDATE",
                        "form_name": "점검표 B v1 draft", "version": 1,
                        "catalog_document_id": CAT_ID_PREPARING,
                        "source_trace": {"source_table": "document_forms"}}],
    CAT_ID_NO_SCHEMA: [],
    # P1,P2,P5 → PREPARING; P3,P4,P6 → READY_FOR_EDIT
    CAT_P1: [{"id": "sp1", "status": "CANDIDATE", "form_name": "c", "version": 1,
              "catalog_document_id": CAT_P1}],
    CAT_P2: [{"id": "sp2", "status": "CANDIDATE", "form_name": "c", "version": 1,
              "catalog_document_id": CAT_P2}],
    CAT_P3: [{"id": "sp3", "status": "APPROVED_FOR_RUNTIME_USE", "form_name": "c",
              "version": 1, "catalog_document_id": CAT_P3}],
    CAT_P4: [{"id": "sp4", "status": "APPROVED_FOR_RUNTIME_USE", "form_name": "c",
              "version": 1, "catalog_document_id": CAT_P4}],
    CAT_P5: [{"id": "sp5", "status": "CANDIDATE", "form_name": "c", "version": 1,
              "catalog_document_id": CAT_P5}],
    CAT_P6: [{"id": "sp6", "status": "APPROVED_FOR_RUNTIME_USE", "form_name": "c",
              "version": 1, "catalog_document_id": CAT_P6}],
}

_FIELDS_DB = {
    SCHEMA_APPROVED_ID: [
        {"id": "f001", "form_schema_id": SCHEMA_APPROVED_ID,
         "field_key": "site_name", "field_label": "현장명",
         "input_type": "text", "field_order": 1, "required_status": "REQUIRED"},
    ],
}

# ── Fake Supabase (validates document_forms SELECT columns) ───────────────────

class _FakeSingle:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return self


class _FakeResult:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count if count is not None else len(data)

    def execute(self):
        return self


class _FakeQuery:
    def __init__(self, table_name):
        self._table = table_name
        self._filters: dict = {}
        self._in_values: list = []
        self._cols = "*"
        self._eq_filters: list = []

    def select(self, cols="*", **__):
        self._cols = cols
        # Validate that workspace readmodel doesn't request unknown document_forms columns
        if self._table == "document_forms" and cols != "*":
            requested = {c.strip() for c in cols.split(",")}
            unknown = requested - _KNOWN_DOCUMENT_FORMS_COLUMNS
            assert not unknown, (
                f"CORR-01 VIOLATION: document_forms SELECT requested "
                f"non-existent column(s): {unknown}"
            )
        return self

    def eq(self, col, val):
        self._filters[col] = val
        self._eq_filters.append((col, val))
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


# ── CORR-01: Column validation (document_family must NOT be requested) ────────

def test_C1_no_document_family_in_select():
    """Fake validates that workspace SELECT doesn't request document_family."""
    result = list_document_workspace()
    for item in result["items"]:
        assert "document_family" not in item, (
            "CORR-01 FAIL: document_family leaked into workspace item"
        )


def test_C2_catalog_fixture_has_no_document_family():
    for row in _CATALOG_DB.values():
        assert "document_family" not in row, (
            f"Fixture still has document_family: {row['doc_id']}"
        )


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


def test_R3_preparing_doc_returns_preparing():
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

def test_W1_workspace_returns_catalog_rows():
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


def test_W6_availability_filter_only_matching():
    result = list_document_workspace(availability="READY_FOR_EDIT")
    for item in result["items"]:
        assert item["availability"] == "READY_FOR_EDIT"


def test_W7_page_size_in_result():
    result = list_document_workspace(page=1, page_size=10)
    assert result["page_size"] == 10
    assert result["page"] == 1


def test_W8_page_size_capped_at_200():
    result = list_document_workspace(page=1, page_size=9999)
    assert result["page_size"] == 200


# ── CORR-02: Filter-before-pagination test ───────────────────────────────────

def test_W9_filter_before_pagination():
    """Availability filter applies before pagination.

    Fixture includes 3 READY (P3,P4,P6) + 3 PREPARING (P1,P2,P5) across 9 catalog rows.
    With availability=READY_FOR_EDIT, page_size=2:
      total  = 4 (3 pagination fixtures + CAT_ID_APPROVED from base fixtures)
      page 1 = 2 items
      page 2 = 2 items (last being CAT_ID_APPROVED)
    All items on all pages must have availability=READY_FOR_EDIT.
    """
    p1 = list_document_workspace(availability="READY_FOR_EDIT", page=1, page_size=2)
    p2 = list_document_workspace(availability="READY_FOR_EDIT", page=2, page_size=2)

    total = p1["total"]
    assert total == 4, f"CORR-02 FAIL: expected filtered total=4, got {total}"
    assert p1["total"] == p2["total"], "total must be consistent across pages"

    assert len(p1["items"]) == 2
    assert len(p2["items"]) == 2

    for item in p1["items"] + p2["items"]:
        assert item["availability"] == "READY_FOR_EDIT", (
            f"CORR-02 FAIL: non-READY item on page with availability filter: {item['doc_id']}"
        )


def test_W10_filtered_total_consistent():
    """Total reflects filtered count, not raw catalog count."""
    all_result = list_document_workspace()
    ready_result = list_document_workspace(availability="READY_FOR_EDIT")
    preparing_result = list_document_workspace(availability="PREPARING")
    no_schema_result = list_document_workspace(availability="NO_SCHEMA")

    sum_filtered = (
        ready_result["total"] + preparing_result["total"] + no_schema_result["total"]
    )
    assert sum_filtered == all_result["total"], (
        f"CORR-02: sum of availability totals ({sum_filtered}) "
        f"!= unfiltered total ({all_result['total']})"
    )
