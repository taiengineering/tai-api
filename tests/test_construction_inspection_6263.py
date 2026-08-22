"""§62·§63 건설점검 — inspector_id 저장·요약 집계."""
from services import construction_svc
from services.construction_svc import inspection_result_summary, inspector_name_map


def test_inspection_result_summary_includes_issue(monkeypatch):
    def fake_count(_sb, _table, filters):
        result = filters.get("overall_result")
        if result == "PASS":
            return 5
        if result == "ISSUE":
            return 2
        if result == "FAIL":
            return 1
        if filters.get("corrective_status") == "IN_PROGRESS":
            return 0
        return 8

    monkeypatch.setattr(construction_svc, "count_table_rows", fake_count)
    summary = inspection_result_summary(None, {"site_id": "site-1", "is_active": True})
    assert summary["total"] == 8
    assert summary["pass"] == 5
    assert summary["issue"] == 2
    assert summary["fail"] == 1
    assert summary["pass"] + summary["issue"] + summary["fail"] == summary["total"]


class _UsersQuery:
    def __init__(self, data):
        self._data = data

    def select(self, *args, **kwargs):
        return self

    def in_(self, *args, **kwargs):
        return self

    def execute(self):
        from types import SimpleNamespace
        return SimpleNamespace(data=self._data)


class _FakeSupabaseUsers:
    def table(self, name):
        assert name == "users"
        return _UsersQuery([{"id": "u1", "name": "김태형"}])


def test_inspector_name_map():
    sb = _FakeSupabaseUsers()
    assert inspector_name_map(sb, ["u1", "u1", None]) == {"u1": "김태형"}


def test_alias_inspection_row_inspector_name():
    from routers.construction_workflow_router import _alias_inspection_row

    row = {"inspector_id": "u1", "inspection_date": "2026-08-22T10:00:00"}
    out = _alias_inspection_row(row, {"u1": "김태형"})
    assert out["inspector_name"] == "김태형"
    assert out["inspection_datetime"] == "2026-08-22T10:00:00"
