"""WO-TAI-SLACK-RELAY-RECOVERY-GATE-001 — DIRECT 핸들러 테스트.
RRH-001: direct://slack_relay_recovery 가 DIRECT_HANDLERS에 등록됐는지 확인
RRH-002: _run_slack_relay_recovery({}) 가 AsyncMock 반환값을 {"processed": N} 으로 감싸고
         run_relay_recovery_once()를 정확히 1회 호출하는지 확인
"""
from unittest.mock import AsyncMock, patch


def test_rrh_001_handler_registered():
    from services.scheduler.handlers import DIRECT_HANDLERS, register_direct_handlers
    register_direct_handlers()
    assert "direct://slack_relay_recovery" in DIRECT_HANDLERS


def test_rrh_002_handler_calls_recovery_and_returns_processed():
    from services.scheduler.handlers import _run_slack_relay_recovery
    mock_recovery = AsyncMock(return_value=3)
    with patch(
        "services.slack_relay_svc.run_relay_recovery_once",
        mock_recovery,
    ):
        result = _run_slack_relay_recovery({})
    assert result == {"processed": 3}
    mock_recovery.assert_called_once()
