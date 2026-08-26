"""OBJ-01 STEP-1A — Resolver wrapper tests (mocked RPC, no DB)."""
import pytest

from services.inspection_record_resolver import (
    InspectionRecordError,
    resolve_inspection_record,
)


class _Resp:
    def __init__(self, data):
        self.data = data


class _RPC:
    def __init__(self, data):
        self._data = data

    def execute(self):
        return _Resp(self._data)


class FakeSupabase:
    def __init__(self, data):
        self._data = data
        self.calls = []

    def rpc(self, name, params):
        self.calls.append((name, params))
        return _RPC(self._data)


_RECORD = {
    "inspection_id": "11111111-1111-1111-1111-111111111111",
    "revision": 0,
    "is_active": True,
    "inspection_status": "COMPLETED",
    "results": [],
    "overall_result": None,
}


def test_success_returns_record():
    sb = FakeSupabase(_RECORD)
    out = resolve_inspection_record("iid", supabase=sb)
    assert out["inspection_status"] == "COMPLETED"
    assert sb.calls[0][0] == "fn_resolve_inspection_record"
    assert sb.calls[0][1] == {"p_inspection_id": "iid"}


@pytest.mark.parametrize("code", [
    "INSPECTION_NOT_FOUND",
    "LEGACY_STATUS_UNRESOLVED",
    "RESULT_CODE_UNRESOLVED",
    "JOURNAL_REVISION_GAP",
])
def test_resolver_domain_errors(code):
    sb = FakeSupabase({"error": code, "detail": "x"})
    with pytest.raises(InspectionRecordError) as ei:
        resolve_inspection_record("iid", supabase=sb)
    assert ei.value.code == code


def test_malformed_response():
    sb = FakeSupabase(["not", "a", "dict"])
    with pytest.raises(InspectionRecordError) as ei:
        resolve_inspection_record("iid", supabase=sb)
    assert ei.value.code == "RESOLVER_MALFORMED_RESPONSE"


def test_no_python_folding_in_source():
    """Python 측 folding 금지: resolver 는 DB rpc 만 호출하고 after_snapshot 을 직접 다루지 않는다."""
    import services.inspection_record_resolver as mod
    from pathlib import Path

    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert 'rpc(' in src and 'fn_resolve_inspection_record' in src
    assert "after_snapshot" not in src
    assert "jsonb" not in src  # no snapshot manipulation in python
