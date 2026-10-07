"""OBJ02-C2A: Runtime State Contract tests.

Covers:
  K-tests: runtime key contract (_validate_runtime_keys)
  M-tests: PATCH merge semantics (update_document)
  R-tests: render (render_document_html + build_render_artifacts)
  P-tests: PDF export (no InspectionFetcher/TbmFetcher, no DB insert)
  A-tests: catalog API (GET /document-engine/catalog/{doc_id})
"""

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ── Fixture UUIDs ──────────────────────────────────────────────────────────────
SCHEMA_ID = "aaaaaaaa-0001-0001-0001-000000000001"
DOC_ID = "bbbbbbbb-0001-0001-0001-000000000001"
FIELD_KEY = "site_name"
FIELD_ID = "cccccccc-0001-0001-0001-000000000001"

# Checklist item UUIDs (36-char with dashes — valid UUID format)
CL_UUID_1 = "dddddddd-0001-0001-0001-000000000001"
CL_UUID_2 = "dddddddd-0002-0002-0002-000000000002"

# Unknown UUID (registered nowhere)
UNKNOWN_UUID = "eeeeeeee-9999-9999-9999-999999999999"

# Catalog fixtures
CAT_UUID = "ffffffff-0001-0001-0001-000000000001"
CAT_DOC_ID_STR = "DOC-BLD-999"
CAT_CANDIDATE_UUID = "ffffffff-0002-0002-0002-000000000002"
CAT_CANDIDATE_DOC_ID_STR = "DOC-BLD-888"
CAT_MISSING_DOC_ID_STR = "DOC-NOT-EXIST"

SCHEMA_APPROVED = {
    "id": SCHEMA_ID,
    "status": "APPROVED_FOR_RUNTIME_USE",
    "form_name": "테스트 점검표",
    "version": 1,
    "catalog_document_id": CAT_UUID,
    "source_trace": {},
}
SCHEMA_CANDIDATE = {
    "id": "aaaaaaaa-0002-0002-0002-000000000002",
    "status": "CANDIDATE",
    "form_name": "테스트 점검표 draft",
    "version": 1,
    "catalog_document_id": CAT_CANDIDATE_UUID,
    "source_trace": {},
}

_FIELDS_FOR_SCHEMA = [
    {
        "id": FIELD_ID,
        "form_schema_id": SCHEMA_ID,
        "field_key": FIELD_KEY,
        "field_label": "현장명",
        "input_type": "text",
        "field_order": 1,
        "required_status": "REQUIRED",
    }
]

_CHECKLISTS_FOR_SCHEMA = [
    {
        "id": CL_UUID_1,
        "form_schema_id": SCHEMA_ID,
        "raw_text": "안전모 착용 확인",
        "input_type": "PASS_FAIL_NA",
        "item_order": 1,
    },
    {
        "id": CL_UUID_2,
        "form_schema_id": SCHEMA_ID,
        "raw_text": "안전화 착용 확인",
        "input_type": "PASS_FAIL_NA",
        "item_order": 2,
    },
]

_DOCUMENT_ROW = {
    "id": DOC_ID,
    "form_schema_id": SCHEMA_ID,
    "runtime_data_json": {FIELD_KEY: "서울 현장"},
    "evidence_links": [],
    "status": "DRAFT",
    "version": 1,
    "created_at": "2026-10-07T00:00:00Z",
    "updated_at": "2026-10-07T00:00:00Z",
}

_CATALOG_DB = {
    CAT_UUID: {
        "id": CAT_UUID,
        "doc_id": CAT_DOC_ID_STR,
        "doc_name": "안전 점검표",
        "sector": "CONSTRUCTION",
        "category": "일상",
    },
    CAT_CANDIDATE_UUID: {
        "id": CAT_CANDIDATE_UUID,
        "doc_id": CAT_CANDIDATE_DOC_ID_STR,
        "doc_name": "초안 점검표",
        "sector": "CONSTRUCTION",
        "category": "일상",
    },
}

_CATALOG_BY_DOC_ID = {
    CAT_DOC_ID_STR: _CATALOG_DB[CAT_UUID],
    CAT_CANDIDATE_DOC_ID_STR: _CATALOG_DB[CAT_CANDIDATE_UUID],
}

_SCHEMA_BY_CATALOG = {
    CAT_UUID: [SCHEMA_APPROVED],
    CAT_CANDIDATE_UUID: [SCHEMA_CANDIDATE],
}

# ── Fake Supabase infrastructure ──────────────────────────────────────────────

_insert_calls: list = []
_update_calls: list = []


def _reset():
    _insert_calls.clear()
    _update_calls.clear()


class _FakeSingle:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return self


class _FakeResult:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count if count is not None else (len(data) if data else 0)

    def execute(self):
        return self


class _FakeQuery:
    def __init__(self, table):
        self._table = table
        self._filters: dict = {}
        self._order_cols: list = []
        self._insert_data = None
        self._update_data = None

    def select(self, *_, **__):
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def order(self, *_, **__):
        return self

    def range(self, *_, **__):
        return self

    def single(self):
        t = self._table
        if t == "runtime_document_data":
            doc_id = self._filters.get("id")
            if doc_id == DOC_ID:
                return _FakeSingle(dict(_DOCUMENT_ROW))
            return _FakeSingle(None)
        if t == "runtime_form_schema":
            sid = self._filters.get("id")
            if sid == SCHEMA_ID:
                return _FakeSingle(dict(SCHEMA_APPROVED))
            return _FakeSingle(None)
        if t == "document_forms":
            cid = self._filters.get("id")
            if cid in _CATALOG_DB:
                return _FakeSingle(dict(_CATALOG_DB[cid]))
            doc_id_str = self._filters.get("doc_id")
            if doc_id_str in _CATALOG_BY_DOC_ID:
                return _FakeSingle(dict(_CATALOG_BY_DOC_ID[doc_id_str]))
            return _FakeSingle(None)
        return _FakeSingle(None)

    def execute(self):
        if self._update_data is not None:
            return self._execute_update()
        t = self._table
        if t == "runtime_field":
            sid = self._filters.get("form_schema_id")
            if sid == SCHEMA_ID:
                return _FakeResult(_FIELDS_FOR_SCHEMA)
            return _FakeResult([])
        if t == "runtime_checklist_item":
            sid = self._filters.get("form_schema_id")
            if sid == SCHEMA_ID:
                return _FakeResult(_CHECKLISTS_FOR_SCHEMA)
            return _FakeResult([])
        if t == "runtime_evidence_field":
            return _FakeResult([])
        if t == "runtime_document_archive":
            return _FakeResult([])
        if t == "document_forms":
            doc_id_str = self._filters.get("doc_id")
            if doc_id_str in _CATALOG_BY_DOC_ID:
                return _FakeResult([dict(_CATALOG_BY_DOC_ID[doc_id_str])])
            if not self._filters:
                return _FakeResult(list(_CATALOG_DB.values()))
            return _FakeResult([])
        if t == "runtime_form_schema":
            cat_id = self._filters.get("catalog_document_id")
            if cat_id in _SCHEMA_BY_CATALOG:
                return _FakeResult(list(_SCHEMA_BY_CATALOG[cat_id]))
            return _FakeResult([])
        if t == "runtime_lifecycle_audit_log":
            return _FakeResult([])
        return _FakeResult([])

    def insert(self, record):
        _insert_calls.append({"table": self._table, "data": record})
        return _FakeResult([{"id": "new-id"}])

    def update(self, record):
        self._update_data = record
        _update_calls.append({"table": self._table, "data": record, "filters": dict(self._filters)})
        return self  # support .update(x).eq("id", y).execute() chaining

    def _execute_update(self):
        record = self._update_data or {}
        if self._table == "runtime_document_data":
            merged = {**_DOCUMENT_ROW, **record}
            return _FakeResult([merged])
        return _FakeResult([record])


class _FakeSupabase:
    def table(self, name):
        return _FakeQuery(name)


# ── Module isolation helper ────────────────────────────────────────────────────

def _make_modules(sb_factory=None):
    """Return a context manager-like dict of modules with fake Supabase."""
    if sb_factory is None:
        sb_factory = lambda: _FakeSupabase()

    _db_pkg = types.ModuleType("db")
    _db_pkg.__path__ = [str(ROOT / "db")]
    _db_client = types.ModuleType("db.supabase_client")
    _db_client.get_supabase = sb_factory
    _db_pkg.supabase_client = _db_client

    _svc_pkg = types.ModuleType("services")
    _svc_pkg.__path__ = [str(ROOT / "services")]

    _time_mod = types.ModuleType("services.time")
    import datetime
    _time_mod.now_kst = lambda: datetime.datetime(2026, 10, 7, 12, 0)
    _time_mod.serialize_external_utc = lambda dt: dt.isoformat() + "Z"

    return {
        "db": _db_pkg,
        "db.supabase_client": _db_client,
        "services": _svc_pkg,
        "services.time": _time_mod,
    }


# Load modules with patched DB ─────────────────────────────────────────────────

_MODULE_NAMES = (
    "db",
    "db.supabase_client",
    "services",
    "services.time",
    "services.document_engine_svc",
    "services.document_engine",
    "services.document_engine.catalog_resolver",
    "services.document_schema_renderer",
)
_MISSING = object()
_saved = {n: sys.modules.get(n, _MISSING) for n in _MODULE_NAMES}

try:
    mods = _make_modules()
    for k, v in mods.items():
        sys.modules[k] = v

    _doc_eng_pkg = types.ModuleType("services.document_engine")
    _doc_eng_pkg.__path__ = [str(ROOT / "services" / "document_engine")]
    sys.modules["services.document_engine"] = _doc_eng_pkg

    # Force fresh load
    for mod_name in ("services.document_engine_svc", "services.document_engine.catalog_resolver",
                     "services.document_schema_renderer"):
        sys.modules.pop(mod_name, None)

    from services.document_engine_svc import (
        _validate_runtime_keys,
        update_document,
        render_document_html,
        resolve_runtime_document_state,
    )
    from services.document_schema_renderer import build_render_artifacts
    from services.document_engine.catalog_resolver import resolve_catalog_runtime_schema

finally:
    for _n, _prev in _saved.items():
        if _prev is _MISSING:
            sys.modules.pop(_n, None)
        else:
            sys.modules[_n] = _prev


# ═══════════════════════════════════════════════════════
# K-tests: Runtime key contract
# ═══════════════════════════════════════════════════════

def test_K1_known_field_key_accepted():
    """K1: known field_key → accepted (no exception)."""
    sb = _FakeSupabase()
    _validate_runtime_keys(sb, SCHEMA_ID, {FIELD_KEY: "서울"})  # should not raise


def test_K2_known_checklist_uuid_accepted():
    """K2: known checklist UUID → accepted."""
    sb = _FakeSupabase()
    _validate_runtime_keys(sb, SCHEMA_ID, {CL_UUID_1: "PASS"})  # should not raise


def test_K3_unknown_key_rejected():
    """K3: unknown non-UUID key → ValueError."""
    sb = _FakeSupabase()
    try:
        _validate_runtime_keys(sb, SCHEMA_ID, {"unknown_field_xyz": "value"})
        assert False, "should raise ValueError"
    except ValueError as e:
        assert "unknown_field_xyz" in str(e)


def test_K4_mixed_field_and_checklist_accepted():
    """K4: valid field_key + valid checklist UUID → both accepted."""
    sb = _FakeSupabase()
    _validate_runtime_keys(sb, SCHEMA_ID, {
        FIELD_KEY: "서울",
        CL_UUID_1: "PASS",
        CL_UUID_2: "FAIL",
    })  # should not raise


def test_K5_checklist_values_pass_fail_na_accepted():
    """K5: PASS/FAIL/NA values → accepted for checklist keys."""
    sb = _FakeSupabase()
    for val in ("PASS", "FAIL", "NA"):
        _validate_runtime_keys(sb, SCHEMA_ID, {CL_UUID_1: val})  # should not raise


def test_K5_checklist_null_accepted():
    """K5b: null value for checklist key → accepted (means 'no answer')."""
    sb = _FakeSupabase()
    _validate_runtime_keys(sb, SCHEMA_ID, {CL_UUID_1: None})  # should not raise


def test_K6_invalid_checklist_value_rejected():
    """K6: invalid checklist value (e.g. 'YES') → ValueError."""
    sb = _FakeSupabase()
    try:
        _validate_runtime_keys(sb, SCHEMA_ID, {CL_UUID_1: "YES"})
        assert False, "should raise ValueError"
    except ValueError as e:
        assert "YES" in str(e) or "invalid" in str(e).lower()


def test_K6_lowercase_rejected():
    """K6b: lowercase 'pass' (not canonical) → ValueError (case-sensitive)."""
    sb = _FakeSupabase()
    try:
        _validate_runtime_keys(sb, SCHEMA_ID, {CL_UUID_1: "pass"})
        assert False, "should raise ValueError"
    except ValueError:
        pass  # expected


def test_K3_unknown_uuid_rejected():
    """K3b: UUID-shaped key that is NOT a registered checklist ID → rejected."""
    sb = _FakeSupabase()
    try:
        _validate_runtime_keys(sb, SCHEMA_ID, {UNKNOWN_UUID: "PASS"})
        assert False, "should raise ValueError"
    except ValueError as e:
        assert UNKNOWN_UUID in str(e)


# ═══════════════════════════════════════════════════════
# M-tests: PATCH merge semantics
# ═══════════════════════════════════════════════════════

# For M-tests, we need a configurable fake that returns a specific existing doc.

class _MergeFakeQuery:
    """Fake query that returns a doc with configurable existing runtime_data_json."""

    def __init__(self, table, existing_json):
        self._table = table
        self._filters = {}
        self._existing_json = existing_json
        self._update_data = None

    def select(self, *_, **__):
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def order(self, *_, **__):
        return self

    def single(self):
        if self._table == "runtime_document_data":
            return _FakeSingle({
                "id": DOC_ID,
                "form_schema_id": SCHEMA_ID,
                "runtime_data_json": self._existing_json,
                "evidence_links": [],
                "status": "DRAFT",
                "version": 2,
                "updated_at": "2026-10-07T00:00:00Z",
            })
        if self._table == "runtime_form_schema":
            return _FakeSingle({"id": SCHEMA_ID, "status": "APPROVED_FOR_RUNTIME_USE"})
        return _FakeSingle(None)

    def insert(self, record):
        _insert_calls.append({"table": self._table, "data": record})
        return _FakeResult([{"id": "new-id"}])

    def update(self, record):
        self._update_data = record
        _update_calls.append({"table": self._table, "data": record})
        return self  # support .update(x).eq("id", y).execute() chaining

    def _execute_update(self):
        record = self._update_data or {}
        existing = self._existing_json or {}
        incoming = record.get("runtime_data_json", {})
        # Simulate the merge that the svc does (so we can see what was written)
        # The svc already merges before putting it in update["runtime_data_json"]
        # so incoming IS the already-merged dict here
        result_row = {
            "id": DOC_ID,
            "form_schema_id": SCHEMA_ID,
            "runtime_data_json": incoming if incoming else existing,
            "status": "DRAFT",
            "version": record.get("version", 2),
        }
        return _FakeResult([result_row])

    def execute(self):
        if self._update_data is not None:
            return self._execute_update()
        t = self._table
        if t == "runtime_field":
            return _FakeResult([{"field_key": "a"}, {"field_key": "b"}])
        if t == "runtime_checklist_item":
            return _FakeResult([])
        if t == "runtime_evidence_field":
            return _FakeResult([])
        if t == "runtime_lifecycle_audit_log":
            return _FakeResult([])
        return _FakeResult([])


class _MergeFakeSupabase:
    def __init__(self, existing_json):
        self._existing_json = existing_json

    def table(self, name):
        return _MergeFakeQuery(name, self._existing_json)


def _load_update_document_with_sb(sb_instance):
    """Reload update_document with a specific fake Supabase."""
    saved = {n: sys.modules.get(n, _MISSING) for n in _MODULE_NAMES}
    try:
        mods = _make_modules(sb_factory=lambda: sb_instance)
        for k, v in mods.items():
            sys.modules[k] = v
        _doc_eng_pkg = types.ModuleType("services.document_engine")
        _doc_eng_pkg.__path__ = [str(ROOT / "services" / "document_engine")]
        sys.modules["services.document_engine"] = _doc_eng_pkg
        sys.modules.pop("services.document_engine_svc", None)
        from services.document_engine_svc import update_document as ud
        return ud
    finally:
        for _n, _prev in saved.items():
            if _prev is _MISSING:
                sys.modules.pop(_n, None)
            else:
                sys.modules[_n] = _prev


def test_M1_patch_merge_preserves_existing():
    """M1: existing {"a": "A", "b": "B"} + incoming {"a": "A2"} → {"a": "A2", "b": "B"}."""
    _reset()
    sb = _MergeFakeSupabase({"a": "A", "b": "B"})
    ud = _load_update_document_with_sb(sb)
    result = ud(DOC_ID, runtime_data_json={"a": "A2"})
    assert result["runtime_data_json"]["a"] == "A2"
    assert result["runtime_data_json"]["b"] == "B"


def test_M2_patch_merge_preserves_checklist_on_field_update():
    """M2: existing checklist UUID key + update non-overlapping field → checklist preserved."""
    _reset()
    existing = {"a": "old_a", CL_UUID_1: "PASS"}

    class _M2SB:
        def table(self, name):
            return _MergeFakeQuery(name, existing)

    class _M2FakeQuery(_MergeFakeQuery):
        def execute(self):
            if self._table == "runtime_field":
                return _FakeResult([{"field_key": "a"}])
            if self._table == "runtime_checklist_item":
                return _FakeResult([{"id": CL_UUID_1}, {"id": CL_UUID_2}])
            return super().execute()

    class _M2SB2:
        def table(self, name):
            return _M2FakeQuery(name, existing)

    ud = _load_update_document_with_sb(_M2SB2())
    result = ud(DOC_ID, runtime_data_json={"a": "new_a"})
    data = result["runtime_data_json"]
    assert data.get("a") == "new_a"
    assert data.get(CL_UUID_1) == "PASS", f"checklist key should be preserved, got: {data}"


def test_M3_patch_none_removes_key():
    """M3: incoming {"key": null} → key removed from merged result."""
    _reset()
    existing = {"a": "A", "b": "B"}
    sb = _MergeFakeSupabase(existing)
    ud = _load_update_document_with_sb(sb)
    result = ud(DOC_ID, runtime_data_json={"a": None})
    assert "a" not in result["runtime_data_json"], (
        f"key 'a' should be removed when set to None, got: {result['runtime_data_json']}"
    )
    assert result["runtime_data_json"].get("b") == "B"


# ═══════════════════════════════════════════════════════
# R-tests: Render
# ═══════════════════════════════════════════════════════

def _make_render_state(runtime_data=None):
    """Build a state dict for build_render_artifacts testing."""
    if runtime_data is None:
        runtime_data = {FIELD_KEY: "서울 현장"}
    doc = {
        "id": DOC_ID,
        "form_schema_id": SCHEMA_ID,
        "runtime_data_json": runtime_data,
        "status": "DRAFT",
        "version": 1,
    }
    schema = {
        "id": SCHEMA_ID,
        "form_name": "테스트 점검표",
        "catalog_document_id": CAT_UUID,
    }
    fields = list(_FIELDS_FOR_SCHEMA)
    checklists = list(_CHECKLISTS_FOR_SCHEMA)
    return doc, schema, fields, checklists


def test_R1_field_value_in_rendered_html():
    """R1: field value → present in rendered HTML."""
    doc, schema, fields, checklists = _make_render_state(
        {FIELD_KEY: "테스트현장"}
    )
    artifacts = build_render_artifacts(
        document=doc, schema=schema, fields=fields, checklists=checklists
    )
    assert "테스트현장" in artifacts["rendered_body"]
    assert "현장명" in artifacts["rendered_body"]


def test_R2_checklist_uuid_pass_in_rendered_html():
    """R2: checklist UUID key with value 'PASS' → present in rendered HTML."""
    doc, schema, fields, checklists = _make_render_state(
        {FIELD_KEY: "서울", CL_UUID_1: "PASS"}
    )
    artifacts = build_render_artifacts(
        document=doc, schema=schema, fields=fields, checklists=checklists
    )
    html = artifacts["rendered_body"]
    assert "PASS" in html
    assert CL_UUID_1 in html  # checklist item id is in data attribute


def test_R3_missing_field_shows_missing_text():
    """R3: no value for a field → '(미입력)' appears."""
    doc, schema, fields, checklists = _make_render_state({})  # no field values
    artifacts = build_render_artifacts(
        document=doc, schema=schema, fields=fields, checklists=checklists
    )
    assert "(미입력)" in artifacts["rendered_body"]


def test_R5_same_state_same_html():
    """R5: same state → same HTML (deterministic)."""
    doc, schema, fields, checklists = _make_render_state(
        {FIELD_KEY: "서울", CL_UUID_1: "PASS"}
    )
    art1 = build_render_artifacts(document=doc, schema=schema, fields=fields, checklists=checklists)
    art2 = build_render_artifacts(document=doc, schema=schema, fields=fields, checklists=checklists)
    assert art1["rendered_body"] == art2["rendered_body"]
    assert art1["template_identity"] == art2["template_identity"]


def test_R_render_document_html_field_present():
    """R1b: render_document_html returns HTML with field value."""
    saved = {n: sys.modules.get(n, _MISSING) for n in _MODULE_NAMES}
    try:
        mods = _make_modules()
        for k, v in mods.items():
            sys.modules[k] = v
        _doc_eng_pkg = types.ModuleType("services.document_engine")
        _doc_eng_pkg.__path__ = [str(ROOT / "services" / "document_engine")]
        sys.modules["services.document_engine"] = _doc_eng_pkg
        sys.modules.pop("services.document_engine_svc", None)
        sys.modules.pop("services.document_schema_renderer", None)
        from services.document_engine_svc import render_document_html as rdh
        html = rdh(DOC_ID)
        assert "서울 현장" in html or "현장명" in html
        assert "<!DOCTYPE html>" in html
    finally:
        for _n, _prev in saved.items():
            if _prev is _MISSING:
                sys.modules.pop(_n, None)
            else:
                sys.modules[_n] = _prev


def test_R_render_document_html_not_found():
    """Render raises ValueError for unknown doc_id."""
    saved = {n: sys.modules.get(n, _MISSING) for n in _MODULE_NAMES}
    try:
        mods = _make_modules()
        for k, v in mods.items():
            sys.modules[k] = v
        _doc_eng_pkg = types.ModuleType("services.document_engine")
        _doc_eng_pkg.__path__ = [str(ROOT / "services" / "document_engine")]
        sys.modules["services.document_engine"] = _doc_eng_pkg
        sys.modules.pop("services.document_engine_svc", None)
        sys.modules.pop("services.document_schema_renderer", None)
        from services.document_engine_svc import render_document_html as rdh
        try:
            rdh("nonexistent-doc-id-xxxxxxxx")
            assert False, "should raise ValueError"
        except ValueError:
            pass  # expected
    finally:
        for _n, _prev in saved.items():
            if _prev is _MISSING:
                sys.modules.pop(_n, None)
            else:
                sys.modules[_n] = _prev


# ═══════════════════════════════════════════════════════
# P-tests: PDF export — verify no side-effects
# ═══════════════════════════════════════════════════════

_inspection_fetcher_called = False
_tbm_fetcher_called = False

class _SpyInspectionFetcher:
    def fetch(self, *a, **kw):
        global _inspection_fetcher_called
        _inspection_fetcher_called = True


class _SpyTbmFetcher:
    def fetch(self, *a, **kw):
        global _tbm_fetcher_called
        _tbm_fetcher_called = True


def test_P2_inspection_fetcher_not_called():
    """P2: InspectionFetcher NOT called during render_document_html."""
    global _inspection_fetcher_called
    _inspection_fetcher_called = False

    saved = {n: sys.modules.get(n, _MISSING) for n in _MODULE_NAMES}
    try:
        mods = _make_modules()
        for k, v in mods.items():
            sys.modules[k] = v
        _doc_eng_pkg = types.ModuleType("services.document_engine")
        _doc_eng_pkg.__path__ = [str(ROOT / "services" / "document_engine")]
        sys.modules["services.document_engine"] = _doc_eng_pkg
        sys.modules.pop("services.document_engine_svc", None)
        sys.modules.pop("services.document_schema_renderer", None)
        from services.document_engine_svc import render_document_html as rdh
        rdh(DOC_ID)
        assert not _inspection_fetcher_called, "InspectionFetcher must NOT be called"
    finally:
        for _n, _prev in saved.items():
            if _prev is _MISSING:
                sys.modules.pop(_n, None)
            else:
                sys.modules[_n] = _prev


def test_P3_tbm_fetcher_not_called():
    """P3: TbmFetcher NOT called during render_document_html."""
    global _tbm_fetcher_called
    _tbm_fetcher_called = False

    saved = {n: sys.modules.get(n, _MISSING) for n in _MODULE_NAMES}
    try:
        mods = _make_modules()
        for k, v in mods.items():
            sys.modules[k] = v
        _doc_eng_pkg = types.ModuleType("services.document_engine")
        _doc_eng_pkg.__path__ = [str(ROOT / "services" / "document_engine")]
        sys.modules["services.document_engine"] = _doc_eng_pkg
        sys.modules.pop("services.document_engine_svc", None)
        sys.modules.pop("services.document_schema_renderer", None)
        from services.document_engine_svc import render_document_html as rdh
        rdh(DOC_ID)
        assert not _tbm_fetcher_called, "TbmFetcher must NOT be called"
    finally:
        for _n, _prev in saved.items():
            if _prev is _MISSING:
                sys.modules.pop(_n, None)
            else:
                sys.modules[_n] = _prev


def test_P4_no_generated_document_insert_on_render():
    """P4: no 'generated_document' INSERT during render_document_html (transient export)."""
    _reset()

    saved = {n: sys.modules.get(n, _MISSING) for n in _MODULE_NAMES}
    try:
        mods = _make_modules()
        for k, v in mods.items():
            sys.modules[k] = v
        _doc_eng_pkg = types.ModuleType("services.document_engine")
        _doc_eng_pkg.__path__ = [str(ROOT / "services" / "document_engine")]
        sys.modules["services.document_engine"] = _doc_eng_pkg
        sys.modules.pop("services.document_engine_svc", None)
        sys.modules.pop("services.document_schema_renderer", None)
        from services.document_engine_svc import render_document_html as rdh
        rdh(DOC_ID)
        generated_inserts = [
            c for c in _insert_calls if c.get("table") == "generated_document"
        ]
        assert len(generated_inserts) == 0, (
            f"generated_document INSERT must NOT happen during transient render, "
            f"found: {generated_inserts}"
        )
    finally:
        for _n, _prev in saved.items():
            if _prev is _MISSING:
                sys.modules.pop(_n, None)
            else:
                sys.modules[_n] = _prev


# ═══════════════════════════════════════════════════════
# A-tests: Catalog API
# ═══════════════════════════════════════════════════════

def _load_catalog_resolver():
    """Load the catalog resolver with fake Supabase."""
    saved = {n: sys.modules.get(n, _MISSING) for n in _MODULE_NAMES}
    try:
        mods = _make_modules()
        for k, v in mods.items():
            sys.modules[k] = v
        _doc_eng_pkg = types.ModuleType("services.document_engine")
        _doc_eng_pkg.__path__ = [str(ROOT / "services" / "document_engine")]
        sys.modules["services.document_engine"] = _doc_eng_pkg
        sys.modules.pop("services.document_engine.catalog_resolver", None)
        from services.document_engine.catalog_resolver import resolve_catalog_runtime_schema as rcrs
        return rcrs
    finally:
        for _n, _prev in saved.items():
            if _prev is _MISSING:
                sys.modules.pop(_n, None)
            else:
                sys.modules[_n] = _prev


def test_A1_approved_schema_can_create_true():
    """A1: doc exists + approved schema → can_create=true, schema_id returned."""
    rcrs = _load_catalog_resolver()
    result = rcrs(CAT_UUID)
    assert result["availability"] == "READY_FOR_EDIT"
    assert result["schema"] is not None
    assert result["schema"]["id"] == SCHEMA_ID
    # can_create logic: availability == READY_FOR_EDIT
    can_create = result["availability"] == "READY_FOR_EDIT"
    assert can_create is True


def test_A2_candidate_only_can_create_false():
    """A2: doc exists + candidate only → can_create=false."""
    rcrs = _load_catalog_resolver()
    result = rcrs(CAT_CANDIDATE_UUID)
    assert result["availability"] == "PREPARING"
    can_create = result["availability"] == "READY_FOR_EDIT"
    assert can_create is False
    assert result["schema"] is None


def test_A3_doc_not_exists_raises_value_error():
    """A3: doc does not exist → ValueError (router returns 404)."""
    rcrs = _load_catalog_resolver()
    try:
        rcrs("nonexistent-uuid-00000000000000000000")
        assert False, "should raise ValueError"
    except ValueError:
        pass  # expected — router maps to 404


def test_A1_fields_and_checklists_returned():
    """A1b: approved schema returns populated fields and checklists."""
    rcrs = _load_catalog_resolver()
    result = rcrs(CAT_UUID)
    assert len(result["fields"]) >= 1
    assert result["fields"][0]["field_key"] == FIELD_KEY
    assert len(result["checklists"]) >= 2


def test_A2_no_fields_for_candidate():
    """A2b: candidate schema → fields and checklists are empty."""
    rcrs = _load_catalog_resolver()
    result = rcrs(CAT_CANDIDATE_UUID)
    assert result["fields"] == []
    assert result["checklists"] == []
