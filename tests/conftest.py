"""Pytest autouse: launch secret for HTTP prepare 회귀 (PROD env 설정 아님)."""
from __future__ import annotations

import os

import pytest

_TEST_LAUNCH_SECRET = "test-payment-launch-secret-value-32b"


@pytest.fixture(autouse=True, scope="session")
def _b7_payment_launch_secret():
    os.environ.setdefault("PAYMENT_LAUNCH_SECRET", _TEST_LAUNCH_SECRET)
    os.environ.setdefault(
        "PAYMENT_LAUNCH_URL",
        "https://taieng.co.kr/_api/payments/tier-upgrade/pay",
    )
    yield
