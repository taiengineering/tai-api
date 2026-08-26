"""OBJ-01 KNOT-2 — effective list wrapper tests (mocked RPC, no DB)."""
import pytest

from services.inspection_record_resolver import (
    InspectionRecordError,
    list_effective_inspection_records_by_inspector,
)


class _Resp:
    def __init__(self, data):
        self.data = data


class _RPC:
    def __init__(self, data, sink, name, params):
        self._data, self._sink, self._name, self._params = data, sink, name, params

    def execute(self):
        self._sink.append((self._name, self._params))
        return _Resp(self._data)


class FakeSupabase:
    def __init__(self, data):
        self._data = data
        self.calls = []

    def rpc(self, name, params):
        return _RPC(self._data, self.calls, name, params)


def test_returns_list_and_params():
    recs = [{"inspection_id": "i1", "is_active": True, "inspector_id": "u1"}]
    sb = FakeSupabase(recs)
    out = list_effective_inspection_records_by_inspector("u1", 50, supabase=sb)
    assert out == recs
    name, params = sb.calls[0]
    assert name == "fn_list_effective_inspection_records_by_inspector"
    assert params == {"p_inspector_id": "u1", "p_limit": 50}


def test_empty_list():
    sb = FakeSupabase([])
    assert list_effective_inspection_records_by_inspector("u1", 50, supabase=sb) == []


@pytest.mark.parametrize("code", [
    "JOURNAL_REVISION_GAP",
    "LEGACY_STATUS_UNRESOLVED",
    "RESULT_CODE_UNRESOLVED",
    "INSPECTION_NOT_FOUND",
])
def test_fail_closed_on_resolver_error(code):
    sb = FakeSupabase({"error": code, "detail": "x"})
    with pytest.raises(InspectionRecordError) as ei:
        list_effective_inspection_records_by_inspector("u1", 50, supabase=sb)
    assert ei.value.code == code


def test_malformed_response():
    sb = FakeSupabase("nope")
    with pytest.raises(InspectionRecordError) as ei:
        list_effective_inspection_records_by_inspector("u1", 50, supabase=sb)
    assert ei.value.code == "EFFECTIVE_LIST_MALFORMED_RESPONSE"


def test_no_python_folding_or_union_in_source():
    import services.inspection_record_resolver as mod
    from pathlib import Path

    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert "fn_list_effective_inspection_records_by_inspector" in src
    # the wrapper must not fold or union in python
    assert "after_snapshot" not in src
    assert "UNION" not in src
