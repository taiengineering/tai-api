"""
STEP 0 — matching 모듈 현재 동작 스냅샷 (분리 전 기준).
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from routers import matching as m
from schemas.matching import CommissionBody, MatchingRequestBody


def test_status_transitions_received_to_matching_allowed():
    allowed = m.STATUS_TRANSITIONS["RECEIVED"]
    assert "MATCHING" in allowed


def test_status_transitions_received_to_in_progress_not_allowed():
    allowed = m.STATUS_TRANSITIONS["RECEIVED"]
    assert "IN_PROGRESS" not in allowed


def test_matching_request_body_expert_type_valid():
    body = MatchingRequestBody(
        user_id="u1",
        expert_type="EXPERT",
        title="테스트",
    )
    assert body.expert_type == "EXPERT"


def test_matching_request_body_expert_type_invalid():
    with pytest.raises(ValidationError):
        MatchingRequestBody(
            user_id="u1",
            expert_type="INVALID",
            title="테스트",
        )


def test_commission_body_fee_rate_range():
    ok = CommissionBody(service_type="EXPERT", fee_rate=10.0)
    assert ok.fee_rate == 10.0
    with pytest.raises(ValidationError):
        CommissionBody(service_type="EXPERT", fee_rate=0)
    with pytest.raises(ValidationError):
        CommissionBody(service_type="EXPERT", fee_rate=101)


def test_calc_commission_default_ten_percent_when_db_empty():
    supabase = MagicMock()
    supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[]
    )
    out = m.calc_commission(supabase, "EXPERT", 1_000_000, 12)
    assert out["fee_rate"] == 10.0
    assert out["tai_fee_amount"] == 100_000
    assert out["expert_amount"] == 900_000
