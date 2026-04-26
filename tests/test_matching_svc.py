"""services.matching_svc 패키지 단위 테스트."""
from __future__ import annotations

from unittest.mock import MagicMock

from services.matching_svc import MatchingSvcError, calc_commission


def test_matching_svc_error_fields():
    e = MatchingSvcError(404, "x")
    assert e.status_code == 404
    assert e.detail == "x"


def test_calc_commission_uses_row_when_present():
    supabase = MagicMock()
    supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{"fee_rate": 15.0}]
    )
    out = calc_commission(supabase, "EXPERT", 200_000, 6)
    assert out["fee_rate"] == 15.0
    assert out["tai_fee_amount"] == 30_000
    assert out["expert_amount"] == 170_000
