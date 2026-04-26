"""payment_svc 단위 테스트 (STEP 5)."""

from unittest.mock import MagicMock, patch

import pytest

from schemas.payment import PrepareBody
from services.payment_svc import PaymentPrepareError, run_inicis_prepare


def test_run_inicis_prepare_requires_period_for_saas():
    body = PrepareBody(
        user_id="u1",
        product_type="SAAS_BUILDING",
        amount=59000,
        goodname="테스트",
    )
    with pytest.raises(PaymentPrepareError) as ei:
        run_inicis_prepare(body)
    assert ei.value.status_code == 400


@patch("services.payment_svc.get_supabase")
def test_run_inicis_prepare_success_minimal(mock_get_sb):
    mock_row = MagicMock()
    mock_row.execute.return_value = MagicMock(data=[{"id": "pay-uuid-1"}])
    mock_get_sb.return_value.table.return_value.insert.return_value = mock_row

    body = PrepareBody(
        user_id="u1",
        product_type="DIAGNOSIS",
        amount=10000,
        goodname="진단",
    )
    out = run_inicis_prepare(body)
    assert out["status"] == "success"
    assert out["data"]["payment_id"] == "pay-uuid-1"
    assert "oid" in out["data"]
    assert out["data"]["gopaymethod"] == "Card"
