"""OBJ-01 STEP-1A — Command service tests (mocked RPC, no DB)."""
import pytest

from services import inspection_record_commands as cmd
from services.inspection_record_resolver import InspectionRecordError


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


def _ok():
    return {"ok": True, "data": {"inspection_id": "i", "revision": 1, "event_id": "e", "command_id": "c"}}


def test_correct_inspection_params():
    sb = FakeSupabase(_ok())
    out = cmd.correct_inspection(
        sb, "iid", expected_revision=0, command_id="cid",
        changes={"inspection_date": "2026-01-01"}, actor_id="u1", reason="r",
    )
    assert out["revision"] == 1
    name, p = sb.calls[0]
    assert name == "fn_apply_inspection_record_command"
    assert p["p_event_type"] == "INSPECTION_CORRECTION"
    assert p["p_target_result_id"] is None
    assert p["p_actor_type"] == "USER"       # server-derived
    assert p["p_source"] == "SAFE_ADMIN"     # server-derived
    assert p["p_actor_id"] == "u1"
    assert p["p_changes"] == {"inspection_date": "2026-01-01"}


def test_correct_result_target():
    sb = FakeSupabase(_ok())
    cmd.correct_result(
        sb, "iid", "rid", expected_revision=0, command_id="cid",
        changes={"result_code": "ABNORMAL"}, actor_id="u1",
    )
    _, p = sb.calls[0]
    assert p["p_event_type"] == "RESULT_CORRECTION"
    assert p["p_target_result_id"] == "rid"


def test_change_status_builds_to_status():
    sb = FakeSupabase(_ok())
    cmd.change_status(sb, "iid", expected_revision=0, command_id="cid", to_status="COMPLETED", actor_id="u1")
    _, p = sb.calls[0]
    assert p["p_event_type"] == "STATUS_CHANGE"
    assert p["p_changes"] == {"to_status": "COMPLETED"}


def test_deactivate_inspection_event():
    sb = FakeSupabase(_ok())
    cmd.deactivate_inspection(sb, "iid", expected_revision=0, command_id="cid", actor_id="u1")
    _, p = sb.calls[0]
    assert p["p_event_type"] == "INSPECTION_DEACTIVATION"
    assert p["p_target_result_id"] is None
    assert p["p_changes"] == {}


def test_deactivate_result_event():
    sb = FakeSupabase(_ok())
    cmd.deactivate_result(sb, "iid", "rid", expected_revision=0, command_id="cid", actor_id="u1")
    _, p = sb.calls[0]
    assert p["p_event_type"] == "RESULT_DEACTIVATION"
    assert p["p_target_result_id"] == "rid"


@pytest.mark.parametrize("code", sorted(cmd.KNOWN_DOMAIN_ERRORS))
def test_known_error_mapping(code):
    sb = FakeSupabase({"ok": False, "error": code, "detail": "d"})
    with pytest.raises(InspectionRecordError) as ei:
        cmd.deactivate_inspection(sb, "iid", expected_revision=0, command_id="cid", actor_id="u1")
    assert ei.value.code == code


def test_malformed_response():
    sb = FakeSupabase("nope")
    with pytest.raises(InspectionRecordError) as ei:
        cmd.deactivate_inspection(sb, "iid", expected_revision=0, command_id="cid", actor_id="u1")
    assert ei.value.code == "COMMAND_MALFORMED_RESPONSE"


def test_no_forbidden_patterns_in_source():
    """command service 는 MAX(revision)/direct insert/base update 를 하지 않는다."""
    from pathlib import Path
    src = Path(cmd.__file__).read_text(encoding="utf-8")
    assert "max(" not in src.lower() or "revision" not in src.lower() or "select" not in src.lower()
    assert ".insert(" not in src
    assert ".update(" not in src
    assert ".delete(" not in src
