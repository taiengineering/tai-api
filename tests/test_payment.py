from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from schemas.payment import BillingPrepareBody
from services.payment_svc import PaymentPrepareError, run_billing_charge, run_billing_prepare


@patch.dict(
    "os.environ",
    {
        "INICIS_BILLING_MID": "mid-test",
        "INICIS_BILLING_SIGN_KEY": "sign-test",
        "INICIS_BILLING_API_URL": "https://api.example.com/billing",
    },
    clear=False,
)
@patch("services.payment_svc.get_supabase")
def test_run_billing_prepare_success(mock_get_supabase):
    mock_insert = MagicMock()
    mock_insert.execute.return_value = MagicMock(data=[{"id": "sub-1"}])
    mock_get_supabase.return_value.table.return_value.insert.return_value = mock_insert

    body = BillingPrepareBody(
        user_id="u1",
        product_type="SAAS_BUILDING",
        amount=99000,
        goodname="정기결제",
    )
    out = run_billing_prepare(body)
    assert out["status"] == "success"
    assert out["data"]["subscription_id"] == "sub-1"
    assert out["data"]["gopaymethod"] == "CardBilling"
    assert out["data"]["oid"].startswith("TAI-BIL-")


@patch.dict(
    "os.environ",
    {
        "INICIS_BILLING_MID": "mid-test",
        "INICIS_BILLING_SIGN_KEY": "sign-test",
        "INICIS_BILLING_API_URL": "https://api.example.com/billing",
    },
    clear=False,
)
@patch("services.payment_svc.get_supabase")
@patch("services.payment_svc._billing_api_post")
def test_run_billing_charge_pauses_after_third_failure(mock_billing_post, mock_get_supabase):
    mock_billing_post.side_effect = PaymentPrepareError(400, "실패")

    sb = mock_get_supabase.return_value

    sub_q = MagicMock()
    sub_q.limit.return_value.execute.return_value = MagicMock(
        data=[{"id": "sub-1", "price": 10000, "product_type": "SAAS_BUILDING"}]
    )
    key_q = MagicMock()
    key_q.order.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{"id": "key-1", "bill_key": "bk", "failure_count": 2}]
    )
    billing_update_q = MagicMock()
    billing_update_q.eq.return_value.execute.return_value = MagicMock(data=[{"id": "key-1"}])
    sub_update_q = MagicMock()
    sub_update_q.eq.return_value.execute.return_value = MagicMock(data=[{"id": "sub-1"}])

    def table_side_effect(name: str):
        if name == "subscriptions":
            t = MagicMock()
            t.select.return_value.eq.return_value = sub_q
            t.update.return_value = sub_update_q
            return t
        if name == "billing_keys":
            t = MagicMock()
            t.select.return_value.eq.return_value.eq.return_value = key_q
            t.update.return_value = billing_update_q
            return t
        return MagicMock()

    sb.table.side_effect = table_side_effect

    body = SimpleNamespace(subscription_id="sub-1", amount=None, goodname=None)
    with pytest.raises(PaymentPrepareError):
        run_billing_charge(body)

    billing_update_q.eq.assert_called_once_with("id", "key-1")
    sub_update_q.eq.assert_called_once_with("id", "sub-1")
