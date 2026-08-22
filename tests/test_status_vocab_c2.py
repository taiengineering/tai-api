"""C-2 status_vocab 단위 테스트."""
from services.status_vocab import (
    is_ptw_pending_approval,
    is_wa_done,
    is_ws_completed,
    normalize_inspection_result_write,
    normalize_site_status_read,
    ptw_filter_query_values,
    site_status_filter_query_values,
    wa_write_ready,
    ws_write_completed,
)


def test_ws_completed_read_compat():
    assert is_ws_completed("completed")
    assert is_ws_completed("DONE")
    assert is_ws_completed("done")
    assert not is_ws_completed("scheduled")
    assert not is_ws_completed("SCHEDULED")


def test_ws_write_canonical():
    assert ws_write_completed() == "completed"


def test_ptw_pending_approval():
    assert is_ptw_pending_approval("REQUESTED")
    assert is_ptw_pending_approval("PENDING")
    assert not is_ptw_pending_approval("DRAFT")
    assert not is_ptw_pending_approval("APPROVED")
    assert ptw_filter_query_values("PENDING") == ["REQUESTED", "PENDING"]


def test_site_status_active_compat():
    assert normalize_site_status_read("ACTIVE") == "IN_PROGRESS"
    assert site_status_filter_query_values("IN_PROGRESS") == ["IN_PROGRESS", "ACTIVE"]


def test_inspection_result_hold():
    assert normalize_inspection_result_write("ok") == "NORMAL"
    assert normalize_inspection_result_write("PASS") == "NORMAL"
    assert normalize_inspection_result_write("hold") == "HOLD"
    assert normalize_inspection_result_write("bad") == "ABNORMAL"


def test_wa_done_and_ready():
    assert is_wa_done("DONE")
    assert is_wa_done("done")
    assert is_wa_done("COMPLETED")
    assert not is_wa_done("READY")
    assert wa_write_ready() == "READY"
